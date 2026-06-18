"""Celery task functions for Labs background workflows."""

from pathlib import Path
from uuid import UUID

import anyio

from core.database.mongodb import close_mongodb, init_mongodb
from labs.helpers.markdown_helper import MarkdownHelper
from core.tasks.celery_app import celery_app
from labs.tasks.dependencies import build_markdown_processing_dependencies


async def _process_markdown_job_async(
    context: str,
    output_path: str,
    process_status_id: str,
) -> None:
    await init_mongodb()
    try:
        dependencies = build_markdown_processing_dependencies()
        await MarkdownHelper.process_and_save_markdown_with_status(
            context,
            Path(output_path),
            dependencies.writer_agent,
            dependencies.translator_agent,
            dependencies.metadata_agent,
            UUID(process_status_id),
            dependencies.process_status_service,
        )
    finally:
        await close_mongodb()


@celery_app.task(name="labs.process_markdown_job")
def process_markdown_job(
    *,
    context: str,
    output_path: str,
    process_status_id: str,
) -> dict[str, str]:
    """Process markdown in a Celery worker and store operational task metadata."""
    anyio.run(
        _process_markdown_job_async,
        context,
        output_path,
        process_status_id,
    )
    return {
        "process_status_id": process_status_id,
        "output_path": output_path,
        "status": "completed",
    }
