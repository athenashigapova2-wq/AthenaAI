import React from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang } from "@/lib/i18n";

const MEAL_KEY = { breakfast: "meal_breakfast", lunch: "meal_lunch", dinner: "meal_dinner", snack: "meal_snack" };

export default function MealCard({ meal, onDelete, compact = false }) {
  const { t } = useLang();
  if (compact) {
    return (
      <div className="flex items-center justify-between py-3 border-b border-border last:border-0">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{meal.name}</p>
          <div className="flex items-center gap-3 mt-0.5">
            <span className="text-xs text-muted-foreground">{meal.calories} {t("coach_cal")}</span>
            <span className="text-xs text-emerald-600">{meal.protein_g} g {t("coach_protein")}</span>
            <span className="text-xs text-blue-500">{meal.carbs_g} g {t("coach_carbs")}</span>
            <span className="text-xs text-amber-500">{meal.fat_g} g {t("coach_fat")}</span>
          </div>
        </div>
        {onDelete && (
          <Button variant="ghost" size="icon" className="touch-target h-7 w-7 text-muted-foreground hover:text-destructive shrink-0" onClick={() => onDelete(meal.id)}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="bg-card rounded-xl border border-border p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold font-heading">{meal.name}</p>
          {meal.meal_type && (
            <span className="text-xs text-muted-foreground">{t(MEAL_KEY[meal.meal_type] || "meal_snack")}</span>
          )}
        </div>
        {onDelete && (
          <Button variant="ghost" size="icon" className="touch-target h-7 w-7 text-muted-foreground hover:text-destructive" onClick={() => onDelete(meal.id)}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>
      <div className="grid grid-cols-4 gap-2 mt-3">
        <div className="text-center">
          <p className="text-sm font-semibold">{meal.calories}</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_cal")}</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold text-emerald-600">{meal.protein_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_protein")}</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold text-blue-500">{meal.carbs_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_carbs")}</p>
        </div>
        <div className="text-center">
          <p className="text-sm font-semibold text-amber-500">{meal.fat_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_fat")}</p>
        </div>
      </div>
    </div>
  );
}