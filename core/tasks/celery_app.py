"""Celery application configuration shared by background workers."""

from celery import Celery

from core.config import settings


def _parse_task_modules(value: str) -> tuple[str, ...]:
    return tuple(module.strip() for module in value.split(",") if module.strip())


celery_app = Celery(
    "labs_reviewer",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=_parse_task_modules(settings.CELERY_TASK_MODULES),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=False,
    task_store_errors_even_if_ignored=True,
    timezone="UTC",
    enable_utc=True,
)

