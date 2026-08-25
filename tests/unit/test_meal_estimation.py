from app.services.meal_estimation import (
    CandidateChoice,
    FoodCandidate,
    MealEstimationService,
    ParsedMealDescription,
)


def test_meal_pipeline_uses_llm_only_for_parse_and_rerank() -> None:
    calls: list[str] = []

    def invoke(**kwargs):
        calls.append(kwargs["purpose"])
        if kwargs["response_model"] is ParsedMealDescription:
            return ParsedMealDescription(english_term="chicken breast", quantity_g=180)
        return CandidateChoice(food_name="chicken breast raw")

    service = MealEstimationService(structured_invoker=invoke)
    parsed = service.parse_description("180 г куриной грудки", "ru")
    candidates = [
        FoodCandidate(
            food_name="chicken breast raw",
            calories_per_100g=120,
            protein_g=23,
            carbs_g=0,
            fat_g=2.5,
        )
    ]
    matched = service.rerank_candidates(
        description="180 г куриной грудки",
        candidates=candidates,
        locale="ru",
    )
    assert matched is candidates[0]
    result = service.calculate_macros(matched, quantity_g=parsed.quantity_g, locale="ru")
    assert calls == ["parse_description", "rerank_candidates"]
    assert result.name == "Куриная грудка"
    assert result.matched_food == "chicken breast raw"
    assert result.calories == 216
    assert result.protein_g == 41.4


def test_reranker_cannot_invent_a_database_candidate() -> None:
    def invoke(**_kwargs):
        return CandidateChoice(food_name="invented food")

    service = MealEstimationService(structured_invoker=invoke)
    candidates = [
        FoodCandidate(
            food_name="cod cooked",
            calories_per_100g=90,
            protein_g=20,
            carbs_g=0,
            fat_g=1,
        )
    ]
    assert service.rerank_candidates(
        description="cod",
        candidates=candidates,
        locale="en",
    ) is None


def test_macro_calculation_is_deterministic() -> None:
    candidate = FoodCandidate(
        food_name="oats",
        calories_per_100g=380,
        protein_g=13,
        carbs_g=68,
        fat_g=7,
    )
    result = MealEstimationService.calculate_macros(
        candidate,
        quantity_g=50,
        locale="en",
    )
    assert result.model_dump() == {
        "matched": True,
        "name": "Oats",
        "matched_food": "oats",
        "quantity_g": 50.0,
        "calories": 190,
        "protein_g": 6.5,
        "carbs_g": 34.0,
        "fat_g": 3.5,
    }
