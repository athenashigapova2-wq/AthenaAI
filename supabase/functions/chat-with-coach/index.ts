// Supabase Edge Function: chat-with-coach
// Полная замена base44 "agent" nutrition_coach (agents.createConversation /
// addMessage / subscribeToConversation) + встроенной функции nutritionInsight.
//
// Что делает:
//   1. Проверяет пользователя по JWT.
//   2. Создаёт разговор, если conversation_id не передан.
//   3. Сохраняет сообщение пользователя.
//   4. Считает детерминированную "nutritionInsight"-сводку сама (без похода к LLM).
//   5. Собирает контекст (профиль, сегодняшние и недавние приёмы пищи, вес,
//      список покупок) и системный промпт (перенесён из base44/agents/nutrition_coach.jsonc).
//   6. Зовёт GigaChat API (Сбер, бесплатный тариф для физлиц) с историей диалога.
//   7. Сохраняет и возвращает ответ ассистента.
//
// Деплой:
//   supabase functions deploy chat-with-coach
//   supabase secrets set GIGACHAT_AUTH_KEY=<Base64(Client ID:Client Secret)>

import { createClient } from 'npm:@supabase/supabase-js@2';

const GIGACHAT_AUTH_KEY = Deno.env.get('GIGACHAT_AUTH_KEY');
const CA_CERT_URL = 'https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt';

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
  if (cachedToken && cachedToken.expiresAt > Date.now() + 5000) {
    return cachedToken.value;
  }
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

const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY');
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

const LANG_NAME = {
  en: 'English', ru: 'Russian', es: 'Spanish', fr: 'French', de: 'German',
  // добавь остальные языки из src/lib/i18n.jsx по мере необходимости
};

// Перенесено почти дословно из base44/agents/nutrition_coach.jsonc -> "instructions"
const BASE_INSTRUCTIONS = `You are MacroCoach, a warm, practical, no-nonsense nutrition coach living inside a macro-tracking app.

Your job is to help the user reach their nutrition goals through conversation. You have their data below (profile, meals, weight logs, shopping list) — use it to give specific, personalized advice, never generic.

## Tone & Style
- Be warm, encouraging, and concise. Talk like a knowledgeable friend, not a doctor or a lecturer.
- Keep replies SHORT and STRUCTURED. Maximum ~80 words. Always use: one short opening line, then 2-4 short bullet points (or a numbered list), then a one-line takeaway. Use line breaks between points. NEVER write a wall of text.
- Language: always reply in the language specified below. Every food, ingredient, and product name must be in that same language.
- Never preach, shame, or moralize about food. There are no "bad" foods.
- If you don't know something about the user, ask — don't assume.

## What You Do
- Answer nutrition and meal-planning questions using the user's actual data and targets below.
- When asked for meal ideas, consider their remaining macros for today, budget, cooking skill, allergies, and food preferences. Never recommend foods they're allergic to or dislike.
- You cannot create meal logs directly — tell them to use the Log button or the Coach tab.
- Interpret their progress using the nutrition summary below; don't recompute it yourself.
- Help with shopping: suggest what to add to their list based on their meal plan.
- If asked about weight changes, reference their weight history and relate it to calorie intake.

## Boundaries
- You are a coach, not a doctor. For medical conditions, medication interactions, eating disorders, or clinical nutrition advice, tell them to consult a healthcare professional.
- Don't make up nutrition numbers — if unsure about macros for a specific food, say so and suggest they verify.
- Don't recommend supplements or weight-loss pills.
- If the user hasn't completed onboarding (no profile found), encourage them to set up their profile first.`;

function computeNutritionInsight(profile, todayMeals) {
  if (!profile) return null;
  const consumed = todayMeals.reduce(
    (a, m) => ({
      cal: a.cal + (m.calories || 0),
      p: a.p + (m.protein_g || 0),
      c: a.c + (m.carbs_g || 0),
      f: a.f + (m.fat_g || 0),
    }),
    { cal: 0, p: 0, c: 0, f: 0 }
  );
  const targets = {
    calories: profile.calorie_target || 0,
    protein: profile.protein_target_g || 0,
    carbs: profile.carb_target_g || 0,
    fat: profile.fat_target_g || 0,
  };
  const remaining = {
    calories: Math.max(targets.calories - consumed.cal, 0),
    protein: Math.max(targets.protein - consumed.p, 0),
    carbs: Math.max(targets.carbs - consumed.c, 0),
    fat: Math.max(targets.fat - consumed.f, 0),
  };
  const overCalories = consumed.cal > targets.calories;
  const gaps = [
    { macro: 'protein', ratio: remaining.protein / (targets.protein || 1) },
    { macro: 'carbs', ratio: remaining.carbs / (targets.carbs || 1) },
    { macro: 'fat', ratio: remaining.fat / (targets.fat || 1) },
  ].sort((a, b) => b.ratio - a.ratio);

  return {
    consumed, targets, remaining,
    over_calories: overCalories,
    verdict: overCalories ? 'over_target' : remaining.calories === 0 ? 'on_target' : 'under_target',
    priority_macro: gaps[0].macro,
    meal_count: todayMeals.length,
  };
}

