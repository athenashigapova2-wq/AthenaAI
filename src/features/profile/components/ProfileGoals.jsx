import { Calculator } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { GOALS } from "@/features/profile/model/profileOptions";

export default function ProfileGoals({ form, t, onGoalChange, onUpdate, onRecalculate }) {
  return (
    <>
      <div className="space-y-3 rounded-2xl border border-border bg-card p-4">
        <h2 className="font-heading text-sm font-semibold">{t("prof_goal")}</h2>
        <div className="grid grid-cols-2 gap-2">
          {GOALS.map((goal) => (
            <button
              key={goal.key}
              type="button"
              onClick={() => onGoalChange(goal.key)}
              className={`rounded-xl border-2 p-3 text-left transition-colors ${form.goal === goal.key ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40"}`}
            >
              <p className="font-heading text-sm">{t(goal.labelKey)}</p>
              <p className="text-[11px] text-muted-foreground">{t(goal.subKey)}</p>
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-4 rounded-2xl border border-border bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-heading text-sm font-semibold">{t("prof_dailyTargets")}</h2>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={onRecalculate}>
            <Calculator className="mr-1 h-3.5 w-3.5" /> {t("prof_recalc")}
          </Button>
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("prof_calories")}</Label>
          <Input type="number" className="h-9" value={form.calorie_target} onChange={(event) => onUpdate("calorie_target", event.target.value)} />
        </div>
        <div className="grid grid-cols-3 gap-3">
          {[
            ["protein_target_g", "prof_protein"],
            ["carb_target_g", "prof_carbs"],
            ["fat_target_g", "prof_fat"],
          ].map(([field, label]) => (
            <div key={field} className="space-y-1.5">
              <Label className="text-xs">{t(label)}</Label>
              <Input type="number" className="h-9" value={form[field]} onChange={(event) => onUpdate(field, event.target.value)} />
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
