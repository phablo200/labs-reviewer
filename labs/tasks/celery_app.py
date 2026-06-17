"""Celery application configuration for Labs background workers."""

from celery import Celery

from core.config import settings

celery_app = Celery(
    "labs_reviewer",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    timezone="UTC",
    enable_utc=True,
    imports=("labs.tasks.celery_tasks",),
)

