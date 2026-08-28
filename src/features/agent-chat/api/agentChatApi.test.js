import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { getSession } = vi.hoisted(() => ({ getSession: vi.fn() }));

vi.mock("@/api/supabaseClient", () => ({
  supabase: {
    auth: {
      getSession,
    },
  },
}));

import {
  confirmWriteAction,
  rejectWriteAction,
  startAgentMessage,
} from "@/features/agent-chat/api/agentChatApi";

afterEach(() => {
  vi.unstubAllGlobals();
});

beforeEach(() => {
  getSession.mockResolvedValue({
    data: { session: { access_token: "test-token" } },
    error: null,
  });
});

describe("agent chat SSE lifecycle", () => {
  it("resolves a completed event and exposes intermediate progress", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: running\ndata: {"job_id":"job-1","status":"running","stage":"running"}\n\n',
        ));
        controller.enqueue(encoder.encode(
          'event: tool_call\ndata: {"job_id":"job-1","status":"running","stage":"tool_call","tool_name":"get_daily_summary"}\n\n',
        ));
        controller.enqueue(encoder.encode(
          'event: completed\ndata: {"job_id":"job-1","status":"succeeded","stage":"completed","answer":"Done","conversation_id":"conversation-1"}\n\n',
        ));
        controller.close();
      },
    });
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        job_id: "job-1",
        status: "queued",
        status_url: "http://test/jobs/job-1",
      }), { status: 202, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    vi.stubGlobal("fetch", fetch);
    const progress = [];

    const request = startAgentMessage({
      conversationId: null,
      message: "How am I doing?",
      locale: "en",
      onProgress: (event) => progress.push(event.stage),
    });

    await expect(request.promise).resolves.toMatchObject({
      answer: "Done",
      conversation_id: "conversation-1",
    });
    expect(progress).toEqual(["queued", "running", "tool_call", "completed"]);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("rejects an expired session before sending a request", async () => {
    getSession.mockResolvedValueOnce({ data: { session: null }, error: null });
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);

    const request = startAgentMessage({ message: "hello", locale: "en" });

    await expect(request.promise).rejects.toThrow("Your session expired");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("surfaces a failed Redis/worker job from the event stream", async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          'event: failed\ndata: {"job_id":"job-2","status":"failed","error":"Worker unavailable"}\n\n',
        ));
        controller.close();
      },
    });
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ job_id: "job-2", status: "queued" }), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(stream, {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      }));
    vi.stubGlobal("fetch", fetch);

    const request = startAgentMessage({ message: "hello", locale: "en" });

    await expect(request.promise).rejects.toThrow("Worker unavailable");
  });
});

describe("write action confirmation", () => {
  const action = {
    action_id: "action-1",
    confirmation_token: "confirmation-secret",
  };

  it("sends an explicit confirmation with a stable idempotency key", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "confirmed",
      action_id: "action-1",
      idempotent_replay: false,
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);

    await confirmWriteAction(action, "write:stable-key");

    const [, options] = fetch.mock.calls[0];
    expect(options.headers["Idempotency-Key"]).toBe("write:stable-key");
    expect(JSON.parse(options.body)).toEqual({ confirmation_token: "confirmation-secret" });
  });

  it("rejects an action without sending an idempotency key", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "rejected",
      action_id: "action-1",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);

    await rejectWriteAction(action);

    const [, options] = fetch.mock.calls[0];
    expect(options.headers).not.toHaveProperty("Idempotency-Key");
  });
});
