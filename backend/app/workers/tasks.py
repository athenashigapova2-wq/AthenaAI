"""Celery tasks for long-running agent work."""

import logging

from app.services.agent_chat import ConversationNotFoundError, run_agent_chat
from app.services.agent_jobs import mark_job_failed, mark_job_running, mark_job_succeeded
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="athena.run_agent_chat")
def run_agent_chat_task(
    *,
    job_id: str,
    user_id: str,
    message: str,
    locale: str,
    conversation_id: str | None,
) -> None:
    """Run one chat request without retrying potentially state-changing tools."""
    mark_job_running(job_id)
    try:
        result = run_agent_chat(
            user_id=user_id,
            message=message,
            locale=locale,
            conversation_id=conversation_id,
        )
    except ConversationNotFoundError as exc:
        mark_job_failed(job_id, str(exc))
        raise
    except Exception:
        logger.exception("Agent job %s failed", job_id)
        mark_job_failed(job_id, "Агент временно недоступен")
        raise
    mark_job_succeeded(job_id, result)
