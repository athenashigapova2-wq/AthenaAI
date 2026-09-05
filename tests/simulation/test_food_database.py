from pathlib import Path
from unittest.mock import patch

import pytest

from app.tools.nutrition import PLAN_FOOD_REFERENCE_NAMES, lookup_food_reference
from simulation.food_database import TestFoodDatabase as FoodDatabase


@pytest.mark.simulation
def test_food_fixture_covers_planner_catalogue() -> None:
    database = FoodDatabase.from_fixture()
    rows = database.table("food_nutrients").select("food_name").execute().data

    assert {row["food_name"] for row in rows} == set(PLAN_FOOD_REFERENCE_NAMES)


@pytest.mark.simulation
def test_food_lookup_uses_read_only_simulation_database() -> None:
    database = FoodDatabase.from_fixture()

    with patch("app.tools.nutrition.get_food_reference_database", return_value=database):
        oats = lookup_food_reference("oats")
        assert oats == {
            "food_name": "oats",
            "calories_per_100g": 357.8,
            "protein_g": 15.6,
            "carbs_g": 60.6,
            "fat_g": 6.4,
        }
        with pytest.raises(LookupError, match="exact food not found"):
            lookup_food_reference("oatmeal invented")


@pytest.mark.simulation
def test_food_database_rejects_non_catalogue_access_and_writes() -> None:
    database = FoodDatabase.from_fixture()

    with pytest.raises(PermissionError, match="does not expose"):
        database.table("user_profiles")
    with pytest.raises(PermissionError, match="read-only"):
        database.table("food_nutrients").insert({"food_name": "invented"})


@pytest.mark.simulation
def test_food_fixture_is_repository_local() -> None:
    fixture = Path(__file__).parents[2] / "backend/simulation/fixtures/test_food_nutrients.json"
    assert fixture.is_file()
