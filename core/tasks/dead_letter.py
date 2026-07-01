"""Application-level dead letter handling for Celery tasks."""

from __future__ import annotations

import json
import logging
from typing import Any

import redis
from celery import Task

from core.config import settings
from core.tasks import constants
from core.utils.datetime import utc_now

logger = logging.getLogger(__name__)


class DeadLetterTask(Task):
    """Celery task base that writes final failures to a Redis DLQ."""

    abstract = True
    max_retries = constants.CELERY_TASK_MAX_RETRIES
    _redis_client = None

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if self._is_final_failure():
            if settings.CELERY_DLQ_ENABLED:
                try:
                    self.write_dead_letter(exc, task_id, args, kwargs)
                except Exception:
                    logger.exception(
                        "Failed to write Celery task to dead letter queue",
                        extra={"task_id": task_id, "task_name": self.name},
                    )

            try:
                self.on_final_failure(exc, task_id, args, kwargs, einfo)
            except Exception:
                logger.exception(
                    "Failed to run Celery task final failure hook",
                    extra={"task_id": task_id, "task_name": self.name},
                )

        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_final_failure(self, exc, task_id, args, kwargs, einfo) -> None:
        """Run workflow-specific final failure handling."""
        return None

    def write_dead_letter(self, exc, task_id, args, kwargs) -> None:
        """Persist a compact final-failure payload to Redis."""
        self._get_redis_client().lpush(
            self.dead_letter_key(),
            json.dumps(
                self.build_dead_letter_payload(exc, task_id, args, kwargs),
                default=str,
            ),
        )

    def build_dead_letter_payload(
        self,
        exc,
        task_id,
        args,
        kwargs,
    ) -> dict[str, Any]:
        """Build the JSON-serializable DLQ payload."""
        return {
            "task_id": task_id,
            "task_name": self.name,
            "args": self.sanitize_args(args),
            "kwargs": self.sanitize_kwargs(kwargs),
            "error": f"{type(exc).__name__}: {exc}",
            "exception_type": type(exc).__name__,
            "retries": self._request_retries(),
            "max_retries": self._max_retries(),
            "queue": self._request_queue(),
            "failed_at": utc_now().isoformat().replace("+00:00", "Z"),
        }

    def sanitize_args(self, args) -> list[Any]:
        """Return args safe to store in the DLQ."""
        return list(args or ())

    def sanitize_kwargs(self, kwargs) -> dict[str, Any]:
        """Return kwargs safe to store in the DLQ."""
        return dict(kwargs or {})

    def dead_letter_key(self) -> str:
        prefix = settings.CELERY_DLQ_KEY_PREFIX.strip()
        return f"{prefix}:{self.name}"

    def _is_final_failure(self) -> bool:
        return self._request_retries() >= self._max_retries()

    def _request_retries(self) -> int:
        return int(getattr(self.request, "retries", 0) or 0)

    def _max_retries(self) -> int:
        return int(self.max_retries or constants.CELERY_TASK_MAX_RETRIES)

    def _request_queue(self) -> str:
        delivery_info = getattr(self.request, "delivery_info", None) or {}
        return delivery_info.get("routing_key") or delivery_info.get("queue") or "celery"

    def _get_redis_client(self):
        if self._redis_client is None:
            self._redis_client = self._build_redis_client()
        return self._redis_client

    def _build_redis_client(self):
        return redis.Redis.from_url(settings.CELERY_BROKER_URL)
