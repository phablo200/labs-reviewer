"""Business operations for Labs process status tracking."""

from uuid import UUID

from labs.process_status.models import AgentStatus, ProcessStatus
from labs.process_status.repository import ProcessStatusRepository
from labs.process_status.schemas import ProcessStatusResponse


class ProcessStatusService:
    """Coordinate process status persistence and response serialization."""

    def __init__(self, repository: ProcessStatusRepository | None = None) -> None:
        self.repository = repository or ProcessStatusRepository()

    async def create_process_status(
        self,
        *,
        file: str,
        user_id: UUID,
        data: list[AgentStatus] | None = None,
    ) -> ProcessStatus:
        return await self.repository.create(file=file, user_id=user_id, data=data)

    async def get_process_status(
        self,
        *,
        process_id: UUID,
        user_id: UUID,
    ) -> ProcessStatus | None:
        return await self.repository.get_by_id(process_id=process_id, user_id=user_id)

    async def save_process_status(self, process_status: ProcessStatus) -> ProcessStatus:
        return await self.repository.save(process_status)

    def build_status_response(
        self,
        process_status: ProcessStatus,
    ) -> ProcessStatusResponse:
        return ProcessStatusResponse.from_process_status(process_status)
