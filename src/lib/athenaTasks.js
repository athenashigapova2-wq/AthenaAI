import { supabase } from '@/api/supabaseClient';

const API_URL = import.meta.env.DEV
  ? '/agent-api'
  : (import.meta.env.VITE_AGENT_API_URL || '').replace(/\/$/, '');

/**
 * Calls a narrow, server-owned AI use case through canonical FastAPI.
 *
 * The browser never supplies a prompt, model name, or response schema. Those
 * are selected and validated by the Python AI Execution Layer.
 */
export async function invokeAthenaTask(useCase, input) {
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error('Your session expired. Please sign in again.');
  if (!API_URL) throw new Error('VITE_AGENT_API_URL is not configured');

  const response = await fetch(`${API_URL}/api/v1/ai/tasks/${encodeURIComponent(useCase)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ input }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || `AI task failed (${response.status})`);
  }
  return payload;
}
