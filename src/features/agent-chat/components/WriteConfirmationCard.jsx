import { Check, ShieldCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";

const PREVIEW_LABELS = {
  name: "chat_writeFieldName",
  meal_type: "chat_writeFieldMealType",
  calories: "chat_writeFieldCalories",
  protein_g: "chat_writeFieldProtein",
  carbs_g: "chat_writeFieldCarbs",
  fat_g: "chat_writeFieldFat",
  day: "chat_writeFieldDate",
  date: "chat_writeFieldDate",
};

const PREVIEW_UNITS = {
  calories: " kcal",
  protein_g: " g",
  carbs_g: " g",
  fat_g: " g",
};

function readableLabel(key, t) {
  const translationKey = PREVIEW_LABELS[key];
  return translationKey ? t(translationKey) : key.replaceAll("_", " ");
}

function readableValue(key, value) {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return Object.values(value).join(", ");
  return `${value}${PREVIEW_UNITS[key] || ""}`;
}

export default function WriteConfirmationCard({ action, busy, error, t, onConfirm, onReject }) {
  if (!action) return null;
  const preview = Object.entries(action.preview || {});
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
      <p className="mt-3 text-xs font-medium">{t(`chat_writeAction_${action.tool_name}`)}</p>
      <dl className="mt-2 divide-y divide-border rounded-xl border border-border bg-background px-3">
        {preview.map(([key, value]) => (
          <div key={key} className="flex items-start justify-between gap-4 py-2 text-xs">
            <dt className="capitalize text-muted-foreground">{readableLabel(key, t)}</dt>
            <dd className="text-right font-medium text-foreground">{readableValue(key, value)}</dd>
          </div>
        ))}
      </dl>
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
