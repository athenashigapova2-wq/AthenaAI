import React, { useState, useEffect, useCallback } from "react";
import { entities } from '@/lib/entities';
import { invokeAthenaTask } from '@/lib/athenaTasks';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Calculator, HeartPulse, Save, AlertTriangle, Pencil, Check } from "lucide-react";
import ResponsiveSelect from "@/components/ResponsiveSelect";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useLang } from "@/lib/i18n";
import { toast } from "@/components/ui/use-toast";
import { ACTIVITY_OPTIONS, ACTIVITY_FACTOR, stepsToActivity, round, macrosFor, VARIANTS } from "@/lib/macroCalc";

export default function RecalcMacrosDialog({ open, onOpenChange, profile, onApplied }) {
  const { t, lang } = useLang();
  const [weight, setWeight] = useState("");
  const [height, setHeight] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("male");
  const [activity, setActivity] = useState("moderate");
  const [steps, setSteps] = useState("");
  const [healthIssues, setHealthIssues] = useState("");
  const [result, setResult] = useState(null);
  const [research, setResearch] = useState(null);
  const [applied, setApplied] = useState(false);
  const [selectedKey, setSelectedKey] = useState("maintenance");
  const [manualCal, setManualCal] = useState(null);
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !profile) return;
    setWeight(profile.weight_kg ? String(profile.weight_kg) : "");
    setHeight(profile.height_cm ? String(profile.height_cm) : "");
    setAge(profile.age ? String(profile.age) : "");
    setSex(profile.sex || "male");
    setActivity("moderate");
    setSteps("");
    setHealthIssues("");
    setResult(null);
    setResearch(null);
    setApplied(false);
    setSelectedKey("maintenance");
    setManualCal(null);
    setEditing(false);
  }, [open, profile]);

  const onSteps = (v) => {
    setSteps(v);
    const s = parseInt(v);
    if (s > 0) setActivity(stepsToActivity(s));
  };

  const calculate = useCallback(async () => {
    const w = parseFloat(weight);
    const h = parseFloat(height);
    const a = parseFloat(age);
    if (!w || !h || !a || !sex) {
      toast({ title: t("calc_fillWarn"), variant: "destructive" });
      return;
    }
    setLoading(true);
    setResearch(null);
    setApplied(false);
    setManualCal(null);

    const bmrMale = 10 * w + 6.25 * h - 5 * a + 5;
    const bmrFemale = 10 * w + 6.25 * h - 5 * a - 161;
    const bmr = sex === "male" ? bmrMale : sex === "female" ? bmrFemale : (bmrMale + bmrFemale) / 2;
    const tdee = bmr * (ACTIVITY_FACTOR[activity] || 1.55);
    setResult({ bmr: round(bmr), tdee: round(tdee) });

    const issues = healthIssues.trim();
    if (issues) {
      try {
        const res = await invokeAthenaTask('health_macro_adjustment', {
          baseline_tdee: round(tdee),
          sex,
          age: a,
          weight_kg: w,
          height_cm: h,
          activity,
          health_issues: issues,
          language: lang,
        });
        setResearch(res);
      } catch {
        toast({ title: t("calc_researchFail"), description: t("calc_showingStandard"), variant: "destructive" });
      }
    }
    setLoading(false);
  }, [weight, height, age, sex, activity, healthIssues, t, lang]);

  const w = parseFloat(weight) || 0;
  const variant = VARIANTS.find((v) => v.key === selectedKey);
  const selectedCal = manualCal != null ? manualCal : result ? result.tdee + variant.delta : 0;
  const computedMacros = macrosFor(Math.max(selectedCal, 0), w);
  const activeMacros = applied && research
    ? { protein: round(research.protein_g), carbs: round(research.carb_g), fat: round(research.fat_g) }
    : computedMacros;
  const activeCal = applied && research ? round(research.adjusted_calories) : selectedCal;

  const applyResearch = () => { setApplied(true); setManualCal(null); setEditing(false); };

  const saveToProfile = async () => {
    if (!profile) return;
    setSaving(true);
    try {
      await entities.UserProfile.update(profile.id, {
        weight_kg: parseFloat(weight) || undefined,
        height_cm: parseFloat(height) || undefined,
        age: parseInt(age) || undefined,
        sex,
        calorie_target: activeCal,
        protein_target_g: activeMacros.protein,
        carb_target_g: activeMacros.carbs,
        fat_target_g: activeMacros.fat,
      });
      onApplied?.({
        weight_kg: parseFloat(weight) || undefined,
        height_cm: parseFloat(height) || undefined,
        age: parseInt(age) || undefined,
        sex,
        calorie_target: activeCal,
        protein_target_g: activeMacros.protein,
        carb_target_g: activeMacros.carbs,
        fat_target_g: activeMacros.fat,
      });
    } catch {
      toast({ title: t("calc_couldntSave"), variant: "destructive" });
    }
    setSaving(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="font-heading">{t("calc_title")}</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex gap-2 text-xs text-muted-foreground bg-muted/60 rounded-xl p-3">
            <AlertTriangle className="w-4 h-4 shrink-0 text-primary mt-0.5" />
            <span>{t("calc_disclaimer")}</span>
          </div>

          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">{t("calc_weight")}</Label>
                <Input type="number" inputMode="decimal" value={weight} onChange={(e) => setWeight(e.target.value)} placeholder="70" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("calc_height")}</Label>
                <Input type="number" inputMode="decimal" value={height} onChange={(e) => setHeight(e.target.value)} placeholder="175" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("calc_age")}</Label>
                <Input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} placeholder="30" />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">{t("calc_sex")}</Label>
                <ResponsiveSelect
                  value={sex}
                  onValueChange={setSex}
                  placeholder={t("calc_select")}
                  options={[
                    { value: "male", label: t("calc_male") },
                    { value: "female", label: t("calc_female") },
                    { value: "other", label: t("calc_other") },
                  ]}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">{t("calc_activity")}</Label>
              <ResponsiveSelect
                value={activity}
                onValueChange={setActivity}
                placeholder={t("calc_activity")}
                options={ACTIVITY_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">{t("calc_steps")}</Label>
              <Input type="number" inputMode="numeric" value={steps} onChange={(e) => onSteps(e.target.value)} placeholder={t("calc_stepsPh")} />
              {parseInt(steps) > 0 && (
                <p className="text-[11px] text-accent">
                  {t("calc_stepsNote", { label: t(ACTIVITY_OPTIONS.find((o) => o.value === activity).labelKey) })}
                </p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs flex items-center gap-1.5">
                <HeartPulse className="w-3.5 h-3.5 text-accent" /> {t("calc_health")}
              </Label>
              <Input value={healthIssues} onChange={(e) => setHealthIssues(e.target.value)} placeholder={t("calc_healthPh")} />
              {healthIssues.trim() && (
                <p className="text-[11px] leading-relaxed text-accent font-medium bg-accent/10 rounded-lg px-2.5 py-2">
                  {t("calc_healthWarn")}
                </p>
              )}
            </div>

            <Button className="w-full h-11" onClick={calculate} disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Calculator className="w-4 h-4" />}
              {loading ? t("calc_calculating") : t("calc_calcBtn")}
            </Button>
          </div>

          {result && (
            <>
              <div className="bg-muted/50 rounded-2xl p-3 flex gap-3">
                <span className="text-xl">🛌</span>
                <div>
                  <p className="text-sm font-heading">{t("calc_bmrTitle", { n: result.bmr })}</p>
                  <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{t("calc_bmrDesc")}</p>
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-muted-foreground mb-2">{t("calc_chooseGoal")}</p>
                <div className="grid grid-cols-2 gap-2">
                  {VARIANTS.map((v) => {
                    const cal = result.tdee + v.delta;
                    const active = selectedKey === v.key && !applied;
                    return (
                      <button
                        key={v.key}
                        type="button"
                        onClick={() => { setSelectedKey(v.key); setApplied(false); setManualCal(null); setEditing(false); }}
                        className={`text-left rounded-xl p-2.5 border-2 transition-colors ${active ? "border-primary bg-primary/5" : "border-border bg-card hover:border-primary/40"}`}
                      >
                        <span className="text-lg">{v.emoji}</span>
                        <p className="text-sm font-heading mt-0.5">{t(v.labelKey)}</p>
                        <p className="text-[11px] text-muted-foreground">{t(v.subKey)}</p>
                        <p className="text-sm font-semibold mt-0.5">{cal} {t("calc_kcal")}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="bg-card rounded-2xl border-2 border-primary/30 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{applied && research ? t("calc_healthAdjusted") : t(variant.labelKey)}</p>
                    {editing ? (
                      <div className="flex items-center gap-2 mt-1">
                        <Input type="number" value={manualCal ?? ""} onChange={(e) => setManualCal(parseInt(e.target.value) || 0)} className="h-9 w-28 text-lg font-heading" />
                        <Button size="icon" className="h-9 w-9" onClick={() => { setEditing(false); setApplied(false); }}>
                          <Check className="w-4 h-4" />
                        </Button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-3xl font-heading">{activeCal}</span>
                        <span className="text-xs text-muted-foreground">{t("calc_kcalDay")}</span>
                        <button type="button" onClick={() => setEditing(true)} className="ml-1 p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-primary">
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <Stat label={t("calc_protein")} value={`${activeMacros.protein}g`} />
                  <Stat label={t("calc_carbs")} value={`${activeMacros.carbs}g`} />
                  <Stat label={t("calc_fat")} value={`${activeMacros.fat}g`} />
                </div>

                {research && !applied && (
                  <div className="mt-2 rounded-xl border-2 border-accent/30 bg-accent/5 p-3 space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-wide text-accent flex items-center gap-1.5">
                      <HeartPulse className="w-3.5 h-3.5" /> {t("calc_adjustedFor")}
                    </p>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <Stat label={t("calc_adjustedCal")} value={`${round(research.adjusted_calories)} ${t("calc_kcal")}`} highlight />
                      <Stat label={t("calc_protein")} value={`${round(research.protein_g)}g`} />
                      <Stat label={t("calc_carbs")} value={`${round(research.carb_g)}g`} />
                      <Stat label={t("calc_fat")} value={`${round(research.fat_g)}g`} />
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed pt-1">“{research.note}”</p>
                    <Button size="sm" variant="outline" className="h-8 text-xs" onClick={applyResearch}>{t("calc_apply")}</Button>
                    <p className="text-[11px] text-accent font-medium">{t("calc_medical")}</p>
                  </div>
                )}

                <Button className="w-full h-10" onClick={saveToProfile} disabled={saving}>
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                  {t("calc_save")}
                </Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Stat({ label, value, highlight }) {
  return (
    <div className={`rounded-xl p-2.5 ${highlight ? "bg-primary/10 border border-primary/30" : "bg-muted/50"}`}>
      <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="font-heading text-base mt-0.5">{value}</p>
    </div>
  );
}
