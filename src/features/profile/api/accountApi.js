import { supabase } from "@/api/supabaseClient";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { authRedirectUrl } from "@/lib/authCallbacks";
import { apiErrorMessage, fetchBackend } from "@/api/backendClient";

const API_URL = import.meta.env.DEV
  ? "/agent-api"
  : (import.meta.env.VITE_AGENT_API_URL || "").replace(/\/$/, "");

export async function reauthenticateAccountDeletionWithPassword(email, password) {
  if (!password) throw new Error("Enter your current password.");
  const { data, error } = await supabase.auth.signInWithPassword({ email, password });
  if (error || !data.session?.access_token) {
    throw new Error("Re-authentication failed. Check your password and try again.");
  }
  return data.session;
}

export async function startAccountDeletionOAuthReauthentication(provider) {
  const native = Capacitor.isNativePlatform();
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: {
      redirectTo: authRedirectUrl("reauth-delete"),
      skipBrowserRedirect: native,
      queryParams: { prompt: "select_account" },
    },
  });
  if (error) throw error;
  if (native) {
    if (!data?.url) throw new Error("OAuth provider did not return an authorization URL");
    await Browser.open({ url: data.url });
  }
}

export async function deletePermanentAccount(email) {
  if (!API_URL) throw new Error("VITE_AGENT_API_URL is not configured");

  const { data, error } = await supabase.auth.getSession();
  const accessToken = data.session?.access_token;
  if (error || !accessToken) {
    throw new Error("Your session expired. Re-authenticate and try again.");
  }

  const response = await fetchBackend(`${API_URL}/api/v1/account`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ confirmation: "DELETE", email }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      apiErrorMessage(payload, `Account deletion failed (${response.status})`),
    );
  }
  return payload;
}
