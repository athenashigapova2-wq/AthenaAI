// Supabase Edge Function: analyze-habits
// Считает частые продукты и разрыв по БЖУ за последние 14 дней, просит
// GigaChat сформулировать одну короткую проактивную подсказку и сохраняет
// результат в agent_memory. Вызывается лениво с фронтенда (Home.jsx),
// когда предыдущий анализ устарел (>24ч) — отдельный cron не нужен.
//
// Деплой: supabase functions deploy analyze-habits
// (использует тот же секрет GIGACHAT_AUTH_KEY, что и остальные функции)

import { createClient } from 'npm:@supabase/supabase-js@2';

const GIGACHAT_AUTH_KEY = Deno.env.get('GIGACHAT_AUTH_KEY');
const GIGACHAT_MODEL = Deno.env.get('GIGACHAT_MODEL') || 'GigaChat-2';
const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY');
const CA_CERT_URL = 'https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, 'Content-Type': 'application/json' },
  });
}

let cachedHttpClient: Deno.HttpClient | null = null;
let cachedToken: { value: string; expiresAt: number } | null = null;

async function getGigaChatHttpClient(): Promise<Deno.HttpClient> {
  if (cachedHttpClient) return cachedHttpClient;
  const certRes = await fetch(CA_CERT_URL);
  const certText = await certRes.text();
  cachedHttpClient = Deno.createHttpClient({ caCerts: [certText] });
  return cachedHttpClient;
}

async function getGigaChatToken(): Promise<string> {
  if (cachedToken && cachedToken.expiresAt > Date.now() + 5000) return cachedToken.value;
  const client = await getGigaChatHttpClient();
  const res = await fetch('https://ngw.devices.sberbank.ru:9443/api/v2/oauth', {
    method: 'POST',
    client,
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
      RqUID: crypto.randomUUID(),
      Authorization: `Basic ${GIGACHAT_AUTH_KEY}`,
    },
    body: 'scope=GIGACHAT_API_PERS',
  });
  if (!res.ok) throw new Error(`GigaChat auth failed: ${await res.text()}`);
  const data = await res.json();
  cachedToken = { value: data.access_token, expiresAt: data.expires_at };
  return cachedToken.value;
}

// Нормализуем название блюда для группировки ("Гречка с курицей 200г" ~ "гречка с курицей")
function normalizeName(name: string) {
  return (name || '').toLowerCase().replace(/\d+\s*(г|гр|ml|мл|kg|кг)?/g, '').trim();
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') return new Response('ok', { headers: CORS_HEADERS });
  if (req.method !== 'POST') return jsonResponse({ error: 'Method not allowed' }, 405);

  try {
    const authHeader = req.headers.get('Authorization') ?? '';
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: userData, error: userError } = await supabase.auth.getUser();
    if (userError || !userData?.user) return jsonResponse({ error: 'Unauthorized' }, 401);
    const userId = userData.user.id;

    const { language = 'en' } = await req.json().catch(() => ({}));

    const since = new Date();
    since.setDate(since.getDate() - 14);
    const sinceStr = since.toISOString().split('T')[0];

    const [{ data: meals }, { data: profiles }] = await Promise.all([
      supabase.from('meal_logs').select('*').eq('user_id', userId).gte('date', sinceStr),
      supabase.from('user_profiles').select('*').eq('user_id', userId).limit(1),
    ]);

    if (!meals || meals.length < 3) {
      // Недостаточно данных для осмысленного анализа — не выдумываем, честно говорим об этом
      return jsonResponse({ insufficient_data: true });
    }

    const profile = profiles?.[0] || null;

    // Частые продукты
    const counts: Record<string, number> = {};
    meals.forEach((m) => {
      const key = normalizeName(m.name);
      if (!key) return;
      counts[key] = (counts[key] || 0) + 1;
    });
    const frequentFoods = Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name]) => name);

    // Средний разрыв по БЖУ относительно целей (группируем по дням)
    const byDate: Record<string, { cal: number; p: number; c: number; f: number }> = {};
    meals.forEach((m) => {
      if (!byDate[m.date]) byDate[m.date] = { cal: 0, p: 0, c: 0, f: 0 };
      byDate[m.date].cal += m.calories || 0;
      byDate[m.date].p += m.protein_g || 0;
      byDate[m.date].c += m.carbs_g || 0;
      byDate[m.date].f += m.fat_g || 0;
    });
    const days = Object.values(byDate);
    const avg = days.reduce(
      (a, d) => ({ cal: a.cal + d.cal / days.length, p: a.p + d.p / days.length, c: a.c + d.c / days.length, f: a.f + d.f / days.length }),
      { cal: 0, p: 0, c: 0, f: 0 }
    );

    let macroGap = null;
    if (profile) {
      const gaps = [
        { macro: 'protein', diff: (avg.p - (profile.protein_target_g || 0)) / (profile.protein_target_g || 1) },
        { macro: 'carbs', diff: (avg.c - (profile.carb_target_g || 0)) / (profile.carb_target_g || 1) },
        { macro: 'fat', diff: (avg.f - (profile.fat_target_g || 0)) / (profile.fat_target_g || 1) },
      ].sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
      const top = gaps[0];
      if (Math.abs(top.diff) > 0.1) {
        macroGap = `${top.macro}:${top.diff > 0 ? 'over' : 'under'}`;
      }
    }

    const client = await getGigaChatHttpClient();
    const token = await getGigaChatToken();

    const prompt = `You are a nutrition coach analyzing a user's eating patterns from the last 14 days.
Frequently eaten foods: ${frequentFoods.join(', ') || 'not enough data'}.
Average daily macros: ${Math.round(avg.cal)} kcal, protein ${Math.round(avg.p)}g, carbs ${Math.round(avg.c)}g, fat ${Math.round(avg.f)}g.
${macroGap ? `Detected gap: ${macroGap}.` : 'No major macro gap detected.'}
Write ONE short, warm, specific, actionable suggestion (max 2 sentences) in ${language === 'ru' ? 'Russian' : 'English'}. Reference one of their frequent foods by name if possible. No generic advice, be concrete.`;

    const res = await fetch('https://api.giga.chat/v1/chat/completions', {
      method: 'POST',
      client,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ model: GIGACHAT_MODEL, messages: [{ role: 'user', content: prompt }] }),
    });

    if (!res.ok) return jsonResponse({ error: `LLM error: ${await res.text()}` }, 502);
    const data = await res.json();
    const suggestion = data.choices?.[0]?.message?.content?.trim() || '';

    const { error: upsertErr } = await supabase.from('agent_memory').upsert(
      {
        user_id: userId,
        frequent_foods: frequentFoods,
        macro_gap: macroGap,
        suggestion,
        suggestion_generated_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
      { onConflict: 'user_id' }
    );
    if (upsertErr) throw upsertErr;

    return jsonResponse({ frequent_foods: frequentFoods, macro_gap: macroGap, suggestion });
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
});
