import { afterEach, describe, expect, it, vi } from "vitest";

import { apiErrorMessage, backendHeaders, fetchBackend } from "@/api/backendClient";

afterEach(() => vi.unstubAllGlobals());

describe("backend client", () => {
  it("adds the ngrok WebView bypass only for free ngrok endpoints", () => {
    expect(backendHeaders("https://demo.ngrok-free.dev/api", {
      Authorization: "Bearer token",
    })).toEqual({
      Authorization: "Bearer token",
      "ngrok-skip-browser-warning": "athena-android",
    });
    expect(backendHeaders("https://api.example.com/api", {
      Authorization: "Bearer token",
    })).toEqual({ Authorization: "Bearer token" });
  });

  it("preserves request options while applying tunnel headers", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);

    await fetchBackend("https://demo.ngrok-free.dev/events", {
      signal: AbortSignal.timeout(1_000),
      headers: { Accept: "text/event-stream" },
    });

    expect(fetch.mock.calls[0][1].headers).toMatchObject({
      Accept: "text/event-stream",
      "ngrok-skip-browser-warning": "athena-android",
    });
  });

  it("renders FastAPI validation details instead of object coercion", () => {
    expect(apiErrorMessage({
      detail: [{ msg: "Field is required" }, { msg: "Invalid value" }],
    }, "Request failed")).toBe("Field is required; Invalid value");
  });
});
