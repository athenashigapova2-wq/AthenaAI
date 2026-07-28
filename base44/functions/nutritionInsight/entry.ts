import { createClientFromRequest } from 'npm:@base44/sdk@0.8.40';

// Deterministic nutrition logic — the agent calls this instead of reasoning
// from raw entity data, so the "decision chain" lives in code, not the LLM.
export default async function(req) {
  try {
    const base44 = createClientFromRequest(req);
    const user = await base44.auth.me();
    if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 });

    const today = new Date().toISOString().split('T')[0];
    const [profiles, meals] = await Promise.all([
      base44.entities.UserProfile.filter({ created_by_id: user.id }),
      base44.entities.MealLog.filter({ date: today, created_by_id: user.id }),
    ]);
    const profile = profiles[0];
    if (!profile) return Response.json({ error: 'no_profile' }, { status: 404 });

    const consumed = meals.reduce(
      (a, m) => ({
        cal: a.cal + (m.calories || 0),
        p: a.p + (m.protein_g || 0),
        c: a.c + (m.carbs_g || 0),
        f: a.f + (m.fat_g || 0),
      }),
      { cal: 0, p: 0, c: 0, f: 0 }
    );

    const targets = {
      calories: profile.calorie_target || 0,
      protein: profile.protein_target_g || 0,
      carbs: profile.carb_target_g || 0,
      fat: profile.fat_target_g || 0,
    };

    const remaining = {
      calories: Math.max(targets.calories - consumed.cal, 0),
      protein: Math.max(targets.protein - consumed.p, 0),
      carbs: Math.max(targets.carbs - consumed.c, 0),
      fat: Math.max(targets.fat - consumed.f, 0),
    };

    const overCalories = consumed.cal > targets.calories;

    // Logical chain: which macro has the biggest relative gap to target?
    const gaps = [
      { macro: 'protein', ratio: remaining.protein / (targets.protein || 1) },
      { macro: 'carbs', ratio: remaining.carbs / (targets.carbs || 1) },
      { macro: 'fat', ratio: remaining.fat / (targets.fat || 1) },
    ].sort((a, b) => b.ratio - a.ratio);
    const priorityMacro = gaps[0].macro;

    const verdict = overCalories
      ? 'over_target'
      : remaining.calories === 0
        ? 'on_target'
        : 'under_target';

    return Response.json({
      date: today,
      consumed,
      targets,
      remaining,
      over_calories: overCalories,
      verdict,
      priority_macro: priorityMacro,
      meal_count: meals.length,
    });
  } catch (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }
}