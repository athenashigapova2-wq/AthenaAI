import { supabase } from '@/api/supabaseClient';

const API_URL = import.meta.env.DEV
  ? '/agent-api'
  : (import.meta.env.VITE_AGENT_API_URL || '').replace(/\/$/, '');

async function post(path, body) {
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error('Your session expired. Please sign in again.');
  if (!API_URL) throw new Error('VITE_AGENT_API_URL is not configured');

  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(payload?.detail || payload?.error || `Nutrition request failed (${response.status})`);
  }
  return payload;
}

export function estimateMeal(description, locale) {
  return post('/api/v1/nutrition/meal-estimate', { description, locale });
}

export function generateHabitInsight(locale) {
  return post('/api/v1/nutrition/habit-insight', { locale });
}
