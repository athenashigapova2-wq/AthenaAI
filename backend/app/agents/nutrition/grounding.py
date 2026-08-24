"""Server-owned fallback food sets used by the nutrition planner."""

from app.agents.nutrition_validation import GroundedMealPlanItem

# The model may choose a nutritionally incompatible ingredient set even when every
# individual food exists in the catalogue. These bounded server-owned templates let
# the validator change the food set (not merely the grams) without inventing foods or
# paying for another LLM call. Every candidate still goes through database grounding,
# portion fitting, allergy checks, diversity checks, and target validation.
_ALTERNATIVE_PLAN_TEMPLATES: tuple[
    tuple[str, tuple[tuple[str, tuple[str, ...]], ...]], ...
] = (
    (
        "balanced_lean",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("greek yogurt", "cucumber")),
            (
                "Lunch",
                ("chicken breast raw", "white rice cooked", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "buckwheat raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "turkey_potato",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("yogurt", "cucumber")),
            (
                "Lunch",
                ("turkey breast roasted", "white rice cooked", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "potato raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "higher_energy",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("greek yogurt", "cucumber")),
            (
                "Lunch",
                (
                    "beef tenderloin steak cooked",
                    "white rice cooked",
                    "broccoli cooked",
                    "olive oil",
                ),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("salmon raw", "buckwheat raw", "spinach raw", "olive oil")),
        ),
    ),
    (
        "low_budget",
        (
            ("Breakfast", ("oats", "egg raw", "banana")),
            ("Snack 1", ("yogurt", "cucumber")),
            (
                "Lunch",
                ("chicken breast raw", "white rice raw", "broccoli cooked", "olive oil"),
            ),
            ("Snack 2", ("cottage cheese nonfat", "carrots raw")),
            ("Dinner", ("cod cooked", "potato raw", "spinach raw", "olive oil")),
        ),
    ),
)


def _alternative_plan_candidates(
    locale: str,
    *,
    low_budget: bool,
) -> list[tuple[str, list[GroundedMealPlanItem]]]:
    """Build deterministic candidate plans in profile-aware priority order."""
    templates = list(_ALTERNATIVE_PLAN_TEMPLATES)
    if low_budget:
        templates.sort(key=lambda item: item[0] != "low_budget")
    ru_names = ("Завтрак", "Перекус 1", "Обед", "Перекус 2", "Ужин")
    candidates: list[tuple[str, list[GroundedMealPlanItem]]] = []
    for template_name, meal_specs in templates:
        meals = [
            GroundedMealPlanItem.model_validate(
                {
                    "name": ru_names[index] if locale == "ru" else meal_name,
                    "ingredients": [
                        {"reference_food": food, "grams": 100.0}
                        for food in foods
                    ],
                }
            )
            for index, (meal_name, foods) in enumerate(meal_specs)
        ]
        candidates.append((template_name, meals))
    return candidates
