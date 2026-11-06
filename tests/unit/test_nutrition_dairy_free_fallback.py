from app.agents.nutrition.planner import _plan_submission_tool
from app.agents.nutrition_validation import NutritionNumbers
from simulation.food_database import load_test_food_database


def _food_resolver(query: str) -> dict:
    database = load_test_food_database()
    rows = (
        database.table("food_nutrients")
        .select("*")
        .eq("food_name", query)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise LookupError(query)
    return rows[0]


def test_milk_allergy_recovers_with_validated_dairy_free_plan() -> None:
    tool = _plan_submission_tool(
        NutritionNumbers(calories=1800, protein_g=161, carbs_g=161, fat_g=57),
        "ru",
        {
            "status": "ok",
            "profile": {
                "allergies": ["milk"],
                "dietary_pattern": "omnivore",
                "dietary_restrictions": [],
                "budget": "medium",
            },
        },
        food_resolver=_food_resolver,
    )
    dairy_draft = {
        "meals": [
            {
                "name": name,
                "ingredients": [{"reference_food": "yogurt", "grams": 100}],
            }
            for name in ("Завтрак", "Перекус 1", "Обед", "Перекус 2", "Ужин")
        ]
    }

    result = tool.invoke(dairy_draft)

    assert result["status"] == "ok", result
    assert result["food_set_selection"] == "server:dairy_free_omnivore"
    matched_foods = {match["matched_food"] for match in result["database_matches"]}
    assert not matched_foods & {
        "greek yogurt",
        "yogurt",
        "cottage cheese nonfat",
    }
    assert result["constraint_validation"]["accepted"] is True
