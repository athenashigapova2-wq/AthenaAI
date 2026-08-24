export const GOALS = [
  { key: "lose_weight", labelKey: "goal_lose", subKey: "goal_lose_sub" },
  { key: "maintain", labelKey: "goal_maintain", subKey: "goal_maintain_sub" },
  { key: "gain_muscle", labelKey: "goal_gain", subKey: "goal_gain_sub" },
  { key: "recomp", labelKey: "goal_recomp", subKey: "goal_recomp_sub" },
];

export const DIETARY_PATTERNS = ["omnivore", "vegetarian", "vegan", "pescatarian"];
export const DIETARY_RESTRICTIONS = ["halal", "kosher", "lactose_free", "gluten_free"];

const GOAL_CONFIG = {
  lose_weight: { delta: -550, proteinPerKg: 1.8 },
  maintain: { delta: 0, proteinPerKg: 1.8 },
  gain_muscle: { delta: 400, proteinPerKg: 2 },
  recomp: { delta: -250, proteinPerKg: 2.2 },
};

export function calculateGoalTargets({ weight, height, age, sex, goal }) {
  if (!weight || !height || !age || !sex) return null;
  const config = GOAL_CONFIG[goal];
  const maleBmr = 10 * weight + 6.25 * height - 5 * age + 5;
  const femaleBmr = 10 * weight + 6.25 * height - 5 * age - 161;
  const bmr = sex === "male" ? maleBmr : sex === "female" ? femaleBmr : (maleBmr + femaleBmr) / 2;
  const calories = Math.round(bmr * 1.55 + config.delta);
  const protein = Math.round(weight * config.proteinPerKg);
  const fat = Math.round((calories * 0.25) / 9);
  const carbs = Math.round((calories - protein * 4 - fat * 9) / 4);
  return { calorie_target: calories, protein_target_g: protein, carb_target_g: carbs, fat_target_g: fat };
}
