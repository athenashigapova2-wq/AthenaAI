"""Validated environment configuration for Athena load tests."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock


class LoadTestConfigurationError(RuntimeError):
    """Raised before traffic starts when the load-test contract is invalid."""


@dataclass(frozen=True)
class LoadStage:
    name: str
    duration_seconds: int
    users: int
    spawn_rate: float


DEFAULT_STAGES = (
    LoadStage("warmup", duration_seconds=30, users=2, spawn_rate=1),
    LoadStage("steady", duration_seconds=90, users=4, spawn_rate=1),
    LoadStage("overload", duration_seconds=90, users=12, spawn_rate=4),
    LoadStage("recovery", duration_seconds=60, users=4, spawn_rate=4),
)

DEFAULT_PROMPTS = (
    "Ответь одним предложением: что такое сбалансированное питание?",
    "Кратко назови три принципа здорового сна без персональных рекомендаций.",
    "Одним абзацем объясни, зачем нужна разминка перед тренировкой.",
)


def _positive_float(name: str, default: float, *, allow_zero: bool = False) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise LoadTestConfigurationError(f"{name} must be a number") from exc
    minimum = 0 if allow_zero else 0.000_001
    if value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise LoadTestConfigurationError(f"{name} must be {qualifier}")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise LoadTestConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise LoadTestConfigurationError(f"{name} must be positive")
    return value


def _json_array(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LoadTestConfigurationError(f"{name} must be a JSON array") from exc
    if not isinstance(value, list) or not value:
        raise LoadTestConfigurationError(f"{name} must be a non-empty JSON array")
    strings = tuple(str(item).strip() for item in value if str(item).strip())
    if not strings:
        raise LoadTestConfigurationError(f"{name} contains no usable values")
    return strings


def load_stages(raw: str | None = None) -> tuple[LoadStage, ...]:
    raw = (raw if raw is not None else os.getenv("LOAD_TEST_STAGES", "")).strip()
    if not raw:
        return DEFAULT_STAGES
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LoadTestConfigurationError("LOAD_TEST_STAGES must be valid JSON") from exc
    if not isinstance(values, list) or not values:
        raise LoadTestConfigurationError("LOAD_TEST_STAGES must be a non-empty array")

    stages: list[LoadStage] = []
    names: set[str] = set()
    for index, value in enumerate(values, start=1):
        if not isinstance(value, dict):
            raise LoadTestConfigurationError(f"stage {index} must be an object")
        name = str(value.get("name") or f"stage-{index}").strip()
        if not name or name in names:
            raise LoadTestConfigurationError("stage names must be non-empty and unique")
        try:
            duration = int(value["duration_seconds"])
            users = int(value["users"])
            spawn_rate = float(value["spawn_rate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise LoadTestConfigurationError(
                f"stage {name} requires duration_seconds, users and spawn_rate"
            ) from exc
        if duration <= 0 or users < 0 or spawn_rate <= 0:
            raise LoadTestConfigurationError(
                f"stage {name} requires duration > 0, users >= 0 and spawn_rate > 0"
            )
        stages.append(LoadStage(name, duration, users, spawn_rate))
        names.add(name)
    return tuple(stages)


def _normalize_token(value: str) -> str:
    token = value.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


def load_access_tokens() -> tuple[str, ...]:
    tokens: list[str] = []
    single_token = _normalize_token(os.getenv("LOAD_TEST_ACCESS_TOKEN", ""))
    if single_token:
        tokens.append(single_token)

    token_file = os.getenv("LOAD_TEST_TOKEN_FILE", "").strip()
    if token_file:
        path = Path(token_file).expanduser()
        if not path.is_file():
            raise LoadTestConfigurationError(f"LOAD_TEST_TOKEN_FILE not found: {path}")
        content = path.read_text(encoding="utf-8").strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = [line for line in content.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        if not isinstance(parsed, list):
            raise LoadTestConfigurationError("LOAD_TEST_TOKEN_FILE must contain a JSON array or one token per line")
        tokens.extend(_normalize_token(str(item)) for item in parsed)

    unique_tokens = tuple(dict.fromkeys(token for token in tokens if token))
    if not unique_tokens:
        raise LoadTestConfigurationError(
            "Set LOAD_TEST_ACCESS_TOKEN or LOAD_TEST_TOKEN_FILE with Supabase access tokens"
        )
    return unique_tokens


def require_provider_cost_acknowledgement() -> None:
    acknowledged = os.getenv("LOAD_TEST_ACKNOWLEDGE_PROVIDER_COSTS", "").strip().lower()
    if acknowledged not in {"1", "true", "yes"}:
        raise LoadTestConfigurationError(
            "Set LOAD_TEST_ACKNOWLEDGE_PROVIDER_COSTS=true because this suite makes real GigaChat calls"
        )


@dataclass(frozen=True)
class LoadSettings:
    locale: str
    prompts: tuple[str, ...]
    poll_interval_seconds: float
    max_job_wait_seconds: float
    request_timeout_seconds: float
    min_think_time_seconds: float
    max_think_time_seconds: float
    turns_per_conversation: int
    stages: tuple[LoadStage, ...]

    @classmethod
    def from_env(cls) -> "LoadSettings":
        require_provider_cost_acknowledgement()
        locale = os.getenv("LOAD_TEST_LOCALE", "ru").strip().lower()
        if locale not in {"ru", "en", "fr", "es", "zh"}:
            raise LoadTestConfigurationError("LOAD_TEST_LOCALE must be ru, en, fr, es or zh")
        min_think = _positive_float("LOAD_TEST_MIN_THINK_SECONDS", 0.5, allow_zero=True)
        max_think = _positive_float("LOAD_TEST_MAX_THINK_SECONDS", 1.5, allow_zero=True)
        if max_think < min_think:
            raise LoadTestConfigurationError(
                "LOAD_TEST_MAX_THINK_SECONDS must be >= LOAD_TEST_MIN_THINK_SECONDS"
            )
        return cls(
            locale=locale,
            prompts=_json_array("LOAD_TEST_PROMPTS", DEFAULT_PROMPTS),
            poll_interval_seconds=_positive_float("LOAD_TEST_POLL_INTERVAL_SECONDS", 0.75),
            max_job_wait_seconds=_positive_float("LOAD_TEST_MAX_JOB_WAIT_SECONDS", 180),
            request_timeout_seconds=_positive_float("LOAD_TEST_REQUEST_TIMEOUT_SECONDS", 15),
            min_think_time_seconds=min_think,
            max_think_time_seconds=max_think,
            turns_per_conversation=_positive_int("LOAD_TEST_TURNS_PER_CONVERSATION", 3),
            stages=load_stages(),
        )


class TokenPool:
    """Assign access tokens round-robin without ever logging their values."""

    def __init__(self, tokens: tuple[str, ...]) -> None:
        if not tokens:
            raise LoadTestConfigurationError("TokenPool requires at least one token")
        self._tokens = tokens
        self._index = 0
        self._lock = Lock()

    @property
    def size(self) -> int:
        return len(self._tokens)

    def next(self) -> str:
        with self._lock:
            token = self._tokens[self._index % len(self._tokens)]
            self._index += 1
        return token
