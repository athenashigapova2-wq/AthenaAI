"""Calendar-like tools for cycle-aware coaching."""

from datetime import date as date_type, timedelta
from typing import Any

from app.services.supabase import get_supabase


def get_cycle_logs(user_id: str, days: int = 45) -> dict[str, Any]:
    """Returns opt-in cycle tracker entries for recovery planning."""
    days = max(1, min(days, 120))
    start_day = (date_type.today() - timedelta(days=days - 1)).isoformat()
    result = (
        get_supabase()
        .table("cycle_logs")
        .select("date, flow, symptoms, notes")
        .eq("user_id", user_id)
        .gte("date", start_day)
        .order("date", desc=True)
        .execute()
    )
    return {"status": "ok", "days": days, "logs": result.data or []}
