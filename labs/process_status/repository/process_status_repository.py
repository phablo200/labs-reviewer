"""Persistence operations for process status documents."""

import re
from uuid import UUID

from beanie.operators import RegEx

from core.utils.datetime import utc_now
from labs.process_status.models import ProcessStatus


class ProcessStatusRepository:
    """Wrap Beanie operations for process status persistence."""

    async def create(
        self,
        *,
        file: str,
        user_id: UUID,
    ) -> ProcessStatus:
        process_status = ProcessStatus(
            file=file,
            status="IN_PROGRESS",
            user_id=user_id,
        )
        await process_status.insert()
        return process_status

    async def create_writing(self, *, user_id: UUID) -> ProcessStatus:
        process_status = ProcessStatus(
            file=utc_now().strftime("%Y-%m-%d %H:%M:%S"),
            status="WRITTING",
            user_id=user_id,
        )
        await process_status.insert()
        return process_status

    async def get_by_process_id(self, process_id: UUID) -> ProcessStatus | None:
        return await ProcessStatus.find_one(ProcessStatus.id == process_id)

    async def get_by_id(
        self,
        *,
        process_id: UUID,
        user_id: UUID,
    ) -> ProcessStatus | None:
        return await ProcessStatus.find_one(
            ProcessStatus.id == process_id,
            ProcessStatus.user_id == user_id,
        )

    async def list_by_user_id(
        self,
        *,
        user_id: UUID,
        term: str | None = None,
        limit: int = 100,
    ) -> list[ProcessStatus]:
        filters = [ProcessStatus.user_id == user_id]
        normalized_term = term.strip() if term is not None else ""
        if normalized_term:
            filters.append(RegEx("file", re.escape(normalized_term), "i"))

        return await (
            ProcessStatus.find(*filters)
            .sort("-created_at")
            .limit(limit)
            .to_list()
        )

    async def save(self, process_status: ProcessStatus) -> ProcessStatus:
        await process_status.save()
        return process_status
