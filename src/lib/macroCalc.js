export const ACTIVITY_OPTIONS = [
  { value: "sedentary", labelKey: "act_sedentary" },
  { value: "light", labelKey: "act_light" },
  { value: "moderate", labelKey: "act_moderate" },
  { value: "active", labelKey: "act_active" },
  { value: "very", labelKey: "act_very" },
];

export const ACTIVITY_FACTOR = { sedentary: 1.2, light: 1.375, moderate: 1.55, active: 1.725, very: 1.9 };

export const stepsToActivity = (s) =>
  s < 5000 ? "sedentary" : s < 7500 ? "light" : s < 10000 ? "moderate" : s < 12500 ? "active" : "very";

export const round = (n) => Math.round(n);

export const isNonNegativeFinite = (value) => Number.isFinite(value) && value >= 0;

export const calculateMacroCalories = (protein, carbs, fat) => {
  if (![protein, carbs, fat].every(isNonNegativeFinite)) {
    throw new RangeError("Nutrition values must be finite and non-negative");
  }
  return protein * 4 + carbs * 4 + fat * 9;
};

export const carbsForCalories = (calories, protein, fat, minimum = 0) => {
  if (![calories, protein, fat, minimum].every(isNonNegativeFinite)) {
    throw new RangeError("Nutrition values must be finite and non-negative");
  }
  return Math.max(round((calories - calculateMacroCalories(protein, 0, fat)) / 4), minimum);
};

export const isValidNutritionValues = ({ calories, protein, carbs, fat }) =>
  [calories, protein, carbs, fat].every(isNonNegativeFinite);

export const macrosFor = (cal, w) => {
  const protein = round(w * 1.8);
  const fat = round((cal * 0.25) / 9);
  const carbs = carbsForCalories(cal, protein, fat);
  return { protein, carbs, fat };
};

export const VARIANTS = [
  { key: "light_loss", labelKey: "v_light_loss", subKey: "v_light_sub", emoji: "🪶", delta: -550 },
  { key: "maintenance", labelKey: "v_maintain", subKey: "v_maintain_sub", emoji: "⚖️", delta: 0 },
  { key: "aggressive", labelKey: "v_aggressive", subKey: "v_aggressive_sub", emoji: "🔥", delta: -880 },
  { key: "bulking", labelKey: "v_bulking", subKey: "v_bulking_sub", emoji: "💪", delta: 400 },
];
