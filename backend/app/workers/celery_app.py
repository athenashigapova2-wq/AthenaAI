"""Celery application configured with Redis as its broker."""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "athena",
    broker=settings.redis_url,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.agent_job_ttl_seconds},
    result_backend=None,
    task_default_queue=settings.agent_job_queue,
    task_ignore_result=True,
    task_serializer="json",
    task_track_started=False,
    timezone="UTC",
    worker_prefetch_multiplier=1,
)
