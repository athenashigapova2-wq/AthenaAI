import { Check, ShieldCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";

export default function WriteConfirmationCard({ action, busy, error, t, onConfirm, onReject }) {
  if (!action) return null;
  return (
    <section
      aria-label={t("chat_writeConfirmTitle")}
      className="rounded-2xl border border-warning/40 bg-warning/10 p-4"
    >
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-warning-foreground" />
        <h3 className="font-heading text-sm font-semibold">{t("chat_writeConfirmTitle")}</h3>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{t("chat_writeConfirmBody")}</p>
      <p className="mt-3 text-xs font-medium">{action.tool_name}</p>
      <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-background p-2 text-[11px] leading-relaxed">
        {JSON.stringify(action.preview, null, 2)}
      </pre>
      {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
      <div className="mt-3 flex gap-2">
        <Button type="button" size="sm" disabled={busy} onClick={onConfirm}>
          <Check className="mr-1 h-4 w-4" />
          {t("chat_writeConfirm")}
        </Button>
        <Button type="button" size="sm" variant="outline" disabled={busy} onClick={onReject}>
          <X className="mr-1 h-4 w-4" />
          {t("chat_writeReject")}
        </Button>
      </div>
    </section>
  );
}
