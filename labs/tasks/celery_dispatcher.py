"""Celery markdown dispatch strategy."""

from fastapi import BackgroundTasks

from core.tasks.exceptions import TaskDispatchEnqueueError
from labs.tasks.celery_tasks import process_markdown_job
from labs.tasks.markdown_jobs import MarkdownOrganizationJob


class CeleryMarkdownDispatcher:
    """Schedule markdown work with Celery."""

    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        try:
            process_markdown_job.delay(
                context=job.context,
                output_path=str(job.output_path),
                process_status_id=str(job.process_status_id),
            )
        except Exception as exc:
            raise TaskDispatchEnqueueError(
                "Failed to enqueue Celery markdown organization job."
            ) from exc
