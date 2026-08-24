import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ResponsiveSelect from "@/components/ResponsiveSelect";
import {
  DIETARY_PATTERNS,
  DIETARY_RESTRICTIONS,
} from "@/features/profile/model/profileOptions";

export default function ProfilePreferences({ form, t, onUpdate }) {
  const toggleRestriction = (restriction) => {
    const selected = form.dietary_restrictions || [];
    onUpdate(
      "dietary_restrictions",
      selected.includes(restriction)
        ? selected.filter((item) => item !== restriction)
        : [...selected, restriction],
    );
  };

  return (
    <div className="space-y-4 rounded-2xl border border-border bg-card p-4">
      <h2 className="font-heading text-sm font-semibold">{t("prof_preferences")}</h2>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("prof_budget")}</Label>
          <ResponsiveSelect value={form.budget} onValueChange={(value) => onUpdate("budget", value)} placeholder={t("prof_budget")} options={[
            { value: "low", label: t("budget_low") },
            { value: "medium", label: t("budget_medium") },
            { value: "high", label: t("budget_high") },
          ]} />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("prof_cooking")}</Label>
          <ResponsiveSelect value={form.cooking_skill} onValueChange={(value) => onUpdate("cooking_skill", value)} placeholder={t("prof_cooking")} options={[
            { value: "none", label: t("cook_none") },
            { value: "basic", label: t("cook_basic") },
            { value: "intermediate", label: t("cook_intermediate") },
            { value: "advanced", label: t("cook_advanced") },
          ]} />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs">{t("prof_dietPattern")}</Label>
        <ResponsiveSelect value={form.dietary_pattern} onValueChange={(value) => onUpdate("dietary_pattern", value)} placeholder={t("prof_dietPattern")} options={DIETARY_PATTERNS.map((value) => ({ value, label: t(`diet_${value}`) }))} />
      </div>
      <div className="space-y-2">
        <Label className="text-xs">{t("prof_dietRestrictions")}</Label>
        <div className="grid grid-cols-2 gap-2">
          {DIETARY_RESTRICTIONS.map((restriction) => {
            const selected = (form.dietary_restrictions || []).includes(restriction);
            return (
              <Button key={restriction} type="button" size="sm" variant={selected ? "default" : "outline"} onClick={() => toggleRestriction(restriction)}>
                {selected ? "✓ " : ""}{t(`restriction_${restriction}`)}
              </Button>
            );
          })}
        </div>
      </div>
      {[
        ["allergies", "prof_allergies", "prof_allergiesPh"],
        ["favorite_foods", "prof_favorite", "prof_favoritePh"],
        ["disliked_foods", "prof_disliked", "prof_dislikedPh"],
      ].map(([field, label, placeholder]) => (
        <div key={field} className="space-y-1.5">
          <Label className="text-xs">{t(label)}</Label>
          <Input className="h-9" placeholder={t(placeholder)} value={form[field]} onChange={(event) => onUpdate(field, event.target.value)} />
        </div>
      ))}
    </div>
  );
}
