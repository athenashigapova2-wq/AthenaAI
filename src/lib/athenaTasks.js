import { supabase } from '@/api/supabaseClient';

/**
 * Calls a narrow, server-owned AI use case.
 *
 * The browser never supplies a prompt, model name, or response schema. Those
 * are selected and validated by the Edge Function for the requested use case.
 */
export async function invokeAthenaTask(useCase, input) {
  const { data, error } = await supabase.functions.invoke('athena-task', {
    body: { use_case: useCase, input },
  });
  if (error) throw error;
  if (data?.error) throw new Error(data.error);
  return data;
}
