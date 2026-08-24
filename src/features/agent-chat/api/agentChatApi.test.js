import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/supabaseClient", () => ({
  supabase: {
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "test-token" } },
        error: null,
      })),
    },
  },
}));

import { startAgentMessage } from "@/features/agent-chat/api/agentChatApi";

afterEach(() => {
  vi.unstubAllGlobals();
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
});
