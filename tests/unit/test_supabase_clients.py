"""Thread-local Supabase client guarantees used by Celery thread workers."""

import pytest

from scripts import test_supabase_thread_local as client_checks


pytestmark = pytest.mark.unit


def test_one_client_per_thread() -> None:
    client_checks.assert_one_client_per_thread()


def test_missing_configuration_fails() -> None:
    client_checks.assert_missing_configuration_still_fails()
