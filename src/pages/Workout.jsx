import React, { useState } from "react";
import { Dumbbell, Home, Trees } from "lucide-react";
import { useLang } from "@/lib/i18n";
import GymGenerator from "@/components/GymGenerator";
import CollapsibleIdeas from "@/components/CollapsibleIdeas";
import { HOME_WORKOUTS, OUTDOOR_WORKOUTS, BLOGGERS } from "@/lib/workoutData";

const CATEGORIES = [
  { key: "gym", icon: Dumbbell },
  { key: "home", icon: Home },
  { key: "freshAir", icon: Trees },
];

export default function Workout() {
  const { t } = useLang();
  const [category, setCategory] = useState("gym");

  return (
    <div className="px-4 pt-6 pb-4 space-y-5">
      <header>
        <p className="text-[11px] uppercase tracking-[0.25em] text-accent font-display">Olympus</p>
        <h1 className="text-2xl font-heading mt-1">{t("workout_title")}</h1>
        <p className="text-sm text-muted-foreground mt-1">{t("workout_subtitle")}</p>
      </header>

      <div>
        <p className="text-xs font-medium text-muted-foreground mb-2">{t("workout_choose")}</p>
        <div className="grid grid-cols-3 gap-2">
          {CATEGORIES.map((c) => {
            const active = category === c.key;
            const Icon = c.icon;
            return (
              <button
                key={c.key}
                type="button"
                onClick={() => setCategory(c.key)}
                className={`flex flex-col items-center gap-1.5 rounded-2xl p-3 border-2 transition-colors ${active ? "border-primary bg-primary/5 text-primary" : "border-border bg-card text-muted-foreground hover:border-primary/40"}`}
              >
                <Icon className="w-5 h-5" strokeWidth={active ? 2.5 : 1.5} />
                <span className="text-xs font-medium">{t(`workout_${c.key}`)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {category === "gym" && <GymGenerator />}
      {category === "home" && <CollapsibleIdeas title={t("workout_home")} items={HOME_WORKOUTS} />}
      {category === "freshAir" && <CollapsibleIdeas title={t("workout_freshAir")} items={OUTDOOR_WORKOUTS} />}

      {/* Promo */}
      <div className="rounded-2xl border-2 border-accent/30 bg-accent/5 p-4 text-center">
        <p className="font-heading text-base">{t("workout_promo")}</p>
      </div>

      {/* Try something new */}
      <div className="space-y-2 pt-2">
        <h2 className="font-heading text-lg">{t("workout_blogNote")}</h2>
        <p className="text-sm text-muted-foreground leading-relaxed">{t("workout_calistDesc")}</p>
        {BLOGGERS.map((b) => (
          <div key={b.name} className="bg-card rounded-2xl border border-border p-3">
            <p className="text-sm font-medium">{b.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{t(b.noteKey)}</p>
            <div className="flex flex-wrap gap-2 mt-2">
              {b.links.map((l) => (
                <a
                  key={l.platform}
                  href={l.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-[11px] px-2.5 py-1 rounded-full border border-border bg-muted/50 hover:bg-accent/10 hover:text-accent hover:border-accent/30 transition-colors"
                >
                  {l.platform} · {l.handle}
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}