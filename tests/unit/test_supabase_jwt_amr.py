from app.auth.supabase_jwt import _latest_direct_authentication


def test_latest_direct_authentication_ignores_newer_token_refresh() -> None:
    assert _latest_direct_authentication(
        [
            {"method": "password", "timestamp": 100},
            {"method": "token_refresh", "timestamp": 900},
        ]
    ) == 100


def test_latest_direct_authentication_accepts_fresh_oauth_round_trip() -> None:
    assert _latest_direct_authentication(
        [
            {"method": "oauth", "timestamp": 800},
            {"method": "token_refresh", "timestamp": 900},
        ]
    ) == 800


def test_missing_or_malformed_amr_never_proves_recent_authentication() -> None:
    assert _latest_direct_authentication(None) is None
    assert _latest_direct_authentication([{"method": "password"}]) is None
