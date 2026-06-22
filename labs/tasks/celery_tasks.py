"""Celery task functions for Labs background workflows."""

import anyio

from core.tasks import constants
from core.tasks.celery_app import celery_app
from core.tasks.dead_letter import DeadLetterTask
from labs.tasks.helpers import (
    context_descriptor,
    mark_process_failed_from_task_args,
    process_markdown_job_async,
)


class MarkdownDeadLetterTask(DeadLetterTask):
    """Dead-letter behavior for markdown processing tasks."""

    def sanitize_args(self, args) -> list:
        values = list(args or ())
        if not values:
            return values

        return ["[omitted-context]", *values[1:]]

    def sanitize_kwargs(self, kwargs) -> dict:
        values = dict(kwargs or {})
        if "context" in values:
            values["context"] = "[omitted-context]"
        return values

    def build_dead_letter_payload(self, exc, task_id, args, kwargs):
        payload = super().build_dead_letter_payload(exc, task_id, args, kwargs)
        payload["context"] = context_descriptor(args, kwargs)
        return payload

    def on_final_failure(self, exc, _task_id, args, kwargs, _einfo) -> None:
        anyio.run(mark_process_failed_from_task_args, args, kwargs, exc)


@celery_app.task(
    bind=True,
    base=MarkdownDeadLetterTask,
    name="labs.process_markdown_job",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": constants.CELERY_TASK_MAX_RETRIES},
    max_retries=constants.CELERY_TASK_MAX_RETRIES,
)
def process_markdown_job(
    _,
    context: str,
    output_path: str,
    process_status_id: str,
    simulate_failure: bool = False,
) -> dict[str, str]:
    """Process markdown in a Celery worker and store operational task metadata."""
    if simulate_failure:
        raise RuntimeError("Simulated DLQ failure")

    anyio.run(
        process_markdown_job_async,
        context,
        output_path,
        process_status_id,
    )
    return {
        "process_status_id": process_status_id,
        "output_path": output_path,
        "status": "completed",
    }
