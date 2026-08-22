import { supabase } from "@/api/supabaseClient";

const RUN_COLUMNS = [
  "id",
  "user_id",
  "conversation_id",
  "route",
  "model_provider",
  "model_name",
  "input_text",
  "output_text",
  "status",
  "error_message",
  "latency_ms",
  "resolution_mode",
  "baseline_version",
  "llm_call_count",
  "token_accounted_call_count",
  "input_tokens",
  "output_tokens",
  "cached_input_tokens",
  "total_tokens",
  "tool_step_count",
  "tool_call_count",
  "created_at",
  "completed_at",
].join(",");

const LLM_COLUMNS = [
  "id",
  "run_id",
  "invocation_id",
  "attempt_number",
  "node_name",
  "purpose",
  "model_provider",
  "model_name",
  "requested_model_tier",
  "model_tier",
  "routing_rule",
  "selection_reason",
  "is_fallback",
  "fallback_reason",
  "retry_reason",
  "status",
  "token_usage_available",
  "input_tokens",
  "output_tokens",
  "cached_input_tokens",
  "total_tokens",
  "latency_ms",
  "error_message",
  "created_at",
  "completed_at",
].join(",");

const TOOL_COLUMNS = [
  "id",
  "run_id",
  "tool_name",
  "tool_step",
  "tool_args",
  "tool_result",
  "status",
  "error_message",
  "latency_ms",
  "created_at",
  "completed_at",
].join(",");

export const OBSERVABILITY_PERIODS = [
  { hours: 24, label: "24h" },
  { hours: 24 * 7, label: "7d" },
  { hours: 24 * 30, label: "30d" },
];

const groupByRun = (rows) => {
  const grouped = new Map();
  for (const row of rows || []) {
    const current = grouped.get(row.run_id) || [];
    current.push(row);
    grouped.set(row.run_id, current);
  }
  return grouped;
};

const ensureResponse = (response, tableName) => {
  if (response.error) {
    throw new Error(`${tableName}: ${response.error.message}`);
  }
  return response.data || [];
};

export async function fetchAgentObservability({ userId, hours, limit = 100 }) {
  if (!userId) return [];

  const since = new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();
  const runsResponse = await supabase
    .from("agent_runs")
    .select(RUN_COLUMNS)
    .eq("user_id", userId)
    .gte("created_at", since)
    .order("created_at", { ascending: false })
    .limit(limit);
  const runs = ensureResponse(runsResponse, "agent_runs");
  if (!runs.length) return [];

  const runIds = runs.map((run) => run.id);
  const [llmResponse, toolResponse, feedbackResponse] = await Promise.all([
    supabase
      .from("agent_llm_calls")
      .select(LLM_COLUMNS)
      .in("run_id", runIds)
      .order("created_at", { ascending: true }),
    supabase
      .from("agent_tool_calls")
      .select(TOOL_COLUMNS)
      .in("run_id", runIds)
      .order("created_at", { ascending: true }),
    supabase
      .from("agent_feedback")
      .select("id,run_id,rating,comment,created_at")
      .in("run_id", runIds),
  ]);

  const llmByRun = groupByRun(ensureResponse(llmResponse, "agent_llm_calls"));
  const toolsByRun = groupByRun(ensureResponse(toolResponse, "agent_tool_calls"));
  const feedbackByRun = groupByRun(ensureResponse(feedbackResponse, "agent_feedback"));

  return runs.map((run) => ({
    ...run,
    llm_calls: llmByRun.get(run.id) || [],
    tool_calls: toolsByRun.get(run.id) || [],
    feedback: feedbackByRun.get(run.id)?.[0] || null,
  }));
}

const percentile = (values, quantile) => {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(sorted.length - 1, Math.ceil(sorted.length * quantile) - 1);
  return sorted[Math.max(0, index)];
};

export function summarizeAgentObservability(runs) {
  const llmCalls = runs.flatMap((run) => run.llm_calls || []);
  const toolCalls = runs.flatMap((run) => run.tool_calls || []);
  const completedRuns = runs.filter((run) => run.status !== "started");
  const successfulRuns = runs.filter((run) => run.status === "succeeded");
  const latencies = completedRuns
    .map((run) => Number(run.latency_ms))
    .filter((value) => Number.isFinite(value) && value >= 0);
  const feedback = runs.map((run) => run.feedback).filter(Boolean);
  const totalTokens = runs.reduce((sum, run) => sum + Number(run.total_tokens || 0), 0);
  const accountedCalls = runs.reduce(
    (sum, run) => sum + Number(run.token_accounted_call_count || 0),
    0,
  );

  return {
    runs: runs.length,
    succeeded: successfulRuns.length,
    failed: runs.filter((run) => run.status === "failed").length,
    running: runs.filter((run) => run.status === "started").length,
    successRate: completedRuns.length
      ? Math.round((successfulRuns.length / completedRuns.length) * 100)
      : 0,
    p50LatencyMs: percentile(latencies, 0.5),
    p95LatencyMs: percentile(latencies, 0.95),
    llmAttempts: llmCalls.length,
    failedLlmAttempts: llmCalls.filter((call) => call.status === "failed").length,
    retryAttempts: llmCalls.filter((call) => Number(call.attempt_number) > 1).length,
    fallbackAttempts: llmCalls.filter((call) => call.is_fallback).length,
    toolCalls: toolCalls.length,
    failedToolCalls: toolCalls.filter((call) => call.status === "failed").length,
    totalTokens,
    tokenCoverage: llmCalls.length ? Math.round((accountedCalls / llmCalls.length) * 100) : 0,
    feedbackCount: feedback.length,
    averageRating: feedback.length
      ? feedback.reduce((sum, item) => sum + Number(item.rating), 0) / feedback.length
      : null,
  };
}

export function buildRunTimeline(runs) {
  const buckets = new Map();
  for (const run of runs) {
    const date = new Date(run.created_at);
    const key = date.toISOString().slice(0, 10);
    const bucket = buckets.get(key) || {
      key,
      label: date.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
      succeeded: 0,
      failed: 0,
      running: 0,
      latencyTotal: 0,
      latencyCount: 0,
    };
    bucket[run.status] += 1;
    if (Number.isFinite(Number(run.latency_ms))) {
      bucket.latencyTotal += Number(run.latency_ms);
      bucket.latencyCount += 1;
    }
    buckets.set(key, bucket);
  }
  return [...buckets.values()]
    .sort((a, b) => a.key.localeCompare(b.key))
    .map((bucket) => ({
      date: bucket.label,
      succeeded: bucket.succeeded,
      failed: bucket.failed,
      running: bucket.running,
      latency: bucket.latencyCount
        ? Math.round(bucket.latencyTotal / bucket.latencyCount)
        : 0,
    }));
}

export function buildRouteBreakdown(runs) {
  const counts = new Map();
  for (const run of runs) counts.set(run.route, (counts.get(run.route) || 0) + 1);
  return [...counts.entries()]
    .map(([route, count]) => ({ route, count }))
    .sort((a, b) => b.count - a.count);
}
