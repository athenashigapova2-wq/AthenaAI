"""Celery application configured with Redis as its broker."""

import logging

from celery import Celery
from celery.signals import worker_ready

from app.config import settings
from app.embeddings import get_embeddings

logger = logging.getLogger(__name__)

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


@worker_ready.connect
def preload_embeddings(**_: object) -> None:
    """Load embeddings before this worker starts consuming chat jobs."""
    logger.info("Preloading embedding model")
    get_embeddings()
    logger.info("Embedding model ready")
