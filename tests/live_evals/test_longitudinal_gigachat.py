"""Live scenario quality suite; excluded unless both opt-in gates are enabled."""

import pytest

from scripts.eval_longitudinal_quality import run


pytestmark = pytest.mark.live


def test_selected_longitudinal_scenarios_live() -> None:
    report = run()
    assert report["provider"] == "gigachat"
    assert report["remote_supabase_writes"] == 0
    assert report["scenario_count"] > 0
    assert report["scenarios_passed"] == report["scenario_count"], report["scenarios"]
