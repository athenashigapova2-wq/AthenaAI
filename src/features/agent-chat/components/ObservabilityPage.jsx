import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  RefreshCw,
  Repeat2,
  Route,
  Star,
  Wrench,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { useAuth } from "@/lib/AuthContext";
import {
  OBSERVABILITY_PERIODS,
  buildRouteBreakdown,
  buildRunTimeline,
  fetchAgentObservability,
  summarizeAgentObservability,
} from "@/lib/agentObservability";

const timelineConfig = {
  succeeded: { label: "Succeeded", color: "hsl(var(--chart-1))" },
  failed: { label: "Failed", color: "hsl(var(--chart-3))" },
};

const routeConfig = {
  count: { label: "Runs", color: "hsl(var(--chart-2))" },
};

const number = new Intl.NumberFormat();

const formatLatency = (value) => {
  const milliseconds = Number(value || 0);
  if (milliseconds < 1_000) return `${milliseconds} ms`;
  return `${(milliseconds / 1_000).toFixed(milliseconds < 10_000 ? 1 : 0)} s`;
};

const formatDate = (value) =>
  new Date(value).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

const statusVariant = (status) => {
  if (status === "failed") return "destructive";
  if (status === "succeeded") return "default";
  return "secondary";
};

function MetricCard({ icon: Icon, label, value, detail }) {
  return (
    <Card className="shadow-sm">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="mt-1 font-heading text-2xl font-semibold tabular-nums">{value}</p>
            {detail && <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>}
          </div>
          <div className="rounded-xl bg-info p-2 text-info-foreground">
            <Icon className="h-4 w-4" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function JsonPreview({ value }) {
  if (value === null || value === undefined) return null;
  return (
    <pre className="max-h-44 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-2 text-[10px] leading-relaxed">
      {typeof value === "string" ? value : JSON.stringify(value, null, 2)}
    </pre>
  );
}

function TraceDetail({ run }) {
  if (!run) return null;

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">Trace {run.id.slice(0, 8)}</CardTitle>
            <CardDescription className="mt-1 font-mono text-[10px]">{run.id}</CardDescription>
          </div>
          <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 p-4">
        <div className="grid grid-cols-2 gap-3 text-xs">
          <div><span className="text-muted-foreground">Route</span><p className="font-medium">{run.route}</p></div>
          <div><span className="text-muted-foreground">Resolution</span><p className="font-medium">{run.resolution_mode}</p></div>
          <div><span className="text-muted-foreground">Latency</span><p className="font-medium">{formatLatency(run.latency_ms)}</p></div>
          <div><span className="text-muted-foreground">Tokens</span><p className="font-medium">{number.format(run.total_tokens || 0)}</p></div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Input</p>
          <p className="whitespace-pre-wrap rounded-lg border bg-background p-3 text-xs">{run.input_text}</p>
          {run.output_text && (
            <>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Output</p>
              <p className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border bg-background p-3 text-xs">{run.output_text}</p>
            </>
          )}
          {run.error_message && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
              {run.error_message}
            </p>
          )}
        </div>

        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">LLM attempts ({run.llm_calls.length})</h3>
          </div>
          {run.llm_calls.length === 0 ? (
            <p className="text-xs text-muted-foreground">No LLM attempts recorded.</p>
          ) : run.llm_calls.map((call) => (
            <div key={call.id} className="space-y-2 rounded-xl border p-3 text-xs">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={statusVariant(call.status)}>attempt {call.attempt_number}</Badge>
                <span className="font-medium">{call.node_name}.{call.purpose}</span>
                <span className="ml-auto text-muted-foreground">{formatLatency(call.latency_ms)}</span>
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                <span>{call.model_name}</span>
                <span>{call.requested_model_tier} → {call.model_tier}</span>
                <span>{number.format(call.total_tokens || 0)} tokens</span>
              </div>
              <p><span className="text-muted-foreground">Rule:</span> {call.routing_rule}</p>
              <p><span className="text-muted-foreground">Reason:</span> {call.selection_reason}</p>
              {call.retry_reason && <p className="text-amber-700 dark:text-amber-300">Retry: {call.retry_reason}</p>}
              {call.fallback_reason && <p className="text-amber-700 dark:text-amber-300">Fallback: {call.fallback_reason}</p>}
              {call.error_message && <p className="text-destructive">{call.error_message}</p>}
            </div>
          ))}
        </section>

        <section className="space-y-2">
          <div className="flex items-center gap-2">
            <Wrench className="h-4 w-4 text-primary" />
            <h3 className="text-sm font-semibold">Tool calls ({run.tool_calls.length})</h3>
          </div>
          {run.tool_calls.length === 0 ? (
            <p className="text-xs text-muted-foreground">No tool calls recorded.</p>
          ) : run.tool_calls.map((call) => (
            <details key={call.id} className="rounded-xl border p-3 text-xs">
              <summary className="cursor-pointer list-none font-medium">
                <span className="mr-2">step {call.tool_step}</span>
                {call.tool_name}
                <Badge className="ml-2" variant={statusVariant(call.status)}>{call.status}</Badge>
                <span className="float-right text-muted-foreground">{formatLatency(call.latency_ms)}</span>
              </summary>
              <div className="mt-3 space-y-2">
                <p className="text-muted-foreground">Arguments</p>
                <JsonPreview value={call.tool_args} />
                {call.tool_result !== null && <p className="text-muted-foreground">Result</p>}
                <JsonPreview value={call.tool_result} />
                {call.error_message && <p className="text-destructive">{call.error_message}</p>}
              </div>
            </details>
          ))}
        </section>
      </CardContent>
    </Card>
  );
}

