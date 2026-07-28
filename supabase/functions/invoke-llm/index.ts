// Supabase Edge Function: invoke-llm
// Заменяет base44.integrations.Core.InvokeLLM({ prompt, response_json_schema }).
// Держит ANTHROPIC_API_KEY на сервере — ключ никогда не попадает в клиентский бандл.
//
// Деплой:
//   supabase functions deploy invoke-llm
//   supabase secrets set ANTHROPIC_API_KEY=sk-ant-...

import { createClient } from 'npm:@supabase/supabase-js@2';

const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
const SUPABASE_ANON_KEY = Deno.env.get('SUPABASE_ANON_KEY');

Deno.serve(async (req) => {
  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Method not allowed' }), { status: 405 });
  }

  try {
    // Проверяем, что запрос пришёл от авторизованного пользователя (не важно кто именно,
    // но токен должен быть валидным — иначе кто угодно тратит наши LLM-кредиты).
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

    // Если задана JSON-схема — просим модель вызвать "инструмент" с этой схемой.
    // Это надёжнее, чем просить "верни JSON" в тексте: Claude обязан вернуть
    // валидный по схеме tool_use-блок.
    const body: Record<string, unknown> = {
      model: 'claude-sonnet-4-6',
      max_tokens: 2048,
      messages: [{ role: 'user', content: prompt }],
    };

    if (response_json_schema) {
      body.tools = [
        {
          name: 'respond',
          description: 'Return the structured response.',
          input_schema: response_json_schema,
        },
      ];
      body.tool_choice = { type: 'tool', name: 'respond' };
    }

    const res = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify(body),
    });

    if (!res.ok) {
      const errText = await res.text();
      return new Response(JSON.stringify({ error: `LLM error: ${errText}` }), { status: 502 });
    }

    const data = await res.json();

    if (response_json_schema) {
      const toolUse = data.content?.find((b: any) => b.type === 'tool_use');
      if (!toolUse) {
        return new Response(JSON.stringify({ error: 'No structured response returned' }), { status: 502 });
      }
      return new Response(JSON.stringify(toolUse.input), {
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const text = data.content?.find((b: any) => b.type === 'text')?.text ?? '';
    return new Response(JSON.stringify({ text }), {
      headers: { 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }
});
