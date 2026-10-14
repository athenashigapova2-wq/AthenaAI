import { beforeEach, describe, expect, it, vi } from "vitest";

const { isNativePlatform, exchangeCodeForSession, close } = vi.hoisted(() => ({
  isNativePlatform: vi.fn(),
  exchangeCodeForSession: vi.fn(),
  close: vi.fn(),
}));

vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform } }));
vi.mock("@capacitor/app", () => ({ App: {} }));
vi.mock("@capacitor/browser", () => ({ Browser: { close } }));
vi.mock("@/api/supabaseClient", () => ({
  supabase: { auth: { exchangeCodeForSession } },
}));

import {
  ANDROID_AUTH_ORIGIN,
  authRedirectUrl,
  consumeAuthCallback,
  parseAuthCallback,
} from "@/lib/authCallbacks";

beforeEach(() => {
  isNativePlatform.mockReset();
  exchangeCodeForSession.mockReset().mockResolvedValue({ error: null });
  close.mockReset().mockResolvedValue(undefined);
});

describe("Android auth callbacks", () => {
  it("uses allow-listable custom-scheme redirects on Android", () => {
    isNativePlatform.mockReturnValue(true);

    expect(authRedirectUrl("callback")).toBe(`${ANDROID_AUTH_ORIGIN}/callback`);
    expect(authRedirectUrl("reset-password")).toBe(`${ANDROID_AUTH_ORIGIN}/reset-password`);
  });

  it("keeps HTTPS browser redirects for the web build", () => {
    isNativePlatform.mockReturnValue(false);

    expect(authRedirectUrl("reset-password")).toBe(`${window.location.origin}/reset-password`);
  });

  it("parses OAuth and password-recovery links but rejects unrelated links", () => {
    expect(parseAuthCallback(`${ANDROID_AUTH_ORIGIN}/callback?code=oauth-code`)).toMatchObject({
      code: "oauth-code",
      destination: "/",
    });
    expect(parseAuthCallback(`${ANDROID_AUTH_ORIGIN}/reset-password?code=recovery-code`))
      .toMatchObject({ code: "recovery-code", destination: "/reset-password" });
    expect(parseAuthCallback(`${ANDROID_AUTH_ORIGIN}/reauth-delete?code=reauth-code`))
      .toMatchObject({
        code: "reauth-code",
        destination: "/profile",
        accountDeletionReauth: true,
      });
    expect(parseAuthCallback("https://example.com/auth/callback?code=ignored")).toBeNull();
  });

  it("exchanges the PKCE code before routing the app", async () => {
    const callback = `${ANDROID_AUTH_ORIGIN}/reset-password?code=unique-recovery-code`;

    await expect(consumeAuthCallback(callback)).resolves.toBe(true);

    expect(exchangeCodeForSession).toHaveBeenCalledWith("unique-recovery-code");
    expect(close).toHaveBeenCalledOnce();
    expect(window.location.pathname).toBe("/reset-password");
  });
});
