import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useLang } from "@/lib/i18n";

export default function CollapsibleIdeas({ title, items }) {
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between rounded-2xl border border-primary/20 bg-gradient-to-r from-primary/5 to-accent/5 p-4 hover:from-primary/10 hover:to-accent/10 hover:border-primary/40 hover:shadow-sm transition-all"
      >
        <span className="flex items-center gap-2.5 font-heading text-sm">
          <span className="w-1.5 h-6 rounded-full bg-accent" />
          {title}
        </span>
        <span className="text-xs font-medium text-accent flex items-center gap-1">
          {open ? t("workout_seeLess") : t("workout_seeSuggestions")}
          <ChevronDown className={`w-4 h-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </span>
      </button>
      {open && (
        <div className="space-y-2">
          {items.map((w) => (
            <div key={w.name} className="bg-card rounded-2xl border border-border p-3">
              <p className="text-sm font-medium">{w.name}</p>
              <ul className="mt-1.5 space-y-1">
                {w.exercises.map((ex, i) => (
                  <li key={i} className="text-xs text-muted-foreground flex gap-1.5">
                    <span className="text-accent">•</span>{ex}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}