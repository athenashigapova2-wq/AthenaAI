from types import SimpleNamespace

from app.services import habit_analytics
from app.services.habit_analytics import HabitAnalyticsService


class FakeQuery:
    def __init__(self, rows, calls):
        self.rows = rows
        self.calls = calls

    def select(self, columns):
        self.calls.append(("select", columns))
        return self

    def eq(self, field, value):
        self.calls.append(("eq", field, value))
        return self

    def gte(self, field, value):
        self.calls.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self.calls.append(("lte", field, value))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeSupabase:
    def __init__(self):
        self.calls = []
        self.rows = {
            "meal_logs": [
                {
                    "name": "Oats 50g",
                    "date": "2026-08-12",
                    "calories": 200,
                    "protein_g": 8,
                    "carbs_g": 35,
                    "fat_g": 4,
                },
                {
                    "name": "Oats 60 g",
                    "date": "2026-08-13",
                    "calories": 220,
                    "protein_g": 9,
                    "carbs_g": 40,
                    "fat_g": 4,
                },
                {
                    "name": "Salmon",
                    "date": "2026-08-13",
                    "calories": 300,
                    "protein_g": 30,
                    "carbs_g": 0,
                    "fat_g": 18,
                },
            ],
            "user_profiles": [{"protein_target_g": 100, "carb_target_g": 200, "fat_target_g": 60}],
        }

    def table(self, name):
        self.calls.append(("table", name))
        return FakeQuery(self.rows[name], self.calls)


def test_habit_analytics_is_owner_scoped_and_deterministic(monkeypatch) -> None:
    fake = FakeSupabase()
    monkeypatch.setattr(habit_analytics, "get_supabase", lambda: fake)
    result = HabitAnalyticsService().analyze("user-123", today=habit_analytics.date(2026, 8, 14))
    assert result is not None
    assert result.period_start.isoformat() == "2026-08-01"
    assert result.period_end.isoformat() == "2026-08-14"
    assert result.frequent_foods[0] == "oats"
    assert result.day_count == 2
    assert result.average_daily.calories == 360.0
    assert result.macro_gap == "carbs:under"
    assert fake.calls.count(("eq", "user_id", "user-123")) == 2


def test_habit_analytics_refuses_to_infer_from_too_little_data(monkeypatch) -> None:
    fake = FakeSupabase()
    fake.rows["meal_logs"] = fake.rows["meal_logs"][:2]
    monkeypatch.setattr(habit_analytics, "get_supabase", lambda: fake)
    assert HabitAnalyticsService().analyze("user-123") is None
