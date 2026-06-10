"""Persistence operations for process status documents."""

from uuid import UUID

from labs.process_status.models import AgentStatus, ProcessStatus


class ProcessStatusRepository:
    """Wrap Beanie operations for process status persistence."""

    async def create(
        self,
        *,
        file: str,
        user_id: UUID,
        data: list[AgentStatus] | None = None,
    ) -> ProcessStatus:
        process_status = ProcessStatus(
            file=file,
            user_id=user_id,
            data=data or [],
        )
        await process_status.insert()
        return process_status

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

    async def save(self, process_status: ProcessStatus) -> ProcessStatus:
        await process_status.save()
        return process_status
