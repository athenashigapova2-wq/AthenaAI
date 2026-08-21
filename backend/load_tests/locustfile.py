"""Staged load test for the Redis-backed Athena agent API."""

from __future__ import annotations

import logging
import os
import random
import sys
import time
from pathlib import Path
from time import perf_counter

import gevent
from locust import HttpUser, LoadTestShape, events, task

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from load_tests.config import LoadSettings, TokenPool, load_access_tokens  # noqa: E402

logger = logging.getLogger(__name__)
SETTINGS = LoadSettings.from_env()
TOKEN_POOL = TokenPool(load_access_tokens())
CURRENT_STAGE = "starting"


def current_stage() -> str:
    return CURRENT_STAGE


def _json_object(response) -> dict | None:
    try:
        value = response.json()
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


@events.test_start.add_listener
def describe_test(environment, **_kwargs) -> None:
    host = environment.host or os.getenv("LOAD_TEST_HOST", "http://127.0.0.1:8001")
    max_users = max(stage.users for stage in SETTINGS.stages)
    logger.warning(
        "Athena load test starting: host=%s stages=%s tokens=%s max_users=%s",
        host,
        ",".join(stage.name for stage in SETTINGS.stages),
        TOKEN_POOL.size,
        max_users,
    )
    if TOKEN_POOL.size < max_users:
        logger.warning(
            "Only %s access token(s) for %s users; tokens will be reused. "
            "Use one dedicated token per user for true multi-user isolation.",
            TOKEN_POOL.size,
            max_users,
        )


class AgentUser(HttpUser):
    """One authenticated user repeatedly enqueues and waits for an agent turn."""

    host = os.getenv("LOAD_TEST_HOST", "http://127.0.0.1:8001")

    def on_start(self) -> None:
        self.access_token = TOKEN_POOL.next()
        self.headers = {"Authorization": f"Bearer {self.access_token}"}
        self.conversation_id: str | None = None
        self.conversation_turns = 0

    def wait_time(self) -> float:
        return random.uniform(
            SETTINGS.min_think_time_seconds,
            SETTINGS.max_think_time_seconds,
        )

    def _record_flow(
        self,
        *,
        stage: str,
        started_at: float,
        started_epoch: float,
        error: Exception | None,
        response_length: int = 0,
    ) -> None:
        self.environment.events.request.fire(
            request_type="FLOW",
            name=f"agent_chat_e2e [{stage}]",
            response_time=max(0, (perf_counter() - started_at) * 1_000),
            response_length=response_length,
            response=None,
            context={"stage": stage},
            exception=error,
            start_time=started_epoch,
            url="/api/v1/agent/chat -> job completion",
        )

    @task
    def agent_chat_round_trip(self) -> None:
        stage = current_stage()
        flow_started = perf_counter()
        flow_started_epoch = time.time()
        prompt = random.choice(SETTINGS.prompts)
        if self.conversation_turns >= SETTINGS.turns_per_conversation:
            self.conversation_id = None
            self.conversation_turns = 0

        request_body = {
            "message": prompt,
            "locale": SETTINGS.locale,
            "conversation_id": self.conversation_id,
        }
        enqueue_error: Exception | None = None
        job_id: str | None = None
        with self.client.post(
            "/api/v1/agent/chat",
            name=f"POST agent/chat enqueue [{stage}]",
            headers=self.headers,
            json=request_body,
            timeout=SETTINGS.request_timeout_seconds,
            catch_response=True,
        ) as response:
            data = _json_object(response)
            if response.status_code != 202:
                enqueue_error = RuntimeError(f"enqueue HTTP {response.status_code}")
                response.failure(str(enqueue_error))
            elif not data or data.get("status") != "queued" or not data.get("job_id"):
                enqueue_error = RuntimeError("enqueue response contract mismatch")
                response.failure(str(enqueue_error))
            else:
                job_id = str(data["job_id"])
                response.success()

        if enqueue_error or not job_id:
            self._record_flow(
                stage=stage,
                started_at=flow_started,
                started_epoch=flow_started_epoch,
                error=enqueue_error or RuntimeError("missing job id"),
            )
            return

        deadline = perf_counter() + SETTINGS.max_job_wait_seconds
        while perf_counter() < deadline:
            gevent.sleep(SETTINGS.poll_interval_seconds)
            flow_error: Exception | None = None
            completed_data: dict | None = None
            with self.client.get(
                f"/api/v1/agent/chat/jobs/{job_id}",
                name=f"GET agent/chat/jobs/{{job_id}} poll [{stage}]",
                headers=self.headers,
                timeout=SETTINGS.request_timeout_seconds,
                catch_response=True,
            ) as response:
                data = _json_object(response)
                if response.status_code != 200:
                    flow_error = RuntimeError(f"poll HTTP {response.status_code}")
                    response.failure(str(flow_error))
                elif not data or data.get("status") not in {
                    "queued",
                    "running",
                    "succeeded",
                    "failed",
                }:
                    flow_error = RuntimeError("poll response contract mismatch")
                    response.failure(str(flow_error))
                elif data["status"] == "failed":
                    flow_error = RuntimeError(str(data.get("error") or "agent job failed"))
                    response.failure(str(flow_error))
                elif data["status"] == "succeeded":
                    if not data.get("answer") or not data.get("conversation_id"):
                        flow_error = RuntimeError("completed job is missing answer or conversation_id")
                        response.failure(str(flow_error))
                    else:
                        completed_data = data
                        response.success()
                else:
                    response.success()

            if flow_error:
                self._record_flow(
                    stage=stage,
                    started_at=flow_started,
                    started_epoch=flow_started_epoch,
                    error=flow_error,
                )
                return
            if completed_data:
                self.conversation_id = str(completed_data["conversation_id"])
                self.conversation_turns += 1
                answer_length = len(str(completed_data["answer"]).encode("utf-8"))
                self._record_flow(
                    stage=stage,
                    started_at=flow_started,
                    started_epoch=flow_started_epoch,
                    error=None,
                    response_length=answer_length,
                )
                return

        self._record_flow(
            stage=stage,
            started_at=flow_started,
            started_epoch=flow_started_epoch,
            error=TimeoutError(f"job did not finish in {SETTINGS.max_job_wait_seconds:g}s"),
        )


class StagedAgentLoadShape(LoadTestShape):
    """Warm up, hold, overload the four-thread worker, then observe recovery."""

    def __init__(self) -> None:
        super().__init__()
        self._last_stage: str | None = None

    def tick(self):
        global CURRENT_STAGE
        run_time = self.get_run_time()
        elapsed = 0
        for stage in SETTINGS.stages:
            elapsed += stage.duration_seconds
            if run_time < elapsed:
                CURRENT_STAGE = stage.name
                if self._last_stage != stage.name:
                    logger.warning(
                        "Load stage %s: users=%s spawn_rate=%s duration=%ss",
                        stage.name,
                        stage.users,
                        stage.spawn_rate,
                        stage.duration_seconds,
                    )
                    self._last_stage = stage.name
                return stage.users, stage.spawn_rate
        return None
