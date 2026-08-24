import { supabase } from "@/api/supabaseClient";

const AGENT_API_URL = import.meta.env.DEV
  ? "/agent-api"
  : (import.meta.env.VITE_AGENT_API_URL || "").replace(/\/$/, "");

const JOB_TIMEOUT_MS = 5 * 60 * 1000;

const parseResponse = async (response) => {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || data?.error || `Agent request failed (${response.status})`);
  }
  return data;
};

async function accessToken() {
  const { data, error } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  if (error || !token) throw new Error("Your session expired. Please sign in again.");
  return token;
}

function decodeEvent(block) {
  let event = "message";
  const data = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? { event, data: JSON.parse(data.join("\n")) } : null;
}

async function waitForJobEvents(jobId, token, signal, onProgress) {
  const response = await fetch(`${AGENT_API_URL}/api/v1/agent/chat/jobs/${jobId}/events`, {
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${token}`,
    },
    signal,
  });
  if (!response.ok || !response.body) return parseResponse(response);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const message = decodeEvent(block);
      if (!message) continue;
      onProgress?.({ stage: message.event, ...message.data });
      if (message.event === "completed") return message.data;
      if (message.event === "failed") throw new Error(message.data.error || "Agent job failed");
      if (message.event === "cancelled") throw new DOMException("Agent job cancelled", "AbortError");
    }
    if (done) break;
  }
  throw new Error("Agent event stream ended before completion.");
}

async function cancelJob(jobId, token) {
  if (!jobId || !token) return;
  await fetch(`${AGENT_API_URL}/api/v1/agent/chat/jobs/${jobId}/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  }).catch(() => null);
}

export function startAgentMessage({ conversationId, message, locale, onProgress }) {
  const controller = new AbortController();
  let jobId = null;
  let token = null;
  let cancelled = false;
  const timeout = globalThis.setTimeout(() => {
    cancelled = true;
    controller.abort("timeout");
    void cancelJob(jobId, token);
  }, JOB_TIMEOUT_MS);

  const promise = (async () => {
    if (!AGENT_API_URL) throw new Error("VITE_AGENT_API_URL is not configured");
    token = await accessToken();
    const response = await fetch(`${AGENT_API_URL}/api/v1/agent/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ conversation_id: conversationId, message, locale }),
      signal: controller.signal,
    });
    const accepted = await parseResponse(response);
    if (!accepted?.job_id) return accepted;
    jobId = accepted.job_id;
    onProgress?.({ stage: "queued", ...accepted });
    if (cancelled) {
      await cancelJob(jobId, token);
      throw new DOMException("Agent job cancelled", "AbortError");
    }
    return waitForJobEvents(jobId, token, controller.signal, onProgress);
  })().finally(() => globalThis.clearTimeout(timeout));

  return {
    promise,
    cancel: async () => {
      cancelled = true;
      controller.abort("cancelled");
      await cancelJob(jobId, token);
    },
  };
}

export async function sendAgentMessage(options) {
  return startAgentMessage(options).promise;
}

export function agentFetchErrorMessage(message) {
  return message === "Failed to fetch"
    ? `FastAPI is unavailable at ${AGENT_API_URL}. Check that Uvicorn is running.`
    : message;
}
