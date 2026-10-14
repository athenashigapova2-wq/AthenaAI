import { App as CapacitorApp } from "@capacitor/app";
import { Browser } from "@capacitor/browser";
import { Capacitor } from "@capacitor/core";
import { supabase } from "@/api/supabaseClient";

export const ANDROID_AUTH_SCHEME = "dev.aminashigapova2.athena";
export const ANDROID_AUTH_ORIGIN = `${ANDROID_AUTH_SCHEME}://auth`;

const handledUrls = new Set();

export function authRedirectUrl(destination = "callback") {
  if (Capacitor.isNativePlatform()) {
    return `${ANDROID_AUTH_ORIGIN}/${destination}`;
  }
  const path = destination === "callback"
    ? "/"
    : (destination === "reauth-delete" ? "/profile?reauth=account-delete" : `/${destination}`);
  return new URL(path, window.location.origin).toString();
}

export function parseAuthCallback(rawUrl) {
  const url = new URL(rawUrl);
  if (url.protocol !== `${ANDROID_AUTH_SCHEME}:` || url.hostname !== "auth") {
    return null;
  }

  const fragment = new URLSearchParams(url.hash.replace(/^#/, ""));
  const get = (name) => url.searchParams.get(name) || fragment.get(name);
  const accountDeletionReauth = url.pathname === "/reauth-delete";
  const destination = url.pathname === "/reset-password"
    ? "/reset-password"
    : (accountDeletionReauth ? "/profile" : "/");
  return {
    code: get("code"),
    error: get("error_description") || get("error"),
    destination,
    accountDeletionReauth,
  };
}

export async function consumeAuthCallback(rawUrl) {
  const callback = parseAuthCallback(rawUrl);
  if (!callback || handledUrls.has(rawUrl)) return false;
  handledUrls.add(rawUrl);

  try {
    if (callback.error) throw new Error(callback.error);
    if (callback.code) {
      const { error } = await supabase.auth.exchangeCodeForSession(callback.code);
      if (error) throw error;
    } else {
      throw new Error("PKCE authentication callback is missing a session code");
    }

    await Browser.close().catch(() => undefined);
    if (callback.accountDeletionReauth) {
      sessionStorage.setItem("athena.accountDeletionReauthenticated", "1");
      window.dispatchEvent(new CustomEvent("athena:account-deletion-reauthenticated"));
    }
    window.history.replaceState({}, "", callback.destination);
    window.dispatchEvent(new PopStateEvent("popstate"));
    return true;
  } catch (error) {
    handledUrls.delete(rawUrl);
    throw error;
  }
}

export function consumeAccountDeletionReauthMarker() {
  const completed = sessionStorage.getItem("athena.accountDeletionReauthenticated") === "1";
  if (completed) sessionStorage.removeItem("athena.accountDeletionReauthenticated");
  return completed;
}

export function registerNativeAuthCallbacks(onError) {
  if (!Capacitor.isNativePlatform()) return () => undefined;

  let disposed = false;
  let listenerHandle;
  const handleUrl = (url) => consumeAuthCallback(url).catch(onError);

  CapacitorApp.addListener("appUrlOpen", ({ url }) => handleUrl(url)).then((handle) => {
    if (disposed) handle.remove();
    else listenerHandle = handle;
  }).catch(onError);
  CapacitorApp.getLaunchUrl().then((result) => {
    if (!disposed && result?.url) handleUrl(result.url);
  }).catch(onError);

  return () => {
    disposed = true;
    listenerHandle?.remove();
  };
}
