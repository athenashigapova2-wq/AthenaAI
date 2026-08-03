import React, { useState, useEffect, useRef } from "react";
import { toLocalDateString } from "@/lib/utils";
import { entities } from '@/lib/entities';
import { useAuth } from "@/lib/AuthContext";
import { useLang } from "@/lib/i18n";
import { Flame, ChevronLeft, ChevronRight } from "lucide-react";

const dateStr = (d) => toLocalDateString(d);

export default function WeekHistory({ profile }) {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const [days, setDays] = useState([]);
  const [loading, setLoading] = useState(true);
  const [weekOffset, setWeekOffset] = useState(0); // 0 = текущая неделя, -1 = прошлая, +1 = следующая
  const [selectedDs, setSelectedDs] = useState(null); // выбранный день (для разворачивания деталей)
  const dataRef = useRef(null); // кэш { mealByDate, workoutByDate } на время сессии компонента

  useEffect(() => {
    (async () => {
      try {
        // Тянем с запасом по обе стороны от текущей недели, чтобы пролистывание
        // не требовало нового похода в БД каждый раз
        const [meals, workouts, healthLogs] = await Promise.all([
          entities.MealLog.filter({ created_by_id: user?.id }, "-date", 400),
          entities.WorkoutLog.filter({ created_by_id: user?.id }, "-date", 200),
          entities.user_health_logs.filter({ created_by_id: user?.id }, "-date", 200),
        ]);
        const mealByDate = {};
        meals.forEach((m) => {
          if (!mealByDate[m.date]) mealByDate[m.date] = { cal: 0, p: 0, c: 0, f: 0 };
          mealByDate[m.date].cal += m.calories || 0;
          mealByDate[m.date].p += m.protein_g || 0;
          mealByDate[m.date].c += m.carbs_g || 0;
          mealByDate[m.date].f += m.fat_g || 0;
        });
        const workoutByDate = {};
        workouts.forEach((w) => {
          if (!workoutByDate[w.date]) workoutByDate[w.date] = { burned: 0, count: 0 };
          workoutByDate[w.date].burned += w.calories_burned || 0;
          workoutByDate[w.date].count += 1;
        });
        // Если чек-ин заполнялся несколько раз за день — берём последний по времени создания
        const healthByDate = {};
        healthLogs.forEach((h) => {
          const existing = healthByDate[h.date];
          if (!existing || new Date(h.created_at) > new Date(existing.created_at)) {
            healthByDate[h.date] = h;
          }
        });
        dataRef.current = { mealByDate, workoutByDate, healthByDate };
        setDays(buildWeek(weekOffset, mealByDate, workoutByDate, healthByDate));
      } catch {
        setDays([]);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (dataRef.current) setDays(buildWeek(weekOffset, dataRef.current.mealByDate, dataRef.current.workoutByDate, dataRef.current.healthByDate));
  }, [weekOffset]);

  function buildWeek(offset, mealByDate, workoutByDate, healthByDate) {
    const today = dateStr(new Date());
    const now = new Date();
    const monday = new Date(now);
    monday.setDate(now.getDate() - ((now.getDay() + 6) % 7) + offset * 7);
    const arr = [];
    for (let i = 0; i < 7; i++) {
      const dt = new Date(monday);
      dt.setDate(monday.getDate() + i);
      const ds = dateStr(dt);
      const meal = mealByDate[ds] || null;
      const workout = workoutByDate[ds] || null;
      const health = healthByDate?.[ds] || null;
      arr.push({
        date: dt, ds,
        isToday: ds === today,
        isPast: ds < today,
        meal, workout, health,
        hasRecords: !!(meal || workout),
      });
    }
    return arr;
  }

  const target = profile?.calorie_target || 0;
  const selectedDay = days.find((d) => d.ds === selectedDs) || null;

  const isRu = lang === "ru";

  function calorieVerdict(cal) {
    if (!target) return null;
    const diff = cal - target;
    const pct = diff / target;
    if (Math.abs(pct) <= 0.05) return isRu ? "уложилась в норму" : "right on target";
    if (diff > 0) return isRu ? `превысила норму на ${Math.round(diff)} ккал` : `over target by ${Math.round(diff)} kcal`;
    return isRu ? `недобрала ${Math.round(-diff)} ккал до нормы` : `under target by ${Math.round(-diff)} kcal`;
  }

  // Ключи симптомов из HealthCheckIn.jsx -> живая фраза для саммари.
  // "Вы могли чувствовать X" звучит естественно для любого симптома отсюда.
  const SYMPTOM_PHRASES = {
    Headache: isRu ? "головную боль" : "a headache",
    Bloating: isRu ? "вздутие живота" : "bloating",
    Fatigue: isRu ? "усталость" : "fatigue",
    Insomnia: isRu ? "бессонницу" : "insomnia",
    "Joint pain": isRu ? "боль в суставах" : "joint pain",
    "Skin issues": isRu ? "проблемы с кожей" : "skin issues",
    "Digestive issues": isRu ? "проблемы с пищеварением" : "digestive issues",
  };

  function joinNaturally(items) {
    if (items.length <= 1) return items[0] || "";
    return `${items.slice(0, -1).join(", ")} ${isRu ? "и" : "and"} ${items[items.length - 1]}`;
  }

  function daySummary(day) {
    const parts = [];
    if (day.meal) {
      const verdict = calorieVerdict(day.meal.cal);
      parts.push(
        isRu
          ? `Съедено ${Math.round(day.meal.cal)} ккал${verdict ? ` — ${verdict}` : ""}.`
          : `Ate ${Math.round(day.meal.cal)} kcal${verdict ? ` — ${verdict}` : ""}.`
      );
    }
    if (day.health) {
      const bits = [];
      if (day.health.mood != null) bits.push(isRu ? `настроение ${day.health.mood}/10` : `mood ${day.health.mood}/10`);
      if (day.health.sleep_hours != null) bits.push(isRu ? `сон ${day.health.sleep_hours}ч` : `sleep ${day.health.sleep_hours}h`);
      if (day.health.energy_level != null) bits.push(isRu ? `энергия ${day.health.energy_level}/10` : `energy ${day.health.energy_level}/10`);
      const symptomKeys = (day.health.symptoms || []).filter((s) => s && s !== "None");
      let sentence = (isRu ? "Самочувствие: " : "Wellbeing: ") + bits.join(", ") + ".";
      if (symptomKeys.length) {
        const phrases = symptomKeys.map((s) => SYMPTOM_PHRASES[s] || s.toLowerCase());
        sentence += isRu
          ? ` Вы могли чувствовать ${joinNaturally(phrases)}.`
          : ` You may have experienced ${joinNaturally(phrases)}.`;
      }
      parts.push(sentence);
    }
    return parts.join(" ");
  }

  const weekLabel = () => {
    if (!days.length) return "";
    const start = days[0].date, end = days[6].date;
    const fmt = (d) => d.toLocaleDateString(lang, { day: "numeric", month: "short" });
    return `${fmt(start)} – ${fmt(end)}`;
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-heading text-lg">{t("week_title")}</h2>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setWeekOffset((o) => o - 1)}
            className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-muted touch-target"
            aria-label={t("week_prev") || "Previous week"}
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-[11px] text-muted-foreground min-w-[92px] text-center">{weekLabel()}</span>
          <button
            onClick={() => setWeekOffset((o) => o + 1)}
            className="h-7 w-7 flex items-center justify-center rounded-lg hover:bg-muted touch-target"
            aria-label={t("week_next") || "Next week"}
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
        {days.map((d) => {
          const cal = d.meal?.cal || 0;
          const pct = target ? Math.min(Math.round((cal / target) * 100), 100) : 0;
          const isSelected = d.ds === selectedDs;
          return (
            <button
              key={d.ds}
              onClick={() => setSelectedDs(isSelected ? null : d.ds)}
              className={`shrink-0 w-[88px] rounded-2xl border-2 p-2.5 flex flex-col gap-1 text-left transition-colors ${
                isSelected ? "border-primary bg-primary/10" : d.isToday ? "border-accent bg-accent/10" : d.hasRecords ? "border-border bg-card" : "border-border bg-card/40"
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  {d.date.toLocaleDateString(lang, { weekday: "short" })}
                </span>
                {d.isPast && d.hasRecords && <span className="text-xs leading-none">🌟</span>}
                {d.isToday && <span className="text-[8px] font-semibold uppercase text-accent">{t("week_today")}</span>}
              </div>
              <span className={`text-base font-heading leading-none ${d.isToday ? "text-accent" : ""}`}>{d.date.getDate()}</span>
              {d.meal ? (
                <>
                  <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-primary rounded-full" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="text-[10px] text-muted-foreground leading-tight">{Math.round(cal)} {t("week_cal")}</span>
                  <span className="text-[9px] text-muted-foreground leading-tight">
                    {t("coach_protein")[0]}{Math.round(d.meal.p)} {t("coach_carbs")[0]}{Math.round(d.meal.c)} {t("coach_fat")[0]}{Math.round(d.meal.f)}
                  </span>
                </>
              ) : (
                <span className="text-[10px] text-muted-foreground/50">{t("week_empty")}</span>
              )}
              {d.workout && (
                <span className="flex items-center gap-0.5 text-[9px] text-accent font-medium leading-tight">
                  <Flame className="w-3 h-3 shrink-0" /> {Math.round(d.workout.burned)} {t("week_cal")}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {selectedDay && (
        <div className="mt-2 bg-card rounded-2xl border border-border p-3 text-sm">
          <p className="font-medium mb-1">{selectedDay.date.toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long" })}</p>
          {(selectedDay.meal || selectedDay.health) && (
            <p className="text-sm mb-2 leading-relaxed">{daySummary(selectedDay)}</p>
          )}
          {selectedDay.meal ? (
            <p className="text-muted-foreground">
              {Math.round(selectedDay.meal.cal)} {t("week_cal")} · {t("coach_protein")[0]}{Math.round(selectedDay.meal.p)}g {t("coach_carbs")[0]}{Math.round(selectedDay.meal.c)}g {t("coach_fat")[0]}{Math.round(selectedDay.meal.f)}g
            </p>
          ) : (
            <p className="text-muted-foreground/60">{t("week_empty")}</p>
          )}
          {selectedDay.workout && (
            <p className="text-accent flex items-center gap-1 mt-1">
              <Flame className="w-3.5 h-3.5" /> {Math.round(selectedDay.workout.burned)} {t("week_cal")} ({selectedDay.workout.count})
            </p>
          )}
        </div>
      )}
    </div>
  );
}
