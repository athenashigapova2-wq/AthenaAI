import React, { useState } from "react";
import { entities } from '@/lib/entities';
import { invokeLLM } from '@/lib/invokeLLM';
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Loader2, Sparkles, Footprints, Utensils, Moon, HeartPulse, Flame } from "lucide-react";
import ResponsiveSelect from "@/components/ResponsiveSelect";
import { useLang } from "@/lib/i18n";
import { WHAT_OPTIONS, INTENSITY_OPTIONS, WHERE_OPTIONS, WHAT_TO_WORKOUT_TYPE } from "@/lib/workoutData";
import { toast } from "@/components/ui/use-toast";

const today = () => new Date().toISOString().split("T")[0];

export default function GymGenerator() {
  const { t, lang } = useLang();
  const [where, setWhere] = useState("commercial_gym");
  const [what, setWhat] = useState("upper_body");
  const [intensity, setIntensity] = useState("moderate");
  const [workout, setWorkout] = useState(null);
  const [loading, setLoading] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [doneMsg, setDoneMsg] = useState(null);

  const generate = async () => {
    setLoading(true);
    setWorkout(null);
    try {
      const focus = WHAT_OPTIONS.find((o) => o.value === what)?.labelEn;
      const whereLabel = WHERE_OPTIONS.find((o) => o.value === where)?.labelEn;
      const res = await invokeLLM({
        prompt: `You are Athena, an expert strength coach. Build ONE gym workout session.
Setting: ${whereLabel}.
Focus: ${focus}.
Intensity: ${intensity}.
Estimate realistic calories_burned for this session and duration_min.
Respond ENTIRELY in this language code: ${lang}. Return JSON only.`,
        response_json_schema: {
          type: "object",
          properties: {
            title: { type: "string" },
            exercises: {
              type: "array",
              items: {
                type: "object",
                properties: { name: { type: "string" }, sets: { type: "string" }, reps: { type: "string" } },
              },
            },
            calories_burned: { type: "number" },
            duration_min: { type: "number" },
            recovery: {
              type: "object",
              properties: { steps: { type: "string" }, eat: { type: "string" }, sleep: { type: "string" }, stretch: { type: "string" } },
            },
          },
          required: ["title", "exercises", "recovery"],
        },
      });
      setWorkout(res);
    } catch {
      toast({ title: "Athena couldn't generate", variant: "destructive" });
    }
    setLoading(false);
  };

  const completeWorkout = async () => {
    if (!workout) return;
    setCompleting(true);
    try {
      const wtype = WHAT_TO_WORKOUT_TYPE[what] || "full_body";
      const burned = Math.round(workout.calories_burned || 0);
      await entities.WorkoutLog.create({
        workout_type: wtype,
        date: today(),
        duration_min: workout.duration_min || null,
        exercises: (workout.exercises || []).map((ex) => ({
          name: ex.name,
          sets: parseInt(ex.sets) || 0,
          reps: ex.reps || "",
        })),
        notes: `${workout.title} · ${intensity}`,
        calories_burned: burned,
      });
      setDoneMsg({ title: t("workout_doneTitle"), desc: t("workout_logged", { n: burned }) });
      setWorkout(null);
      setTimeout(() => setDoneMsg(null), 2600);
    } catch {
      toast({ title: "Error", variant: "destructive" });
    }
    setCompleting(false);
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t("workout_gymDesc")}</p>

      <div className="space-y-3 bg-card rounded-2xl border border-border p-4">
        <div className="space-y-1.5">
          <Label className="text-xs">{t("workout_where")}</Label>
          <ResponsiveSelect
            value={where}
            onValueChange={setWhere}
            options={WHERE_OPTIONS.map((o) => ({ value: o.value, label: t(o.key) }))}
            placeholder="—"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("workout_what")}</Label>
          <ResponsiveSelect
            value={what}
            onValueChange={setWhat}
            options={WHAT_OPTIONS.map((o) => ({ value: o.value, label: t(o.key) }))}
            placeholder="—"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">{t("workout_intensity")}</Label>
          <div className="grid grid-cols-3 gap-2">
            {INTENSITY_OPTIONS.map((o) => {
              const active = intensity === o.value;
              return (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => setIntensity(o.value)}
                  className={`relative flex flex-col items-center gap-0.5 rounded-xl p-2.5 border-2 transition-colors ${
                    active ? "border-primary bg-primary/5 text-primary" : "border-border bg-card text-muted-foreground hover:border-primary/40"
                  }`}
                >
                  <span className="text-xs font-medium">{t(o.key)}</span>
                  {o.recommended && (
                    <span className="absolute -top-2 right-1 text-[8px] font-semibold px-1.5 py-0.5 rounded-full bg-accent text-accent-foreground whitespace-nowrap shadow-sm">
                      {t("workout_recommended")}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
        <Button className="w-full h-11" onClick={generate} disabled={loading}>
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
          {loading ? t("workout_generating") : t("workout_generate")}
        </Button>
      </div>

      {workout && (
        <div className="space-y-3">
          <div className="bg-card rounded-2xl border-2 border-primary/30 p-4">
            <div className="flex items-center justify-between gap-2">
              <p className="font-heading text-base">{workout.title}</p>
              {workout.calories_burned != null && (
                <span className="flex items-center gap-1 text-xs font-medium text-accent bg-accent/10 px-2 py-1 rounded-full whitespace-nowrap">
                  <Flame className="w-3.5 h-3.5" /> {Math.round(workout.calories_burned)} {t("week_cal")}
                </span>
              )}
            </div>
            <ul className="mt-2 space-y-1.5">
              {workout.exercises?.map((ex, i) => (
                <li key={i} className="text-sm flex justify-between gap-2">
                  <span>{ex.name}</span>
                  <span className="text-muted-foreground whitespace-nowrap">{ex.sets} × {ex.reps}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="bg-card rounded-2xl border-2 border-accent/25 p-4 space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-accent flex items-center gap-1.5">
              <HeartPulse className="w-3.5 h-3.5" /> {t("workout_recovery")}
            </p>
            <RecRow icon={Footprints} label={t("workout_stepsWalk")} value={workout.recovery?.steps} />
            <RecRow icon={Utensils} label={t("workout_eat")} value={workout.recovery?.eat} />
            <RecRow icon={Moon} label={t("workout_sleep")} value={workout.recovery?.sleep} />
            <RecRow icon={HeartPulse} label={t("workout_stretch")} value={workout.recovery?.stretch} />
          </div>
          <Button className="w-full h-11" onClick={completeWorkout} disabled={completing}>
            {completing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Flame className="w-4 h-4" />}
            {completing ? t("workout_generating") : t("workout_complete")}
          </Button>
        </div>
      )}

      {doneMsg && (
        <div className="fixed inset-0 z-50 flex items-center justify-center pointer-events-none px-4">
          <div className="bg-card/95 backdrop-blur-sm border-2 border-primary/30 rounded-3xl px-6 py-5 text-center shadow-xl max-w-xs">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-2">
              <Flame className="w-6 h-6 text-primary" />
            </div>
            <p className="font-heading text-lg">{doneMsg.title}</p>
            <p className="text-sm text-muted-foreground mt-1">{doneMsg.desc}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function RecRow({ icon: Icon, label, value }) {
  return (
    <div className="flex gap-2.5">
      <Icon className="w-4 h-4 text-accent shrink-0 mt-0.5" />
      <div>
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="text-sm leading-relaxed">{value}</p>
      </div>
    </div>
  );
}