import React, { useState, useEffect, useCallback, useRef } from "react";
import { toLocalDateStr } from "@/lib/utils";
import { entities } from '@/lib/entities';
import { invokeAthenaTask } from '@/lib/athenaTasks';
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Loader2, Sparkles, RefreshCw } from "lucide-react";
import RecommendationCard from "@/components/RecommendationCard";
import { useNavigate } from "react-router-dom";
import { useLang } from "@/lib/i18n";
import { toast } from "@/components/ui/use-toast";
import { createIdempotencyKey } from "@/lib/idempotency";

const ATHENA_IMG = "/athena-avatar.png";

const today = () => toLocalDateStr();
const recommendationKey = (rec) => JSON.stringify([
  rec.name,
  rec.calories,
  rec.protein_g,
  rec.carbs_g,
  rec.fat_g,
]);

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
  const [loggingMeals, setLoggingMeals] = useState(new Set());
  const [loggedMeals, setLoggedMeals] = useState(new Set());
  const [addingShoppingLists, setAddingShoppingLists] = useState(new Set());
  const [addedShoppingLists, setAddedShoppingLists] = useState(new Set());
  const loggingMealsRef = useRef(new Set());
  const idempotencyKeysRef = useRef(new Map());
  const addingShoppingListsRef = useRef(new Set());
  const shoppingIdempotencyKeysRef = useRef(new Map());

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
    try {
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

      const res = await invokeAthenaTask('meal_recommendations', {
        remaining,
        goal: profile.goal,
        budget: profile.budget || 'medium',
        cooking_skill: profile.cooking_skill || 'basic',
        dietary_pattern: profile.dietary_pattern || 'omnivore',
        dietary_restrictions: profile.dietary_restrictions || [],
        allergies: profile.allergies || [],
        favorite_foods: profile.favorite_foods || [],
        disliked_foods: profile.disliked_foods || [],
        meals_eaten: meals.map((meal) => meal.name),
        language: lang,
      });
      setRecommendations(res.meals || []);
    } catch (error) {
      toast({
        title: "Не удалось получить рекомендации",
        description: error instanceof Error ? error.message : "Попробуйте ещё раз",
        variant: "destructive",
      });
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => {
    if (profile && !loading) generateRecommendations();
     
  }, [profile, loading, lang]);

  const handleLogRec = async (rec) => {
    const recKey = recommendationKey(rec);
    if (loggingMealsRef.current.has(recKey) || loggedMeals.has(recKey)) return;
    loggingMealsRef.current.add(recKey);
    setLoggingMeals((current) => new Set(current).add(recKey));
    const idempotencyKey = idempotencyKeysRef.current.get(recKey)
      || createIdempotencyKey("recommended-meal");
    idempotencyKeysRef.current.set(recKey, idempotencyKey);
    try {
      const meal = await entities.MealLog.createIdempotently({
        name: rec.name,
        calories: Math.round(rec.calories),
        protein_g: Math.round(rec.protein_g),
        carbs_g: Math.round(rec.carbs_g),
        fat_g: Math.round(rec.fat_g),
        date: today(),
        from_recommendation: true,
      }, idempotencyKey);
      idempotencyKeysRef.current.delete(recKey);
      setMeals((current) => current.some((item) => item.id === meal.id) ? current : [...current, meal]);
      setLoggedMeals((current) => new Set(current).add(recKey));
    } catch (error) {
      toast({
        title: "Не удалось записать приём пищи",
        description: error instanceof Error ? error.message : "Попробуйте ещё раз",
        variant: "destructive",
      });
    } finally {
      loggingMealsRef.current.delete(recKey);
      setLoggingMeals((current) => {
        const next = new Set(current);
        next.delete(recKey);
        return next;
      });
    }
  };

  const handleAddToShoppingList = async (rec) => {
    const recKey = recommendationKey(rec);
    if (addingShoppingListsRef.current.has(recKey) || addedShoppingLists.has(recKey)) return;
    addingShoppingListsRef.current.add(recKey);
    setAddingShoppingLists((current) => new Set(current).add(recKey));
    const actionKeys = shoppingIdempotencyKeysRef.current.get(recKey) || new Map();
    shoppingIdempotencyKeysRef.current.set(recKey, actionKeys);
    try {
      const existing = await entities.ShoppingItem.filter({ created_by_id: user?.id });
      const existingNames = new Set(existing.map((item) => item.name.trim().toLowerCase()));
      const uniqueIngredients = [...new Map(
        rec.ingredients
          .map((name) => name.trim())
          .filter(Boolean)
          .map((name) => [name.toLowerCase(), name]),
      ).values()];
      const newItems = uniqueIngredients.filter((name) => !existingNames.has(name.toLowerCase()));
      await Promise.all(newItems.map((name) => {
        const normalizedName = name.toLowerCase();
        const key = actionKeys.get(normalizedName) || createIdempotencyKey("shopping-item");
        actionKeys.set(normalizedName, key);
        return entities.ShoppingItem.createIdempotently({ name, checked: false }, key);
      }));
      shoppingIdempotencyKeysRef.current.delete(recKey);
      setAddedShoppingLists((current) => new Set(current).add(recKey));
    } catch (error) {
      toast({
        title: "Не удалось добавить продукты",
        description: error instanceof Error ? error.message : "Попробуйте ещё раз",
        variant: "destructive",
      });
    } finally {
      addingShoppingListsRef.current.delete(recKey);
      setAddingShoppingLists((current) => {
        const next = new Set(current);
        next.delete(recKey);
        return next;
      });
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
                logging={loggingMeals.has(recommendationKey(rec))}
                logged={loggedMeals.has(recommendationKey(rec))}
                addingToShoppingList={addingShoppingLists.has(recommendationKey(rec))}
                addedToShoppingList={addedShoppingLists.has(recommendationKey(rec))}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
