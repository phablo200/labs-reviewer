"""Factories for Labs task dispatch adapters."""

from fastapi import BackgroundTasks

from core.tasks.background_task_dispatcher import (
    BackgroundTaskSubmission,
    BackgroundTasksDispatcher,
)
from core.tasks.celery_task_dispatcher import CeleryTaskDispatcher, CeleryTaskSubmission
from core.tasks.task_dispatcher import (
    TaskDispatcher,
    build_task_dispatcher,
)
from labs.helpers.markdown_helper import MarkdownHelper
from labs.tasks.celery_tasks import process_markdown_job
from labs.tasks.markdown_jobs import (
    MarkdownOrganizationDispatcher,
    MarkdownOrganizationJob,
)


class MarkdownOrganizationTaskDispatcher:
    """Adapt markdown organization jobs to the generic task dispatcher."""

    def __init__(
        self,
        *,
        task_dispatcher: TaskDispatcher,
        writer_agent,
        translator_agent,
        metadata_agent,
        process_status_service,
    ) -> None:
        self.task_dispatcher = task_dispatcher
        self.writer_agent = writer_agent
        self.translator_agent = translator_agent
        self.metadata_agent = metadata_agent
        self.process_status_service = process_status_service

    async def enqueue(
        self,
        *,
        job: MarkdownOrganizationJob,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        if isinstance(self.task_dispatcher, BackgroundTasksDispatcher):
            if background_tasks is None:
                raise RuntimeError(
                    "BackgroundTasks is required for background_tasks dispatch."
                )

            await self.task_dispatcher.enqueue(
                background_task_submission=BackgroundTaskSubmission(
                    function=MarkdownHelper.process_and_save_markdown_with_status,
                    args=(
                        job.context,
                        job.output_path,
                        self.writer_agent,
                        self.translator_agent,
                        self.metadata_agent,
                        job.process_status_id,
                        self.process_status_service,
                    ),
                ),
                background_tasks=background_tasks,
            )
            return

        if isinstance(self.task_dispatcher, CeleryTaskDispatcher):
            await self.task_dispatcher.enqueue(
                celery_task_submission=CeleryTaskSubmission(
                    task=process_markdown_job,
                    args=(
                        job.context,
                        str(job.output_path),
                        str(job.process_status_id),
                    ),
                ),
            )
            return

        raise RuntimeError("Unsupported task dispatcher.")


def build_markdown_dispatcher(
    *,
    writer_agent,
    translator_agent,
    metadata_agent,
    process_status_service,
) -> MarkdownOrganizationDispatcher:
    """Build the configured markdown dispatch adapter."""
    return MarkdownOrganizationTaskDispatcher(
        task_dispatcher=build_task_dispatcher(),
        writer_agent=writer_agent,
        translator_agent=translator_agent,
        metadata_agent=metadata_agent,
        process_status_service=process_status_service,
    )
