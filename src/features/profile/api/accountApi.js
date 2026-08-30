import { supabase } from "@/api/supabaseClient";

const API_URL = import.meta.env.DEV
  ? "/agent-api"
  : (import.meta.env.VITE_AGENT_API_URL || "").replace(/\/$/, "");

export async function deletePermanentAccount(email) {
  if (!API_URL) throw new Error("VITE_AGENT_API_URL is not configured");

  // A freshly issued access token satisfies the backend's recent-auth gate.
  const { data, error } = await supabase.auth.refreshSession();
  const token = data.session?.access_token;
  if (error || !token) {
    throw new Error("Your session expired. Please sign in again before deleting the account.");
  }

  const response = await fetch(`${API_URL}/api/v1/account`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ confirmation: "DELETE", email }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      payload?.detail || payload?.error || `Account deletion failed (${response.status})`,
    );
  }
  return payload;
}
