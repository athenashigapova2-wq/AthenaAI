import React, { useState } from "react";
import { toLocalDateStr } from "@/lib/utils";
import { entities } from '@/lib/entities';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ResponsiveSelect from "@/components/ResponsiveSelect";
import { ArrowRight, ArrowLeft, Loader2 } from "lucide-react";
import { useLang } from "@/lib/i18n";

const STEPS = ["goal", "body", "nutrition", "preferences"];

const GOALS = [
  { value: "lose_weight", labelKey: "onb_goalLose", emoji: "🔥" },
  { value: "maintain", labelKey: "onb_goalMaintain", emoji: "⚖️" },
  { value: "gain_muscle", labelKey: "onb_goalGain", emoji: "💪" },
  { value: "recomp", labelKey: "onb_goalRecomp", emoji: "🔄" },
];

function calculateDefaults(weight, goal) {
  let cals, protMult;
  switch (goal) {
    case "lose_weight": cals = Math.round(weight * 24); protMult = 2.0; break;
    case "gain_muscle": cals = Math.round(weight * 33); protMult = 2.2; break;
    case "recomp": cals = Math.round(weight * 28); protMult = 2.2; break;
    default: cals = Math.round(weight * 28); protMult = 1.8;
  }
  const protein = Math.round(weight * protMult);
  const fat = Math.round(weight * 0.9);
  const carbCals = cals - protein * 4 - fat * 9;
  const carbs = Math.max(Math.round(carbCals / 4), 50);
  return { calorie_target: cals, protein_target_g: protein, carb_target_g: carbs, fat_target_g: fat };
}

