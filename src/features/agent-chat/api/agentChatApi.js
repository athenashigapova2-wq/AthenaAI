import { supabase } from "@/api/supabaseClient";

const AGENT_API_URL = import.meta.env.DEV
  ? "/agent-api"
  : (import.meta.env.VITE_AGENT_API_URL || "").replace(/\/$/, "");

const POLL_INTERVAL_MS = 750;
const JOB_TIMEOUT_MS = 5 * 60 * 1000;

const parseResponse = async (response) => {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.detail || data?.error || `Agent request failed (${response.status})`);
  }
  return data;
};

async function waitForJob(jobId, accessToken) {
  const deadline = Date.now() + JOB_TIMEOUT_MS;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
    const response = await fetch(`${AGENT_API_URL}/api/v1/agent/chat/jobs/${jobId}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const data = await parseResponse(response);
    if (data.status === "succeeded") return data;
    if (data.status === "failed") throw new Error(data.error || "Agent job failed");
  }
  throw new Error("Agent response timed out. Please try again.");
}

export async function sendAgentMessage({ conversationId, message, locale }) {
  if (!AGENT_API_URL) throw new Error("VITE_AGENT_API_URL is not configured");

  const { data: sessionData, error: sessionError } = await supabase.auth.getSession();
  const accessToken = sessionData.session?.access_token;
  if (sessionError || !accessToken) {
    throw new Error("Your session expired. Please sign in again.");
  }

  const response = await fetch(`${AGENT_API_URL}/api/v1/agent/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({ conversation_id: conversationId, message, locale }),
  });
  const data = await parseResponse(response);
  return data?.job_id ? waitForJob(data.job_id, accessToken) : data;
}

export function agentFetchErrorMessage(message) {
  return message === "Failed to fetch"
    ? `FastAPI is unavailable at ${AGENT_API_URL}. Check that Uvicorn is running.`
    : message;
}
