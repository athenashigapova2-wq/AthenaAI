import React from "react";
import { Clock, ShoppingCart, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLang, CURRENCY, CURRENCY_RATE, LANG_CURRENCY_CODE } from "@/lib/i18n";

export default function RecommendationCard({ rec, onLog, onAddToShoppingList }) {
  const { t, lang } = useLang();
  const priceLabel =
    rec.estimated_price_rub != null
      ? `${CURRENCY[lang]}${Math.round(rec.estimated_price_rub * (CURRENCY_RATE[LANG_CURRENCY_CODE[lang]] || 1))}`
      : rec.estimated_price;
  return (
    <div className="bg-card rounded-xl border border-border p-4 space-y-3">
      <div>
        <p className="font-semibold font-heading text-sm">{rec.name}</p>
        {rec.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{rec.description}</p>
        )}
      </div>

      <div className="grid grid-cols-4 gap-2">
        <div className="text-center bg-muted/50 rounded-lg py-1.5">
          <p className="text-xs font-semibold">{rec.calories}</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_cal")}</p>
        </div>
        <div className="text-center bg-emerald-50 rounded-lg py-1.5">
          <p className="text-xs font-semibold text-emerald-600">{rec.protein_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_protein")}</p>
        </div>
        <div className="text-center bg-blue-50 rounded-lg py-1.5">
          <p className="text-xs font-semibold text-blue-500">{rec.carbs_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_carbs")}</p>
        </div>
        <div className="text-center bg-amber-50 rounded-lg py-1.5">
          <p className="text-xs font-semibold text-amber-500">{rec.fat_g} g</p>
          <p className="text-[10px] text-muted-foreground">{t("coach_fat")}</p>
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        {rec.prep_time && (
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" /> {rec.prep_time}
          </span>
        )}
        {priceLabel && (
          <span className="flex items-center gap-1">
            <span className="text-xs font-medium">{priceLabel}</span>
          </span>
        )}
      </div>

      <div className="flex gap-2">
        <Button size="sm" className="flex-1 h-8 text-xs" onClick={() => onLog(rec)}>
          <Plus className="w-3 h-3 mr-1" /> {t("rec_logMeal")}
        </Button>
        {rec.ingredients && rec.ingredients.length > 0 && (
          <Button size="sm" variant="outline" className="h-8 text-xs" onClick={() => onAddToShoppingList(rec.ingredients)}>
            <ShoppingCart className="w-3 h-3 mr-1" /> {t("rec_list")}
          </Button>
        )}
      </div>
    </div>
  );
}