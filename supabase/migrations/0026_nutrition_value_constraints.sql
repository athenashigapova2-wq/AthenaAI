-- Enforce the same universal nutrition invariant at the durable boundary:
-- calorie and macronutrient values must be non-negative finite numbers.

alter table public.user_profiles
  add constraint user_profiles_nutrition_nonnegative_check check (
    calorie_target >= 0 and calorie_target <> 'NaN'::numeric
    and protein_target_g >= 0 and protein_target_g <> 'NaN'::numeric
    and carb_target_g >= 0 and carb_target_g <> 'NaN'::numeric
    and fat_target_g >= 0 and fat_target_g <> 'NaN'::numeric
  ) not valid;

alter table public.meal_logs
  add constraint meal_logs_nutrition_nonnegative_check check (
    calories >= 0 and calories <> 'NaN'::numeric
    and protein_g >= 0 and protein_g <> 'NaN'::numeric
    and carbs_g >= 0 and carbs_g <> 'NaN'::numeric
    and fat_g >= 0 and fat_g <> 'NaN'::numeric
  ) not valid;

alter table public.food_nutrients
  add constraint food_nutrients_nutrition_nonnegative_check check (
    (calories_per_100g is null or (
      calories_per_100g >= 0 and calories_per_100g <> 'NaN'::numeric
    ))
    and (protein_g is null or (protein_g >= 0 and protein_g <> 'NaN'::numeric))
    and (carbs_g is null or (carbs_g >= 0 and carbs_g <> 'NaN'::numeric))
    and (fat_g is null or (fat_g >= 0 and fat_g <> 'NaN'::numeric))
  ) not valid;

alter table public.custom_products
  add constraint custom_products_nutrition_nonnegative_check check (
    (calories is null or (calories >= 0 and calories <> 'NaN'::numeric))
    and (protein_g is null or (protein_g >= 0 and protein_g <> 'NaN'::numeric))
    and (carbs_g is null or (carbs_g >= 0 and carbs_g <> 'NaN'::numeric))
    and (fat_g is null or (fat_g >= 0 and fat_g <> 'NaN'::numeric))
  ) not valid;

alter table public.user_profiles
  validate constraint user_profiles_nutrition_nonnegative_check;
alter table public.meal_logs
  validate constraint meal_logs_nutrition_nonnegative_check;
alter table public.food_nutrients
  validate constraint food_nutrients_nutrition_nonnegative_check;
alter table public.custom_products
  validate constraint custom_products_nutrition_nonnegative_check;
