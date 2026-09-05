"""Recovery tools: health check-ins and body-weight trend."""

from datetime import date as date_type, timedelta
from typing import Any

from app.services.supabase import get_supabase


def get_recovery_logs(user_id: str, days: int = 14) -> dict[str, Any]:
    """Returns sleep, energy, mood and symptom check-ins."""
    days = max(1, min(days, 60))
    start_day = (date_type.today() - timedelta(days=days - 1)).isoformat()
    result = (
        get_supabase()
        .table("user_health_logs")
        .select("date, sleep_hours, energy_level, mood, symptoms, notes")
        .eq("user_id", user_id)
        .gte("date", start_day)
        .order("date", desc=True)
        .execute()
    )
    return {"status": "ok", "days": days, "logs": result.data or []}


def get_weight_trend(user_id: str, days: int = 30) -> dict[str, Any]:
    """Returns recent weight entries; the model can explain trends without guessing."""
    days = max(1, min(days, 180))
    start_day = (date_type.today() - timedelta(days=days - 1)).isoformat()
    result = (
        get_supabase()
        .table("weight_logs")
        .select("date, weight_kg, notes")
        .eq("user_id", user_id)
        .gte("date", start_day)
        .order("date")
        .execute()
    )
    weights = result.data or []
    delta = None
    if len(weights) >= 2:
        delta = round(float(weights[-1]["weight_kg"]) - float(weights[0]["weight_kg"]), 2)
    return {"status": "ok", "days": days, "delta_kg": delta, "weights": weights}
