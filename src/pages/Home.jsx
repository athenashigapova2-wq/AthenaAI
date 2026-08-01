import React, { useState, useEffect, useCallback } from "react";
import { entities } from '@/lib/entities';
import { invokeLLM } from '@/lib/invokeLLM';
import { supabase } from '@/api/supabaseClient';
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";
import { Plus, Sparkles, TrendingDown, TrendingUp, Minus, Loader2, Calculator } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import MacroRing from "@/components/MacroRing";
import CalorieRing from "@/components/CalorieRing";
import MealCard from "@/components/MealCard";
import Onboarding from "@/pages/Onboarding";
import LogMealDialog from "@/components/LogMealDialog";
import WeekHistory from "@/components/WeekHistory";
import HerculesQuote from "@/components/HerculesQuote";
import { HealthCheckIn } from "@/components/HealthCheckIn";
import { usePullToRefresh } from "@/hooks/usePullToRefresh";
import { toast } from "@/components/ui/use-toast";
import { useLang } from "@/lib/i18n";
import { LineChart, Line, ResponsiveContainer, YAxis } from "recharts";

const today = () => new Date().toISOString().split("T")[0];

export default function Home() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { t, lang } = useLang();
  const [profile, setProfile] = useState(null);
  const [meals, setMeals] = useState([]);
  const [weights, setWeights] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [showLogMeal, setShowLogMeal] = useState(false);
  const [aiTip, setAiTip] = useState(null);
  const [loadingTip, setLoadingTip] = useState(false);
  const [habitInsight, setHabitInsight] = useState(null); // { suggestion, insufficient_data }
  const [loadingHabit, setLoadingHabit] = useState(false);

  const [loadError, setLoadError] = useState(false);

  const loadData = useCallback(async () => {
    if (!user?.id) return; // ждём, пока авторизация точно готова — иначе запросы уйдут с пустым user_id
    setLoading(true);
    setLoadError(false);
    try {
      const [profiles, todayMeals, allWeights] = await Promise.all([
        entities.UserProfile.filter({ created_by_id: user.id }),
        entities.MealLog.filter({ date: today(), created_by_id: user.id }),
        entities.WeightLog.filter({ created_by_id: user.id }, "-date", 14),
      ]);
      if (!profiles.length || !profiles[0].onboarding_complete) {
        setShowOnboarding(true);
        return;
      }
      setProfile(profiles[0]);
      setMeals(todayMeals);
      setWeights(allWeights.reverse());
    } catch (err) {
      console.error("Home loadData failed:", err);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [user]);

  const { pullDistance, refreshing: pullRefreshing } = usePullToRefresh(loadData);
  useEffect(() => { loadData(); }, [loadData]);

  const fetchTip = useCallback(async (prof, todayMeals) => {
    if (!prof) return;
    const consumed = todayMeals.reduce(
      (a, m) => ({ cal: a.cal + m.calories, p: a.p + m.protein_g, c: a.c + m.carbs_g, f: a.f + m.fat_g }),
      { cal: 0, p: 0, c: 0, f: 0 }
    );
    const remaining = {
      calories: Math.max(prof.calorie_target - consumed.cal, 0),
      protein: Math.max(prof.protein_target_g - consumed.p, 0),
      carbs: Math.max(prof.carb_target_g - consumed.c, 0),
      fat: Math.max(prof.fat_target_g - consumed.f, 0),
    };
    if (remaining.calories === 0) { setAiTip(t("home_hitTargets")); return; }
    setLoadingTip(true);
    try {
      const res = await invokeLLM({
        prompt: `You are a concise nutrition coach. The user has ${remaining.calories} cal, ${remaining.protein}g protein, ${remaining.carbs}g carbs, ${remaining.fat}g fat remaining today. Their goal is "${prof.goal}". In 1-2 short sentences, tell them what their priority macro is and one quick food suggestion. Be warm, not preachy. Respond in language code: ${lang}.`,
      });
      setAiTip(res.text);
    } catch (err) {
      console.error("fetchTip failed:", err);
    } finally {
      setLoadingTip(false);
    }
  }, []);

  useEffect(() => {
    if (profile && !loading) fetchTip(profile, meals);
  }, [profile, loading]);

  // Проактивный анализ привычек: читаем закэшированный результат, и если он
  // старше суток (или его вообще ещё нет) — просим Edge Function пересчитать.
  const loadHabitInsight = useCallback(async (forceRefresh = false) => {
    if (!user?.id) return;
    try {
      const { data } = await supabase.from('agent_memory').select('*').eq('user_id', user.id).limit(1);
      const mem = data?.[0];
      const isStale = !mem?.suggestion_generated_at ||
        Date.now() - new Date(mem.suggestion_generated_at).getTime() > 24 * 60 * 60 * 1000;

      if (mem?.suggestion && !isStale && !forceRefresh) {
        setHabitInsight({ suggestion: mem.suggestion, frequent_foods: mem.frequent_foods });
        return;
      }

      setLoadingHabit(true);
      const { data: res, error } = await supabase.functions.invoke('analyze-habits', { body: { language: lang } });
      if (!error && res) setHabitInsight(res);
    } catch {
      // тихо игнорируем — это дополнительная, не критичная фича
    } finally {
      setLoadingHabit(false);
    }
  }, [user?.id, lang]);

  useEffect(() => {
    if (profile && !loading) loadHabitInsight();
  }, [profile, loading]);

  const handleDeleteMeal = async (id) => {
    const prevMeals = meals;
    setMeals((m) => m.filter((x) => x.id !== id)); // optimistic
    try {
      await entities.MealLog.delete(id);
    } catch {
      setMeals(prevMeals); // rollback
      toast({ title: "Couldn't delete meal", description: "Please try again.", variant: "destructive" });
    }
  };

  const handleMealLogged = (meal) => {
    setMeals((m) => [...m, meal]);
    setShowLogMeal(false);
    fetchTip(profile, [...meals, meal]);
  };

  const onOnboardingComplete = () => {
    setShowOnboarding(false);
    loadData();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-3 px-6 text-center">
        <p className="text-sm text-muted-foreground">{t("home_loadError") || "Не получилось загрузить данные. Проверь соединение."}</p>
        <Button size="sm" onClick={loadData}>{t("home_retry") || "Попробовать снова"}</Button>
      </div>
    );
  }

  if (showOnboarding) return <Onboarding onComplete={onOnboardingComplete} />;

  const consumed = meals.reduce(
    (a, m) => ({ cal: a.cal + m.calories, p: a.p + m.protein_g, c: a.c + m.carbs_g, f: a.f + m.fat_g }),
    { cal: 0, p: 0, c: 0, f: 0 }
  );

  const calPct = Math.min(Math.round((consumed.cal / profile.calorie_target) * 100), 100);
  const calRemaining = Math.max(profile.calorie_target - consumed.cal, 0);

  const weightData = weights.map((w) => ({ val: w.weight_kg }));
  const weightTrend = weights.length >= 2 ? weights[weights.length - 1].weight_kg - weights[0].weight_kg : 0;

  return (
    <div className="px-4 pt-6 pb-4 space-y-6">
      {/* Pull-to-refresh indicator */}
      <div
        className="flex items-center justify-center overflow-hidden"
        style={{ height: pullDistance }}
      >
        {(pullDistance > 0 || pullRefreshing) && (
          <Loader2 className={`w-5 h-5 text-primary ${pullRefreshing ? "animate-spin" : ""}`} />
        )}
      </div>

      {/* Hero header */}
      <header>
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[11px] uppercase tracking-[0.25em] text-accent font-display">
              {new Date().toLocaleDateString(lang, { weekday: "long" })} · Olympus
            </p>
            <h1 className="text-2xl font-heading mt-1">
              {t("home_greeting", { name: user?.user_metadata?.full_name?.split(" ")[0] || t("home_hero") })}
            </h1>
          </div>
        </div>
        <HerculesQuote />
      </header>

      <WeekHistory profile={profile} />

      {/* Calorie card */}
      <div className="bg-card rounded-3xl border-2 border-primary/25 p-5 shadow-sm flex flex-col items-center">
        <CalorieRing
          remaining={calRemaining}
          target={profile.calorie_target}
          consumed={consumed.cal}
          label={t("home_calLabel")}
          ofLabel={t("home_ofTarget", { n: profile.calorie_target })}
        />
        <div className="flex justify-center gap-6 mt-5">
          <MacroRing label={t("coach_protein")} current={consumed.p} target={profile.protein_target_g} color="green" />
          <MacroRing label={t("coach_carbs")} current={consumed.c} target={profile.carb_target_g} color="blue" />
          <MacroRing label={t("coach_fat")} current={consumed.f} target={profile.fat_target_g} color="amber" />
        </div>
      </div>

      {/* Daily health check-in */}
      <HealthCheckIn />

      {/* Calculator CTA */}
      <Link to="/calculator" className="block">
        <div className="flex items-center gap-3 rounded-2xl border-2 border-accent/30 bg-accent/5 p-4 hover:bg-accent/10 transition-colors">
          <div className="w-10 h-10 rounded-full bg-accent/15 flex items-center justify-center">
            <Calculator className="w-5 h-5 text-accent" />
          </div>
          <div className="flex-1">
            <p className="font-heading text-sm">{t("home_calcTargets")}</p>
            <p className="text-[11px] text-muted-foreground">{t("home_calcSub")}</p>
          </div>
          <span className="text-accent text-lg">⚔️</span>
        </div>
      </Link>

      {/* AI tip — the oracle */}
      <div className="rounded-2xl border-2 border-primary/20 bg-gradient-to-br from-primary/5 to-accent/5 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="w-4 h-4 text-primary" />
          <span className="text-[11px] font-semibold text-primary uppercase tracking-[0.2em] font-display">Oracle</span>
        </div>
        {loadingTip ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t("home_consulting")}
          </div>
        ) : (
          <p className="text-sm font-heading leading-relaxed">{aiTip || t("home_oracle")}</p>
        )}
        <Button size="sm" variant="outline" className="mt-3 h-8 text-xs bg-card" onClick={() => navigate("/coach")}>
          {t("home_getMealIdeas")}
        </Button>
      </div>

      {/* Проактивный анализ привычек — не ждёт вопроса от пользователя */}
      {(loadingHabit || habitInsight?.suggestion) && (
        <div className="rounded-2xl border-2 border-accent/20 bg-gradient-to-br from-accent/5 to-transparent p-4">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles className="w-4 h-4 text-accent" />
            <span className="text-[11px] font-semibold text-accent uppercase tracking-[0.2em] font-display">
              {t("home_noticed") || "Заметила"}
            </span>
          </div>
          {loadingHabit ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> {t("home_analyzing") || "Анализирую привычки..."}
            </div>
          ) : (
            <p className="text-sm font-heading leading-relaxed">{habitInsight.suggestion}</p>
          )}
        </div>
      )}

      {/* Weight trend */}
      {weights.length > 1 && (
        <div className="bg-card rounded-2xl border border-border p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground">{t("home_weightTrend")}</span>
            <span className={`flex items-center gap-0.5 text-xs font-medium ${weightTrend < 0 ? "text-emerald-600" : weightTrend > 0 ? "text-rose-500" : "text-muted-foreground"}`}>
              {weightTrend < 0 ? <TrendingDown className="w-3 h-3" /> : weightTrend > 0 ? <TrendingUp className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
              {Math.abs(weightTrend).toFixed(1)} kg
            </span>
          </div>
          <ResponsiveContainer width="100%" height={60}>
            <LineChart data={weightData}>
              <YAxis domain={["dataMin - 0.5", "dataMax + 0.5"]} hide />
              <Line type="monotone" dataKey="val" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Today's meals */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg">{t("home_todaysFeasts")}</h2>
          <Button size="sm" className="h-8 text-xs" onClick={() => setShowLogMeal(true)}>
            <Plus className="w-3.5 h-3.5 mr-1" /> {t("home_log")}
          </Button>
        </div>
        {meals.length === 0 ? (
          <div className="bg-card rounded-2xl border border-border p-6 text-center">
            <p className="text-sm text-muted-foreground">{t("home_emptyMeals")}</p>
            <Button size="sm" variant="outline" className="mt-3 h-8 text-xs" onClick={() => setShowLogMeal(true)}>
              {t("home_logFirst")}
            </Button>
          </div>
        ) : (
          <div className="bg-card rounded-2xl border border-border px-4">
            {meals.map((m) => (
              <MealCard key={m.id} meal={m} onDelete={handleDeleteMeal} compact />
            ))}
          </div>
        )}
      </div>

      <LogMealDialog open={showLogMeal} onOpenChange={setShowLogMeal} onLogged={handleMealLogged} />
    </div>
  );
}
