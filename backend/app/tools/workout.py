"""Workout tools: training history, simple planning inputs and workout logging."""

from datetime import date as date_type, timedelta
from typing import Any

from app.services.supabase import get_supabase
from app.tools.idempotent_writes import insert_idempotently
from app.tools.write_context import require_idempotency_key


_ALLOWED_WORKOUT_TYPES = {
    "upper_body", "lower_body", "full_body", "functional", "crossfit", "cardio", "rest",
}


def get_workout_history(user_id: str, days: int = 14) -> dict[str, Any]:
    """Returns recent workouts for safe progression and volume decisions."""
    days = max(1, min(days, 60))
    start_day = (date_type.today() - timedelta(days=days - 1)).isoformat()
    result = (
        get_supabase().table("workout_logs")
        .select("date, workout_type, duration_min, calories_burned, exercises, notes")
        .eq("user_id", user_id)
        .gte("date", start_day)
        .order("date", desc=True)
        .execute()
    )
    return {"status": "ok", "days": days, "workouts": result.data or []}


def log_workout(
    user_id: str,
    workout_type: str,
    duration_min: float | None = None,
    exercises: list[dict[str, Any]] | None = None,
    calories_burned: float | None = None,
    notes: str | None = None,
    day: str | None = None,
) -> dict[str, Any]:
    """Writes a workout only after an explicit user request."""
    if workout_type not in _ALLOWED_WORKOUT_TYPES:
        return {"status": "error", "message": f"workout_type must be one of {sorted(_ALLOWED_WORKOUT_TYPES)}"}
    if duration_min is not None and duration_min < 0:
        return {"status": "error", "message": "duration_min cannot be negative"}

    payload = {
        "user_id": user_id,
        "workout_type": workout_type,
        "duration_min": duration_min,
        "calories_burned": calories_burned,
        "exercises": exercises or [],
        "notes": notes,
        "date": day or date_type.today().isoformat(),
    }
    _, replayed = insert_idempotently(
        get_supabase(),
        "workout_logs",
        payload,
        require_idempotency_key(),
    )
    return {
        "status": "ok",
        "workout_type": workout_type,
        "date": payload["date"],
        "idempotent_replay": replayed,
    }
