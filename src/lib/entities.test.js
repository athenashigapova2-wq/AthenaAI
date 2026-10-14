import { beforeEach, describe, expect, it, vi } from "vitest";

const { from, getUser } = vi.hoisted(() => ({
  from: vi.fn(),
  getUser: vi.fn(),
}));

vi.mock("@/api/supabaseClient", () => ({
  supabase: { from, auth: { getUser } },
}));

import { entities } from "./entities";

beforeEach(() => {
  from.mockReset();
  getUser.mockResolvedValue({ data: { user: { id: "user-1" } }, error: null });
});

describe("entity idempotent create", () => {
  it("returns the committed row when an insert response fails", async () => {
    let storedRow = null;
    let fromCall = 0;
    const findBuilder = () => ({
      select() { return this; },
      eq() { return this; },
      limit: async () => ({ data: storedRow ? [storedRow] : [], error: null }),
    });
    const insertBuilder = {
      insert(payload) {
        storedRow = { id: "meal-1", ...payload };
        return this;
      },
      select() { return this; },
      single: async () => ({ data: null, error: new Error("response lost") }),
    };
    from.mockImplementation(() => {
      fromCall += 1;
      return fromCall === 2 ? insertBuilder : findBuilder();
    });

    const result = await entities.MealLog.createIdempotently(
      { name: "Oats", calories: 350 },
      "ui:meal:stable-key",
    );

    expect(result.id).toBe("meal-1");
    expect(result.idempotency_key).toBe("ui:meal:stable-key");
    expect(result.idempotency_fingerprint).toMatch(/^[a-f0-9]{64}$/);
    expect(from).toHaveBeenCalledTimes(3);
  });
});
