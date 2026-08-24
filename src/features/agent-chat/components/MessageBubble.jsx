import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import {
  ChevronDown,
  ChevronRight,
  Check,
  Loader2,
  AlertCircle,
  Wrench,
} from "lucide-react";

function ToolCallDisplay({ toolCall }) {
  const [expanded, setExpanded] = useState(false);
  const status = toolCall.status;
  const projection = toolCall.display_projection || {};

  // If hide_details and details_redacted, only show the label
  if (projection.hide_details && projection.details_redacted) {
    const label =
      status === "failed" || status === "error"
        ? projection.error_label
        : ["pending", "running", "in_progress"].includes(status)
        ? projection.active_label
        : projection.label;
    return (
      <div className="flex items-center gap-1.5 mt-2 text-xs text-muted-foreground">
        <Wrench className="w-3 h-3" />
        <span>{label || toolCall.name}</span>
      </div>
    );
  }

  const isError =
    status === "failed" ||
    status === "error" ||
    (typeof toolCall.results === "string" && /error|failed/i.test(toolCall.results));

  let parsedArgs = toolCall.arguments_string;
  try {
    parsedArgs = JSON.parse(toolCall.arguments_string);
  } catch {
    // keep raw
  }

  let parsedResults = toolCall.results;
  if (typeof parsedResults === "string") {
    try {
      parsedResults = JSON.parse(parsedResults);
    } catch {
      // keep raw
    }
  }

  const statusIcon = isError ? (
    <AlertCircle className="w-3 h-3 text-destructive" />
  ) : status === "success" || status === "completed" ? (
    <Check className="w-3 h-3 text-primary" />
  ) : (
    <Loader2 className="w-3 h-3 animate-spin text-muted-foreground" />
  );

  const statusText =
    status === "success" || status === "completed"
      ? "done"
      : ["pending", "running", "in_progress"].includes(status)
      ? "running…"
      : "failed";

  return (
    <div className="mt-2 text-xs border border-border rounded-lg bg-muted/40 overflow-hidden">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center gap-1.5 w-full px-2.5 py-1.5 hover:bg-muted/60 transition-colors"
      >
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        {statusIcon}
        <span className="font-medium text-foreground">{toolCall.name}</span>
        <span className="text-muted-foreground">— {statusText}</span>
      </button>
      {expanded && (
        <div className="px-2.5 pb-2.5 space-y-2">
          {parsedArgs !== undefined && (
            <div>
              <p className="text-muted-foreground mb-0.5">Parameters:</p>
              <pre className="bg-background rounded p-2 overflow-x-auto text-[11px] leading-relaxed">
                {typeof parsedArgs === "string"
                  ? parsedArgs
                  : JSON.stringify(parsedArgs, null, 2)}
              </pre>
            </div>
          )}
          {parsedResults !== undefined && (
            <div>
              <p className="text-muted-foreground mb-0.5">Result:</p>
              <pre className="bg-background rounded p-2 overflow-x-auto text-[11px] leading-relaxed">
                {typeof parsedResults === "string"
                  ? parsedResults
                  : JSON.stringify(parsedResults, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 ${
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card border border-border"
        }`}
      >
        {message.content && (
          isUser ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="text-sm leading-relaxed prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          )
        )}
        {message.tool_calls?.filter((tc) => !/^read_/.test(tc.name || "")).map((tc, idx) => (
          <ToolCallDisplay key={idx} toolCall={tc} />
        ))}
      </div>
    </div>
  );
}