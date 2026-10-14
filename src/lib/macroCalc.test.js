import { describe, expect, it } from "vitest";

import {
  calculateMacroCalories,
  carbsForCalories,
  isValidNutritionValues,
  macrosFor,
} from "./macroCalc";

describe("nutrition policy", () => {
  it("uses one 4/4/9 macro calculation", () => {
    expect(calculateMacroCalories(20, 30, 10)).toBe(290);
  });

  it("never derives negative carbohydrates", () => {
    expect(carbsForCalories(100, 100, 20)).toBe(0);
    expect(macrosFor(100, 100).carbs).toBe(0);
  });

  it("rejects negative and non-finite nutrition values", () => {
    expect(isValidNutritionValues({ calories: 100, protein: -1, carbs: 10, fat: 5 })).toBe(false);
    expect(isValidNutritionValues({ calories: Number.NaN, protein: 1, carbs: 10, fat: 5 })).toBe(false);
    expect(() => calculateMacroCalories(10, -1, 5)).toThrow(RangeError);
  });
});
