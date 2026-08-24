// Supabase Edge Function: estimate-meal
// Основной точный поиск для LogMealDialog.jsx:
//   1. Просим GigaChat извлечь из описания (на любом языке) английский поисковый
//      термин + количество в граммах.
//   2. Ищем по food_nutrients (ILIKE по-английски, база уже на английском).
//   3. Если нашлись кандидаты — просим GigaChat выбрать лучший (или NONE).
//   4. Нашли — считаем точные БЖУ по найденной строке * граммовка/100.
//      Не нашли — как раньше, чистая оценка ИИ без базы.
//
// Деплой: supabase functions deploy estimate-meal
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

function extractJson(text: string) {
  const cleaned = text.replace(/```json\s*|```/g, '').trim();
  return JSON.parse(cleaned);
}

async function askGigaChat(client: Deno.HttpClient, token: string, prompt: string, schema?: object) {
  const finalPrompt = schema
    ? `${prompt}\n\nRespond with ONLY valid JSON matching this schema, no other text, no markdown fences:\n${JSON.stringify(schema)}`
    : prompt;
  const res = await fetch('https://api.giga.chat/v1/chat/completions', {
    method: 'POST',
    client,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ model: GIGACHAT_MODEL, messages: [{ role: 'user', content: finalPrompt }] }),
  });
  if (!res.ok) throw new Error(`LLM error: ${await res.text()}`);
  const data = await res.json();
  const text = data.choices?.[0]?.message?.content ?? '';
  return schema ? extractJson(text) : text;
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

    const { description, language = 'en' } = await req.json();
    if (!description?.trim()) return jsonResponse({ error: 'description required' }, 400);

    const client = await getGigaChatHttpClient();
    const token = await getGigaChatToken();

    // Шаг 1: извлекаем английский поисковый термин + граммовку
    const extracted = await askGigaChat(
      client, token,
      `Extract from this food description (any language): "${description}". Give a short core food name in English (2-4 words, no adjectives like "fresh"/"tasty", no brand names) suitable for a database search, and the quantity in grams (if not specified, assume a reasonable typical portion).`,
      { type: 'object', properties: { english_term: { type: 'string' }, quantity_g: { type: 'number' } }, required: ['english_term', 'quantity_g'] }
    );

    const term = (extracted.english_term || '').trim();
    const grams = Number(extracted.quantity_g) || 100;

    let candidates = [];
    if (term) {
      const { data } = await supabase.rpc('search_food_nutrients', { search_term: term, match_limit: 15 });
      candidates = data || [];
    }

    if (candidates.length === 0) {
      // Ничего похожего в базе — честно говорим клиенту, чтобы он сделал fallback на чистую оценку ИИ
      return jsonResponse({ matched: false });
    }

    // Шаг 2: просим GigaChat выбрать лучшее совпадение среди кандидатов
    const match = await askGigaChat(
      client, token,
      `User described this food (original, any language): "${description}".\nCandidates from database (English names):\n${candidates.map((c) => `- ${c.food_name}`).join('\n')}\nWhich candidate is the best match? Respond with the exact food_name string, or "NONE" if none genuinely match.`,
      { type: 'object', properties: { food_name: { type: 'string' } }, required: ['food_name'] }
    );

    const chosen = candidates.find((c) => c.food_name === match.food_name);
    if (!chosen || match.food_name === 'NONE') {
      return jsonResponse({ matched: false });
    }

    const factor = grams / 100;
    return jsonResponse({
      matched: true,
      name: chosen.food_name,
      quantity_g: grams,
      calories: Math.round(chosen.calories_per_100g * factor),
      protein_g: Math.round(chosen.protein_g * factor * 10) / 10,
      carbs_g: Math.round(chosen.carbs_g * factor * 10) / 10,
      fat_g: Math.round(chosen.fat_g * factor * 10) / 10,
    });
  } catch (error) {
    return jsonResponse({ error: error.message }, 500);
  }
});
