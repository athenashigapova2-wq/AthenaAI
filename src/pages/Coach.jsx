import React, { useState, useEffect, useCallback } from "react";
import { entities } from '@/lib/entities';
import { invokeLLM } from '@/lib/invokeLLM';
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Loader2, Sparkles, RefreshCw } from "lucide-react";
import RecommendationCard from "@/components/RecommendationCard";
import { useNavigate } from "react-router-dom";
import { useLang, LANG_NAME } from "@/lib/i18n";
import LanguageSwitcher from "@/components/LanguageSwitcher";

const ATHENA_IMG = "/athena-avatar.png";

const today = () => new Date().toISOString().split("T")[0];

export default function Coach() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { t, lang } = useLang();
  const [profile, setProfile] = useState(null);
  const [meals, setMeals] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [showLogMeal, setShowLogMeal] = useState(false);
  const [mealToLog, setMealToLog] = useState(null);

  const loadData = useCallback(async () => {
    const [profiles, todayMeals] = await Promise.all([
      entities.UserProfile.filter({ created_by_id: user?.id }),
      entities.MealLog.filter({ date: today(), created_by_id: user?.id }),
    ]);
    setProfile(profiles[0] || null);
    setMeals(todayMeals);
    setLoading(false);
  }, [user]);

  useEffect(() => { loadData(); }, [loadData]);

  const generateRecommendations = async () => {
    if (!profile) return;
    setGenerating(true);
    const consumed = meals.reduce(
      (a, m) => ({ cal: a.cal + m.calories, p: a.p + m.protein_g, c: a.c + m.carbs_g, f: a.f + m.fat_g }),
      { cal: 0, p: 0, c: 0, f: 0 }
    );
    const remaining = {
      calories: Math.max(profile.calorie_target - consumed.cal, 0),
      protein: Math.max(profile.protein_target_g - consumed.p, 0),
      carbs: Math.max(profile.carb_target_g - consumed.c, 0),
      fat: Math.max(profile.fat_target_g - consumed.f, 0),
    };

    const prompt = `You are a practical nutrition coach. Generate exactly 3 meal options for the user.

IMPORTANT — LANGUAGE: Write the ENTIRE response in ${LANG_NAME[lang]} — meal names, descriptions, prep_time, and every ingredient. Use everyday ${LANG_NAME[lang]} grocery terms a shopper would recognize. Do not use any other language.

User context:
- Goal: ${profile.goal}
- Remaining today: ${remaining.calories} cal, ${remaining.protein} g protein, ${remaining.carbs} g carbs, ${remaining.fat} g fat
- Budget: ${profile.budget || "medium"}
- Cooking skill: ${profile.cooking_skill || "basic"}
- Allergies: ${profile.allergies?.join(", ") || "none"}
- Favorite foods: ${profile.favorite_foods?.join(", ") || "none listed"}
- Disliked foods: ${profile.disliked_foods?.join(", ") || "none listed"}
- Meals already eaten today: ${meals.map((m) => m.name).join(", ") || "none yet"}

Rules:
- Each meal should get the user closer to their remaining macros
- Prioritize the macro with the biggest gap vs target
- Include one quick option (under 10 min), one cooking option, and one ordering/buying option
- Be specific with portion sizes
- Never lecture about nutrition
- Prices: set estimated_price_rub as a realistic meal price in Russian rubles (number only, e.g. 750). The app converts it to the user's currency automatically. This ruble field is only for price conversion — it must NOT influence the language of any other field.
- CRITICAL: all text fields must be in ${LANG_NAME[lang]} — meal name, description, prep_time, and the ingredients array (everyday ${LANG_NAME[lang]} grocery terms).

Return JSON with "meals" array. Each meal: name, description (1 sentence), calories (number), protein_g, carbs_g, fat_g, prep_time (e.g. "5 min"), estimated_price_rub (number, rubles), ingredients (array of strings for shopping list). Every string value must be in ${LANG_NAME[lang]}.`;

    const res = await invokeLLM({
      prompt,
      response_json_schema: {
        type: "object",
        properties: {
          meals: {
            type: "array",
            items: {
              type: "object",
              properties: {
                name: { type: "string" },
                description: { type: "string" },
                calories: { type: "number" },
                protein_g: { type: "number" },
                carbs_g: { type: "number" },
                fat_g: { type: "number" },
                prep_time: { type: "string" },
                estimated_price_rub: { type: "number" },
                ingredients: { type: "array", items: { type: "string" } },
              },
            },
          },
        },
      },
    });
    setRecommendations(res.meals || []);
    setGenerating(false);
  };

  useEffect(() => {
    if (profile && !loading) generateRecommendations();
     
  }, [profile, loading, lang]);

  const handleLogRec = async (rec) => {
    const meal = await entities.MealLog.create({
      name: rec.name,
      calories: Math.round(rec.calories),
      protein_g: Math.round(rec.protein_g),
      carbs_g: Math.round(rec.carbs_g),
      fat_g: Math.round(rec.fat_g),
      date: today(),
      from_recommendation: true,
    });
    setMeals((m) => [...m, meal]);
  };

  const handleAddToShoppingList = async (ingredients) => {
    const existing = await entities.ShoppingItem.filter({ created_by_id: user?.id });
    const existingNames = new Set(existing.map((i) => i.name.toLowerCase()));
    const newItems = ingredients.filter((i) => !existingNames.has(i.toLowerCase()));
    if (newItems.length > 0) {
      await entities.ShoppingItem.bulkCreate(
        newItems.map((name) => ({ name, checked: false }))
      );
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="px-4 pt-12 text-center">
        <p className="text-sm text-muted-foreground">Complete your profile first to get recommendations.</p>
      </div>
    );
  }

  const consumed = meals.reduce(
    (a, m) => ({ cal: a.cal + m.calories, p: a.p + m.protein_g, c: a.c + m.carbs_g, f: a.f + m.fat_g }),
    { cal: 0, p: 0, c: 0, f: 0 }
  );
  const remaining = {
    calories: Math.max(profile.calorie_target - consumed.cal, 0),
    protein: Math.max(profile.protein_target_g - consumed.p, 0),
    carbs: Math.max(profile.carb_target_g - consumed.c, 0),
    fat: Math.max(profile.fat_target_g - consumed.f, 0),
  };

  const maxGap = Math.max(
    remaining.protein / profile.protein_target_g,
    remaining.carbs / profile.carb_target_g,
    remaining.fat / profile.fat_target_g
  );
  const priority =
    remaining.protein / profile.protein_target_g === maxGap ? t("coach_protein") :
    remaining.carbs / profile.carb_target_g === maxGap ? t("coach_carbs") : t("coach_fat");

  return (
    <div className="px-4 pt-6 pb-4 space-y-5">
      <div className="flex justify-end">
        <LanguageSwitcher compact />
      </div>
      <div className="flex items-center gap-3">
        <img
          src={ATHENA_IMG}
          alt="Athena"
          className="w-16 h-16 rounded-full object-cover object-top border-2 border-primary/30 shrink-0 bg-background"
        />
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold font-heading">{t("coach_title")}</h1>
          <p className="text-sm text-muted-foreground mt-0.5">{t("coach_subtitle")}</p>
        </div>
        <Button size="sm" variant="outline" className="h-8 text-xs shrink-0" onClick={() => navigate("/chat")}>
          {t("coach_askAthena")}
        </Button>
      </div>

      {/* Remaining summary */}
      <div className="bg-info rounded-2xl p-4 text-info-foreground border border-info-foreground/10 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide mb-2 text-info-foreground/70">{t("coach_stillNeeded")}</p>
        <div className="grid grid-cols-4 gap-2">
          <div>
            <p className="text-xl font-bold font-heading">{remaining.calories}</p>
            <p className="text-[10px] text-info-foreground/60">{t("coach_cal")}</p>
          </div>
          <div>
            <p className="text-xl font-bold font-heading">{remaining.protein} g</p>
            <p className="text-[10px] text-info-foreground/60">{t("coach_protein")}</p>
          </div>
          <div>
            <p className="text-xl font-bold font-heading">{remaining.carbs} g</p>
            <p className="text-[10px] text-info-foreground/60">{t("coach_carbs")}</p>
          </div>
          <div>
            <p className="text-xl font-bold font-heading">{remaining.fat} g</p>
            <p className="text-[10px] text-info-foreground/60">{t("coach_fat")}</p>
          </div>
        </div>
        {remaining.calories > 0 && (
          <p className="text-xs mt-3 text-info-foreground/75">
            <span className="font-semibold">{t("coach_priority")}:</span> {priority}
          </p>
        )}
      </div>

      {/* Recommendations */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold font-heading">{t("coach_suggestions")}</h2>
          <Button
            size="sm"
            variant="outline"
            className="h-8 text-xs"
            onClick={generateRecommendations}
            disabled={generating}
          >
            {generating ? <Loader2 className="w-3 h-3 animate-spin mr-1" /> : <RefreshCw className="w-3 h-3 mr-1" />}
            {t("coach_refresh")}
          </Button>
        </div>

        {generating && recommendations.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Sparkles className="w-8 h-8 mb-3 text-primary animate-pulse" />
            <p className="text-sm">{t("coach_generating")}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {recommendations.map((rec, i) => (
              <RecommendationCard
                key={i}
                rec={rec}
                onLog={handleLogRec}
                onAddToShoppingList={handleAddToShoppingList}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}