Deno.serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405 });
  }

  try {
    const authHeader = req.headers.get('Authorization') ?? '';
    const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      global: { headers: { Authorization: authHeader } },
    });
    const { data: userData, error: userError } = await supabase.auth.getUser();
    if (userError || !userData?.user) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), { status: 401 });
    }
    const userId = userData.user.id;

    const { conversation_id, message, language = 'en' } = await req.json();
    if (!message || !message.trim()) {
      return new Response(JSON.stringify({ error: 'message required' }), { status: 400 });
    }

    // 1. Разговор — берём существующий или создаём новый
    let conversationId = conversation_id;
    if (!conversationId) {
      const { data: conv, error: convErr } = await supabase
        .from('agent_conversations')
        .insert({
          user_id: userId,
          agent_name: 'nutrition_coach',
          metadata: { language },
          title: message.slice(0, 48),
        })
        .select()
        .single();
      if (convErr) throw convErr;
      conversationId = conv.id;
    }

    // 2. Сохраняем сообщение пользователя
    const { error: userMsgErr } = await supabase
      .from('agent_messages')
      .insert({ conversation_id: conversationId, role: 'user', content: message });
    if (userMsgErr) throw userMsgErr;

    // 3. Контекст пользователя (те же сущности, что раньше читал агент)
    const today = new Date().toISOString().split('T')[0];
    const [{ data: profiles }, { data: todayMeals }, { data: weightLogs }, { data: shoppingItems }, { data: history }] =
      await Promise.all([
        supabase.from('user_profiles').select('*').eq('user_id', userId).limit(1),
        supabase.from('meal_logs').select('*').eq('user_id', userId).eq('date', today),
        supabase.from('weight_logs').select('*').eq('user_id', userId).order('date', { ascending: false }).limit(10),
        supabase.from('shopping_items').select('*').eq('user_id', userId),
        supabase.from('agent_messages').select('role, content').eq('conversation_id', conversationId).order('created_at', { ascending: true }),
      ]);

    const profile = profiles?.[0] || null;
    const insight = computeNutritionInsight(profile, todayMeals || []);

    const contextBlock = `
## Language for this reply
${LANG_NAME[language] || language}

## User profile
${profile ? JSON.stringify({
      goal: profile.goal, budget: profile.budget, cooking_skill: profile.cooking_skill,
      allergies: profile.allergies, disliked_foods: profile.disliked_foods, favorite_foods: profile.favorite_foods,
    }) : 'No profile yet — user has not completed onboarding.'}

## Nutrition summary (deterministic — do not recompute)
${insight ? JSON.stringify(insight) : 'No data yet.'}

## Recent weight log (most recent first)
${(weightLogs || []).map((w) => `${w.date}: ${w.weight_kg}kg`).join('; ') || 'none'}

## Shopping list
${(shoppingItems || []).map((s) => s.name).join(', ') || 'empty'}
`.trim();

    const systemPrompt = `${BASE_INSTRUCTIONS}\n\n${contextBlock}`;

    // 4. История диалога для GigaChat (формат OpenAI-совместимый: role user/assistant)
    const chatMessages = [
      { role: 'system', content: systemPrompt },
      ...(history || []).map((m) => ({ role: m.role, content: m.content })),
    ];

    const client = await getGigaChatHttpClient();
    const token = await getGigaChatToken();

    const res = await fetch('https://gigachat.devices.sberbank.ru/api/v1/chat/completions', {
      method: 'POST',
      client,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        model: 'GigaChat',
        messages: chatMessages,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      return new Response(JSON.stringify({ error: `LLM error: ${errText}` }), { status: 502 });
    }

    const data = await res.json();
    const replyText = data.choices?.[0]?.message?.content?.trim() || '';

    // 5. Сохраняем ответ ассистента (через service_role — RLS для user-insert
    //    не пускает "чужую" роль assistant, поэтому используем сервисный ключ)
    const supabaseAdmin = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const { error: assistantMsgErr } = await supabaseAdmin
      .from('agent_messages')
      .insert({ conversation_id: conversationId, role: 'assistant', content: replyText });
    if (assistantMsgErr) throw assistantMsgErr;

    return new Response(
      JSON.stringify({ conversation_id: conversationId, reply: replyText }),
      { headers: { 'Content-Type': 'application/json' } }
    );
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
});
