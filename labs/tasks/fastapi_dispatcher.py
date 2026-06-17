"""FastAPI BackgroundTasks markdown dispatch strategy."""

from fastapi import BackgroundTasks

from labs.helpers.markdown_helper import MarkdownHelper
from labs.tasks.markdown_jobs import MarkdownOrganizationJob


class FastAPIBackgroundMarkdownDispatcher:
    """Schedule markdown work with FastAPI BackgroundTasks."""

    def __init__(
        self,
        *,
        writer_agent,
        translator_agent,
        metadata_agent,
        process_status_service,
    ) -> None:
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
        if background_tasks is None:
            raise RuntimeError("BackgroundTasks is required for background_tasks dispatch.")

        background_tasks.add_task(
            MarkdownHelper.process_and_save_markdown_with_status,
            job.context,
            job.output_path,
            self.writer_agent,
            self.translator_agent,
            self.metadata_agent,
            job.process_status_id,
            self.process_status_service,
        )