export default function Onboarding({ onComplete }) {
  const { t } = useLang();
  const [step, setStep] = useState(0);
  const [saving, setSaving] = useState(false);
  const [data, setData] = useState({
    goal: "", sex: "male", age: "", height_cm: "", weight_kg: "",
    calorie_target: "", protein_target_g: "", carb_target_g: "", fat_target_g: "",
    budget: "medium", cooking_skill: "basic", allergies: [], disliked_foods: [], favorite_foods: [],
    cycle_tracking_enabled: false,
  });

  const update = (field, value) => setData((d) => ({ ...d, [field]: value }));

  const goNext = () => {
    if (step === 1 && data.weight_kg && data.goal) {
      const defaults = calculateDefaults(Number(data.weight_kg), data.goal);
      setData((d) => ({
        ...d,
        calorie_target: d.calorie_target || defaults.calorie_target,
        protein_target_g: d.protein_target_g || defaults.protein_target_g,
        carb_target_g: d.carb_target_g || defaults.carb_target_g,
        fat_target_g: d.fat_target_g || defaults.fat_target_g,
      }));
    }
    setStep((s) => Math.min(s + 1, STEPS.length - 1));
  };

  const goBack = () => setStep((s) => Math.max(s - 1, 0));

  const handleSave = async () => {
    setSaving(true);
    const payload = {
      ...data,
      age: Number(data.age) || undefined, height_cm: Number(data.height_cm) || undefined, weight_kg: Number(data.weight_kg) || undefined,
      calorie_target: Number(data.calorie_target), protein_target_g: Number(data.protein_target_g),
      carb_target_g: Number(data.carb_target_g), fat_target_g: Number(data.fat_target_g),
      onboarding_complete: true,
      cycle_tracking_offered: data.sex === "female", // уже спросили здесь — не дублируем вопрос в профиле
    };
    await entities.UserProfile.create(payload);
    if (data.weight_kg) {
      await entities.WeightLog.create({ weight_kg: Number(data.weight_kg), date: toLocalDateStr() });
    }
    setSaving(false);
    onComplete();
  };

  const canProceed = () => {
    if (step === 0) return !!data.goal;
    if (step === 1) return data.weight_kg && data.height_cm;
    if (step === 2) return data.calorie_target && data.protein_target_g && data.carb_target_g && data.fat_target_g;
    return true;
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8">
          <div className="flex items-center gap-1.5 mb-6">
            {STEPS.map((_, i) => (
              <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${i <= step ? "bg-primary" : "bg-muted"}`} />
            ))}
          </div>
          <h1 className="text-2xl font-bold font-heading">
            {step === 0 && t("onb_goalTitle")}
            {step === 1 && t("onb_bodyTitle")}
            {step === 2 && t("onb_nutritionTitle")}
            {step === 3 && t("onb_prefTitle")}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {step === 0 && t("onb_goalSub")}
            {step === 1 && t("onb_bodySub")}
            {step === 2 && t("onb_nutritionSub")}
            {step === 3 && t("onb_prefSub")}
          </p>
        </div>

        {step === 0 && (
          <div className="space-y-3">
            {GOALS.map((g) => (
              <button
                key={g.value}
                onClick={() => update("goal", g.value)}
                className={`w-full flex items-center gap-3 p-4 rounded-xl border transition-all text-left ${
                  data.goal === g.value ? "border-primary bg-accent" : "border-border bg-card hover:border-primary/40"
                }`}
              >
                <span className="text-2xl">{g.emoji}</span>
                <span className="font-medium">{t(g.labelKey)}</span>
              </button>
            ))}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t("onb_sex")}</Label>
                <ResponsiveSelect value={data.sex} onValueChange={(v) => update("sex", v)} placeholder={t("onb_sex")}
                  options={[
                    { value: "male", label: t("calc_male") },
                    { value: "female", label: t("calc_female") },
                    { value: "other", label: t("calc_other") },
                  ]}
                />
              </div>
              <div className="space-y-2">
                <Label>{t("onb_age")}</Label>
                <Input type="number" placeholder="25" value={data.age} onChange={(e) => update("age", e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t("onb_height")}</Label>
                <Input type="number" placeholder="175" value={data.height_cm} onChange={(e) => update("height_cm", e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>{t("onb_weight")}</Label>
                <Input type="number" placeholder="75" value={data.weight_kg} onChange={(e) => update("weight_kg", e.target.value)} />
              </div>
            </div>

            {data.sex === "female" && (
              <div className="p-3 bg-secondary rounded-xl space-y-2">
                <Label>Хотите включить отслеживание менструального цикла?</Label>
                <p className="text-xs text-muted-foreground">
                  Полностью приватно — видно только Вам. Можно включить или отключить позже в профиле.
                </p>
                <div className="flex gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant="default"
                    onClick={() => update("cycle_tracking_enabled", true)}
                  >
                    {data.cycle_tracking_enabled && "✓ "}Да
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => update("cycle_tracking_enabled", false)}
                  >
                    {!data.cycle_tracking_enabled && "✓ "}Нет
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t("onb_calories")}</Label>
              <Input type="number" value={data.calorie_target} onChange={(e) => update("calorie_target", e.target.value)} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-2"><Label>{t("onb_protein")}</Label><Input type="number" value={data.protein_target_g} onChange={(e) => update("protein_target_g", e.target.value)} /></div>
              <div className="space-y-2"><Label>{t("onb_carbs")}</Label><Input type="number" value={data.carb_target_g} onChange={(e) => update("carb_target_g", e.target.value)} /></div>
              <div className="space-y-2"><Label>{t("onb_fat")}</Label><Input type="number" value={data.fat_target_g} onChange={(e) => update("fat_target_g", e.target.value)} /></div>
            </div>
            <p className="text-xs text-muted-foreground">{t("onb_autoNote")}</p>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>{t("onb_budget")}</Label>
                <ResponsiveSelect value={data.budget} onValueChange={(v) => update("budget", v)} placeholder={t("onb_budget")}
                  options={[
                    { value: "low", label: t("budget_low") },
                    { value: "medium", label: t("budget_medium") },
                    { value: "high", label: t("budget_high") },
                  ]}
                />
              </div>
              <div className="space-y-2">
                <Label>{t("onb_cooking")}</Label>
                <ResponsiveSelect value={data.cooking_skill} onValueChange={(v) => update("cooking_skill", v)} placeholder={t("onb_cooking")}
                  options={[
                    { value: "none", label: t("cook_none") },
                    { value: "basic", label: t("cook_basic") },
                    { value: "intermediate", label: t("cook_intermediate") },
                    { value: "advanced", label: t("cook_advanced") },
                  ]}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label>{t("onb_allergies")}</Label>
              <Input placeholder={t("prof_allergiesPh")} value={data.allergies.join(", ")} onChange={(e) => update("allergies", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
            </div>
            <div className="space-y-2">
              <Label>{t("onb_favorite")}</Label>
              <Input placeholder={t("prof_favoritePh")} value={data.favorite_foods.join(", ")} onChange={(e) => update("favorite_foods", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
            </div>
            <div className="space-y-2">
              <Label>{t("onb_disliked")}</Label>
              <Input placeholder={t("prof_dislikedPh")} value={data.disliked_foods.join(", ")} onChange={(e) => update("disliked_foods", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
            </div>
          </div>
        )}

        <div className="flex gap-3 mt-8">
          {step > 0 && (
            <Button variant="outline" className="h-12" onClick={goBack}>
              <ArrowLeft className="w-4 h-4 mr-1" /> {t("onb_back")}
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button className="flex-1 h-12" onClick={goNext} disabled={!canProceed()}>
              {t("onb_continue")} <ArrowRight className="w-4 h-4 ml-1" />
            </Button>
          ) : (
            <Button className="flex-1 h-12" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
              {saving ? t("onb_settingUp") : t("onb_start")}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