export default function Observability() {
  const { user } = useAuth();
  const [hours, setHours] = useState(24 * 7);
  const [runs, setRuns] = useState([]);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!user?.id) return;
    setLoading(true);
    setError("");
    try {
      const nextRuns = await fetchAgentObservability({ userId: user.id, hours });
      setRuns(nextRuns);
      setSelectedRunId((current) =>
        nextRuns.some((run) => run.id === current) ? current : nextRuns[0]?.id || null,
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load traces");
    } finally {
      setLoading(false);
    }
  }, [hours, user?.id]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = useMemo(() => summarizeAgentObservability(runs), [runs]);
  const timeline = useMemo(() => buildRunTimeline(runs), [runs]);
  const routes = useMemo(() => buildRouteBreakdown(runs), [runs]);
  const selectedRun = runs.find((run) => run.id === selectedRunId) || null;

  return (
    <div className="space-y-5 px-4 py-5">
      <header className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-primary">
              <Activity className="h-5 w-5" />
              <span className="font-display text-xs font-semibold uppercase tracking-[0.18em]">Observability</span>
            </div>
            <h1 className="mt-1 font-heading text-2xl font-bold">Agent traces</h1>
            <p className="mt-1 text-xs text-muted-foreground">Your runs, provider attempts, tools and routing decisions.</p>
          </div>
          <Button variant="outline" size="icon" onClick={load} disabled={loading} aria-label="Refresh traces">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
        <div className="flex rounded-xl bg-muted p-1">
          {OBSERVABILITY_PERIODS.map((period) => (
            <button
              key={period.hours}
              onClick={() => setHours(period.hours)}
              className={`flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                hours === period.hours ? "bg-card text-foreground shadow-sm" : "text-muted-foreground"
              }`}
            >
              {period.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Could not load observability data</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3">
        <MetricCard icon={Activity} label="Runs" value={number.format(summary.runs)} detail={`${summary.running} still running`} />
        <MetricCard icon={CheckCircle2} label="Success rate" value={`${summary.successRate}%`} detail={`${summary.succeeded} succeeded · ${summary.failed} failed`} />
        <MetricCard icon={Clock3} label="P95 latency" value={formatLatency(summary.p95LatencyMs)} detail={`P50 ${formatLatency(summary.p50LatencyMs)}`} />
        <MetricCard icon={Bot} label="LLM attempts" value={number.format(summary.llmAttempts)} detail={`${summary.failedLlmAttempts} failed · ${summary.tokenCoverage}% token coverage`} />
        <MetricCard icon={Repeat2} label="Retries / fallbacks" value={`${summary.retryAttempts} / ${summary.fallbackAttempts}`} detail="Actual provider attempts" />
        <MetricCard icon={Wrench} label="Tool calls" value={number.format(summary.toolCalls)} detail={`${summary.failedToolCalls} failed`} />
        <MetricCard icon={Database} label="Total tokens" value={number.format(summary.totalTokens)} detail={`${summary.runs} runs loaded`} />
        <MetricCard icon={Star} label="Feedback" value={summary.averageRating === null ? "—" : `${summary.averageRating.toFixed(1)}/5`} detail={`${summary.feedbackCount} ratings`} />
      </div>

      {loading && runs.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Loading traces…
        </div>
      ) : runs.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center px-6 py-12 text-center">
            <Activity className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="font-medium">No traces in this period</p>
            <p className="mt-1 text-xs text-muted-foreground">Send a message to Athena, then refresh this dashboard.</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-sm">Runs over time</CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-0">
              <ChartContainer config={timelineConfig} className="h-48 w-full">
                <AreaChart data={timeline} margin={{ left: -24, right: 6, top: 12 }}>
                  <CartesianGrid vertical={false} />
                  <XAxis dataKey="date" tickLine={false} axisLine={false} fontSize={10} />
                  <YAxis allowDecimals={false} tickLine={false} axisLine={false} fontSize={10} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Area type="monotone" dataKey="succeeded" stackId="runs" stroke="var(--color-succeeded)" fill="var(--color-succeeded)" fillOpacity={0.35} />
                  <Area type="monotone" dataKey="failed" stackId="runs" stroke="var(--color-failed)" fill="var(--color-failed)" fillOpacity={0.35} />
                </AreaChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-2 text-sm"><Route className="h-4 w-4" /> Routes</CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-0">
              <ChartContainer config={routeConfig} className="h-40 w-full">
                <BarChart data={routes} layout="vertical" margin={{ left: 4, right: 12 }}>
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" hide />
                  <YAxis dataKey="route" type="category" tickLine={false} axisLine={false} width={72} fontSize={10} />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Bar dataKey="count" fill="var(--color-count)" radius={5} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="text-sm">Recent runs</CardTitle>
              <CardDescription className="text-xs">Up to 100 runs in the selected period.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 p-3">
              {runs.map((run) => (
                <button
                  key={run.id}
                  onClick={() => setSelectedRunId(run.id)}
                  className={`w-full rounded-xl border p-3 text-left transition-colors ${
                    selectedRunId === run.id ? "border-primary bg-info/50" : "bg-card hover:bg-muted/60"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
                    <span className="text-xs font-semibold capitalize">{run.route}</span>
                    <span className="ml-auto text-[10px] text-muted-foreground">{formatDate(run.created_at)}</span>
                  </div>
                  <p className="mt-2 truncate text-xs">{run.input_text}</p>
                  <div className="mt-2 flex gap-3 text-[10px] text-muted-foreground">
                    <span>{formatLatency(run.latency_ms)}</span>
                    <span>{run.llm_calls.length} LLM</span>
                    <span>{run.tool_calls.length} tools</span>
                    <span>{number.format(run.total_tokens || 0)} tokens</span>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>

          <TraceDetail run={selectedRun} />
        </>
      )}
    </div>
  );
}
