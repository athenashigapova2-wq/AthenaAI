import { beforeEach, describe, expect, it, vi } from "vitest";

const { refreshSession } = vi.hoisted(() => ({ refreshSession: vi.fn() }));

vi.mock("@/api/supabaseClient", () => ({
  supabase: { auth: { refreshSession } },
}));

import { deletePermanentAccount } from "@/features/profile/api/accountApi";

beforeEach(() => {
  refreshSession.mockResolvedValue({
    data: { session: { access_token: "fresh-token" } },
    error: null,
  });
});

describe("permanent account deletion", () => {
  it("refreshes auth and sends the explicit destructive confirmation", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "deleted",
      storage_objects_deleted: 1,
      runtime_records_scrubbed: 2,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);

    await deletePermanentAccount("owner@example.com");

    expect(refreshSession).toHaveBeenCalledOnce();
    const [, options] = fetch.mock.calls[0];
    expect(options.method).toBe("DELETE");
    expect(options.headers.Authorization).toBe("Bearer fresh-token");
    expect(JSON.parse(options.body)).toEqual({
      confirmation: "DELETE",
      email: "owner@example.com",
    });
  });

  it("does not call the backend when recent authentication cannot be obtained", async () => {
    refreshSession.mockResolvedValueOnce({ data: { session: null }, error: new Error("expired") });
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);

    await expect(deletePermanentAccount("owner@example.com")).rejects.toThrow("sign in again");
    expect(fetch).not.toHaveBeenCalled();
  });
});
