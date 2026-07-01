"""Helper functions for Labs background tasks."""

import hashlib
import logging
from pathlib import Path
from uuid import UUID

from core.database.mongodb import close_mongodb, init_mongodb
from labs.helpers.markdown_helper import MarkdownHelper
from labs.process_status.service import ProcessStatusService
from labs.tasks.dependencies import build_markdown_processing_dependencies

logger = logging.getLogger(__name__)


async def process_markdown_job_async(
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


async def mark_process_failed_from_task_args(args, kwargs, exc) -> None:
    process_status_id = extract_process_status_id(args, kwargs)
    if process_status_id is None:
        logger.warning("Cannot mark failed process without process_status_id")
        return

    await init_mongodb()
    try:
        await ProcessStatusService().mark_process_failed(
            process_status_id=process_status_id,
            result=f"{type(exc).__name__}: {exc}",
        )
    finally:
        await close_mongodb()


def extract_process_status_id(args, kwargs) -> UUID | None:
    raw_process_status_id = None
    if args and len(args) >= 3:
        raw_process_status_id = args[2]
    elif kwargs:
        raw_process_status_id = kwargs.get("process_status_id")

    if raw_process_status_id is None:
        return None

    try:
        return UUID(str(raw_process_status_id))
    except ValueError:
        logger.warning(
            "Cannot mark failed process with invalid process_status_id",
            extra={"process_status_id": raw_process_status_id},
        )
        return None


def context_descriptor(args, kwargs) -> dict[str, object]:
    context = None
    if args:
        context = args[0]
    elif kwargs:
        context = kwargs.get("context")

    if context is None:
        return {"omitted": True, "length": 0, "sha256": None}

    text = str(context)
    return {
        "omitted": True,
        "length": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
