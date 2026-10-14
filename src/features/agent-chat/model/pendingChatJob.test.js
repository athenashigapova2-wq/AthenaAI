import { afterEach, describe, expect, it } from "vitest";

import {
  clearPendingChatJob,
  loadPendingChatJob,
  savePendingChatJob,
} from "@/features/agent-chat/model/pendingChatJob";

afterEach(() => localStorage.clear());

describe("pending chat job persistence", () => {
  it("survives a page lifecycle and is scoped to the authenticated user", () => {
    const pending = {
      requestId: "request-1",
      jobId: "job-1",
      message: "hello",
      locale: "en",
      conversationId: null,
    };

    savePendingChatJob("user-1", pending);

    expect(loadPendingChatJob("user-1")).toEqual(pending);
    expect(loadPendingChatJob("user-2")).toBeNull();
  });

  it("does not clear a newer request with an older completion", () => {
    savePendingChatJob("user-1", { requestId: "new-request", jobId: "job-2" });

    clearPendingChatJob("user-1", "old-request");

    expect(loadPendingChatJob("user-1")).toMatchObject({ requestId: "new-request" });
  });
});
