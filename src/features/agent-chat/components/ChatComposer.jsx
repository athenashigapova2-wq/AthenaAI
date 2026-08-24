import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function ChatComposer({ input, sending, error, t, textareaRef, onChange, onSend }) {
  return (
    <div className="border-t border-border bg-card/80 px-4 py-3 backdrop-blur-sm">
      {error && (
        <div role="alert" className="mb-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
          {error}
        </div>
      )}
      <div className="flex items-end gap-2">
        <textarea
          ref={textareaRef}
          placeholder={t("chat_placeholder")}
          value={input}
          onChange={(event) => {
            onChange(event.target.value);
            event.target.style.height = "auto";
            event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          rows={1}
          className="max-h-[120px] min-h-[44px] flex-1 resize-none rounded-xl border border-input bg-background px-3 py-2.5 text-sm leading-relaxed focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          disabled={sending}
        />
        <Button className="h-11 w-11 shrink-0 rounded-xl p-0" onClick={onSend} disabled={!input.trim() || sending}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
