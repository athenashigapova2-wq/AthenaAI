import React, { useState } from "react";
import { toLocalDateStr } from "@/lib/utils";
import { entities } from '@/lib/entities';
import { invokeAthenaTask } from '@/lib/athenaTasks';
import { supabase } from '@/api/supabaseClient';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import ResponsiveSelect from "@/components/ResponsiveSelect";
import { Loader2, Sparkles } from "lucide-react";
import { useLang } from "@/lib/i18n";

const today = () => toLocalDateStr();

export default function LogMealDialog({ open, onOpenChange, onLogged }) {
  const { t, lang } = useLang();
  const [desc, setDesc] = useState("");
  const [estimating, setEstimating] = useState(false);
  const [form, setForm] = useState({ name: "", meal_type: "lunch", calories: "", protein_g: "", carbs_g: "", fat_g: "" });
  const [source, setSource] = useState(null); // 'db' | 'ai' | null
  const [saving, setSaving] = useState(false);

  const update = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const handleEstimate = async () => {
    if (!desc.trim()) return;
    setEstimating(true);
    try {
      // Сначала пробуем найти точное совпадение в базе (перевод + поиск на сервере)
      const { data: dbResult, error: dbError } = await supabase.functions.invoke('estimate-meal', {
        body: { description: desc, language: lang },
      });

      if (!dbError && dbResult?.matched) {
        setForm((f) => ({
          ...f,
          name: dbResult.name || desc,
          calories: String(dbResult.calories),
          protein_g: String(dbResult.protein_g),
          carbs_g: String(dbResult.carbs_g),
          fat_g: String(dbResult.fat_g),
        }));
        setSource('db');
        setEstimating(false);
        return;
      }
    } catch {
      // Тихо падаем на фолбэк ниже — это не критично, просто теряем точность
    }

    // Не нашли в базе (или база недоступна) — как раньше, чистая оценка ИИ
    const res = await invokeAthenaTask('meal_estimate', {
      description: desc,
      language: lang,
    });
    setForm((f) => ({
      ...f,
      name: res.name || desc,
      calories: String(Math.round(res.calories || 0)),
      protein_g: String(Math.round(res.protein_g || 0)),
      carbs_g: String(Math.round(res.carbs_g || 0)),
      fat_g: String(Math.round(res.fat_g || 0)),
    }));
    setSource('ai');
    setEstimating(false);
  };

  const handleSave = async () => {
    setSaving(true);
    const meal = await entities.MealLog.create({
      name: form.name, meal_type: form.meal_type,
      calories: Number(form.calories), protein_g: Number(form.protein_g),
      carbs_g: Number(form.carbs_g), fat_g: Number(form.fat_g), date: today(),
    });
    setSaving(false);
    setForm({ name: "", meal_type: "lunch", calories: "", protein_g: "", carbs_g: "", fat_g: "" });
    setDesc("");
    setSource(null);
    onLogged(meal);
  };

  const canSave = form.name && form.calories && form.protein_g && form.carbs_g && form.fat_g;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-heading">{t("log_title")}</DialogTitle>
        </DialogHeader>

        <div className="bg-accent rounded-xl p-3 space-y-2">
          <p className="text-xs font-medium text-primary flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> {t("log_desc")}
          </p>
          <div className="flex gap-2">
            <Input placeholder={t("log_descPh")} value={desc} onChange={(e) => { setDesc(e.target.value); setSource(null); }} className="text-sm" />
            <Button size="sm" className="shrink-0" onClick={handleEstimate} disabled={estimating || !desc.trim()}>
              {estimating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : t("log_estimate")}
            </Button>
          </div>
          {source === 'db' && (
            <p className="text-[11px] text-emerald-600">✓ Точные данные из базы продуктов</p>
          )}
          {source === 'ai' && (
            <p className="text-[11px] text-muted-foreground">Оценка ИИ (в базе не нашлось точного совпадения)</p>
          )}
        </div>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs">{t("log_name")}</Label>
              <Input value={form.name} onChange={(e) => update("name", e.target.value)} placeholder={t("log_namePh")} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">{t("log_mealType")}</Label>
              <ResponsiveSelect
                value={form.meal_type}
                onValueChange={(v) => update("meal_type", v)}
                placeholder={t("log_mealType")}
                options={[
                  { value: "breakfast", label: t("meal_breakfast") },
                  { value: "lunch", label: t("meal_lunch") },
                  { value: "dinner", label: t("meal_dinner") },
                  { value: "snack", label: t("meal_snack") },
                ]}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">{t("log_calories")}</Label>
            <Input type="number" value={form.calories} onChange={(e) => update("calories", e.target.value)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1.5"><Label className="text-xs">{t("log_protein")}</Label><Input type="number" value={form.protein_g} onChange={(e) => update("protein_g", e.target.value)} /></div>
            <div className="space-y-1.5"><Label className="text-xs">{t("log_carbs")}</Label><Input type="number" value={form.carbs_g} onChange={(e) => update("carbs_g", e.target.value)} /></div>
            <div className="space-y-1.5"><Label className="text-xs">{t("log_fat")}</Label><Input type="number" value={form.fat_g} onChange={(e) => update("fat_g", e.target.value)} /></div>
          </div>
        </div>

        <Button className="w-full h-10" onClick={handleSave} disabled={!canSave || saving}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin mr-1" /> : null}
          {saving ? t("log_saving") : t("log_logMeal")}
        </Button>
      </DialogContent>
    </Dialog>
  );
}
