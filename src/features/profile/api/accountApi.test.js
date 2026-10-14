import { beforeEach, describe, expect, it, vi } from "vitest";

const { getSession, signInWithPassword, signInWithOAuth, isNativePlatform, open } = vi.hoisted(() => ({
  getSession: vi.fn(),
  signInWithPassword: vi.fn(),
  signInWithOAuth: vi.fn(),
  isNativePlatform: vi.fn(),
  open: vi.fn(),
}));

vi.mock("@/api/supabaseClient", () => ({
  supabase: { auth: { getSession, signInWithPassword, signInWithOAuth } },
}));
vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform } }));
vi.mock("@capacitor/browser", () => ({ Browser: { open } }));
vi.mock("@/lib/authCallbacks", () => ({
  authRedirectUrl: vi.fn((destination) => `dev.aminashigapova2.athena://auth/${destination}`),
}));

import {
  deletePermanentAccount,
  reauthenticateAccountDeletionWithPassword,
  startAccountDeletionOAuthReauthentication,
} from "@/features/profile/api/accountApi";

beforeEach(() => {
  vi.restoreAllMocks();
  getSession.mockReset().mockResolvedValue({
    data: { session: { access_token: "reauthenticated-token" } },
    error: null,
  });
  signInWithPassword.mockReset().mockResolvedValue({
    data: { session: { access_token: "password-session" } },
    error: null,
  });
  signInWithOAuth.mockReset().mockResolvedValue({
    data: { url: "https://provider.example/authorize" },
    error: null,
  });
  isNativePlatform.mockReset().mockReturnValue(true);
  open.mockReset().mockResolvedValue(undefined);
});

describe("permanent account deletion", () => {
  it("requires the current password instead of refreshing the existing session", async () => {
    await reauthenticateAccountDeletionWithPassword("owner@example.com", "current-password");

    expect(signInWithPassword).toHaveBeenCalledWith({
      email: "owner@example.com",
      password: "current-password",
    });
  });

  it("starts a fresh OAuth login using the Android deletion callback", async () => {
    await startAccountDeletionOAuthReauthentication("google");

    expect(signInWithOAuth).toHaveBeenCalledWith({
      provider: "google",
      options: {
        redirectTo: "dev.aminashigapova2.athena://auth/reauth-delete",
        skipBrowserRedirect: true,
        queryParams: { prompt: "select_account" },
      },
    });
    expect(open).toHaveBeenCalledWith({ url: "https://provider.example/authorize" });
  });

  it("sends the recently authenticated session with destructive confirmation", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "deleted",
      storage_objects_deleted: 1,
      runtime_records_scrubbed: 2,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);

    await deletePermanentAccount("owner@example.com");

    const [, options] = fetch.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer reauthenticated-token");
    expect(JSON.parse(options.body)).toEqual({
      confirmation: "DELETE",
      email: "owner@example.com",
    });
  });

  it("does not call the backend without an authenticated session", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null }, error: new Error("expired") });
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);

    await expect(deletePermanentAccount("owner@example.com"))
      .rejects.toThrow("Re-authenticate");
    expect(fetch).not.toHaveBeenCalled();
  });
});
