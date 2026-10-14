import { describe, expect, it } from "vitest";

import { payloadFingerprint } from "./idempotency";

describe("idempotency payload fingerprint", () => {
  it("is stable across object key order and changes with the payload", async () => {
    const first = await payloadFingerprint({ name: "Oats", calories: 350 });
    const reordered = await payloadFingerprint({ calories: 350, name: "Oats" });
    const changed = await payloadFingerprint({ calories: 351, name: "Oats" });

    expect(first).toBe(reordered);
    expect(first).not.toBe(changed);
    expect(first).toMatch(/^[a-f0-9]{64}$/);
  });
});
