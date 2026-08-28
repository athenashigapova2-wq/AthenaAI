import { Loader2, Sparkles, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import MessageBubble from "@/features/agent-chat/components/MessageBubble";
import WriteConfirmationCard from "@/features/agent-chat/components/WriteConfirmationCard";

export default function ChatMessages({
  messages,
  sending,
  progress,
  suggestions,
  t,
  onSuggestion,
  onCancel,
  pendingWriteAction,
  confirmationBusy,
  confirmationError,
  onConfirmWrite,
  onRejectWrite,
  scrollRef,
}) {
  const visibleStage = ["queued", "running", "tool_call", "generating"].includes(progress?.stage)
    ? progress.stage
    : "generating";
  return (
    <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-y-contain px-4 py-4">
      {messages.length === 0 ? (
        <div className="flex h-full flex-col items-center justify-center px-6 text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-info">
            <Sparkles className="h-7 w-7 text-info-foreground" />
          </div>
          <h2 className="mb-1 font-heading font-semibold">{t("chat_emptyTitle")}</h2>
          <p className="mb-6 text-sm text-muted-foreground">{t("chat_emptyBody")}</p>
          <div className="w-full max-w-xs space-y-2">
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                onClick={() => onSuggestion(suggestion)}
                className="w-full rounded-xl border border-border bg-card px-3 py-2.5 text-left text-sm transition-colors hover:border-info-foreground/20 hover:bg-info hover:text-info-foreground"
              >
                {suggestion}
              </button>
            ))}
          </div>
          <Button onClick={() => onSuggestion(t("chat_consultPrompt"))} disabled={sending} className="mt-2 h-11 w-full max-w-xs rounded-xl text-sm">
            <Sparkles className="mr-1.5 h-4 w-4" />
            {t("chat_consult")}
          </Button>
        </div>
      ) : (
        messages.map((message, index) => <MessageBubble key={message.id || index} message={message} />)
      )}
      {sending && (
        <div className="flex justify-start">
          <div className="flex items-center gap-3 rounded-2xl border border-border bg-card px-3.5 py-2.5">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-xs text-muted-foreground">
              {t(`chat_progress_${visibleStage}`)}
            </span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              onClick={onCancel}
            >
              <Square className="h-3 w-3 fill-current" />
              {t("chat_cancel")}
            </Button>
          </div>
        </div>
      )}
      <WriteConfirmationCard
        action={pendingWriteAction}
        busy={confirmationBusy}
        error={confirmationError}
        t={t}
        onConfirm={onConfirmWrite}
        onReject={onRejectWrite}
      />
    </div>
  );
}
