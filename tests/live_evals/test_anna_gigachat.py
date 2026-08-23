"""Live Anna quality evaluation. This module is excluded from normal pytest runs."""

import pytest

from scripts.eval_anna_longitudinal_quality import run


pytestmark = pytest.mark.live


def test_anna_longitudinal_quality_live() -> None:
    report = run()
    assert report["provider"] == "gigachat"
    assert report["checkpoints_total"] > 0
    assert report["checkpoints_passed"] == report["checkpoints_total"]

