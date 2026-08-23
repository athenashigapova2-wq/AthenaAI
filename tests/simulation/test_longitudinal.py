"""Offline longitudinal simulation with frozen application time and mock LLM."""

import pytest

from scripts import test_longitudinal_simulation as simulation_checks


pytestmark = pytest.mark.simulation


def test_profiles_and_generation() -> None:
    report = simulation_checks.check_profiles_and_generation()
    assert report


def test_timeline_and_date_sensitive_tools() -> None:
    report = simulation_checks.check_timeline_and_date_sensitive_tools()
    assert report


def test_mock_agent_replay() -> None:
    report = simulation_checks.check_mock_agent_replay()
    assert report["external_llm_calls"] == 0

