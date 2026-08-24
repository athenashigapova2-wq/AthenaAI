"""Core contract for layered, high-confidence conversation memory."""

import pytest

from scripts import test_agent_memory as memory_checks


pytestmark = pytest.mark.unit


def test_layered_agent_memory_contract() -> None:
    memory_checks.main()
