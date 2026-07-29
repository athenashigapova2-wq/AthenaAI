// Supabase Edge Function: invoke-llm
// Заменяет base44.integrations.Core.InvokeLLM({ prompt, response_json_schema }).
// Использует GigaChat API (Сбер) — бесплатный тариф для физлиц (1 млн токенов
// в месяц), регистрация через SberID, без банковской карты, без VPN.
//
// Важно про сертификат: GigaChat требует доверия корневому сертификату НУЦ
// Минцифры (иначе TLS-запрос падает с ошибкой). Ниже он скачивается один раз
// при холодном старте функции и используется для всех запросов к Сберу.
//
// Деплой:
//   supabase functions deploy invoke-llm
//   supabase secrets set GIGACHAT_AUTH_KEY=<Base64(Client ID:Client Secret) из личного кабинета Sber Developers>

import { createClient } from 'npm:@supabase/supabase-js@2';

const GIGACHAT_AUTH_KEY = Deno.env.get('GIGACHAT_AUTH_KEY');
const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY');

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

function extractJson(text: string) {
  // Модель иногда оборачивает JSON в ```json ... ``` — вырезаем на всякий случай
  const cleaned = text.replace(/```json\s*|```/g, '').trim();
  return JSON.parse(cleaned);
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

    const { prompt, response_json_schema } = await req.json();
    if (!prompt) {
      return new Response(JSON.stringify({ error: 'prompt required' }), { status: 400 });
    }

    const client = await getGigaChatHttpClient();
    const token = await getGigaChatToken();

    const finalPrompt = response_json_schema
      ? `${prompt}\n\nRespond with ONLY valid JSON matching this schema, no other text, no markdown fences:\n${JSON.stringify(response_json_schema)}`
      : prompt;

    const res = await fetch('https://gigachat.devices.sberbank.ru/api/v1/chat/completions', {
      method: 'POST',
      client,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        model: 'GigaChat',
        messages: [{ role: 'user', content: finalPrompt }],
      }),
    });

    if (!res.ok) {
      return new Response(JSON.stringify({ error: `LLM error: ${await res.text()}` }), { status: 502 });
    }

    const data = await res.json();
    const text = data.choices?.[0]?.message?.content ?? '';

    if (response_json_schema) {
      try {
        return new Response(JSON.stringify(extractJson(text)), {
          headers: { 'Content-Type': 'application/json' },
        });
      } catch {
        return new Response(JSON.stringify({ error: 'Invalid JSON from model', raw: text }), { status: 502 });
      }
    }

    return new Response(JSON.stringify({ text }), { headers: { 'Content-Type': 'application/json' } });
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
});
