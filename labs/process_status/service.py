"""Business operations for Labs process status tracking."""

from collections import defaultdict
from uuid import UUID

from core.utils.datetime import utc_now
from labs.process_status.models import (
    AgentProcessStatus,
    AgentProcessStatusState,
    ProcessStatus,
    ProcessStatusState,
)
from labs.process_status.repository import (
    AgentProcessStatusRepository,
    ProcessStatusRepository,
)
from labs.process_status.schemas import (
    AgentProcessStatusDetailResponse,
    AgentProcessStatusSummaryResponse,
    ProcessStatusResponse,
)


class ProcessStatusService:
    """Coordinate process status persistence and response serialization."""

    def __init__(
        self,
        repository: ProcessStatusRepository | None = None,
        agent_repository: AgentProcessStatusRepository | None = None,
    ) -> None:
        self.repository = repository or ProcessStatusRepository()
        self.agent_repository = agent_repository or AgentProcessStatusRepository()

    async def create_process_for_review(
        self,
        *,
        file: str,
        user_id: UUID,
    ) -> ProcessStatus:
        return await self.repository.create(file=file, user_id=user_id)

    async def create_process_status(
        self,
        *,
        file: str,
        user_id: UUID,
    ) -> ProcessStatus:
        return await self.create_process_for_review(file=file, user_id=user_id)

    async def create_agent_process(
        self,
        *,
        process_status_id: UUID,
        name: str,
        parent_agent_process_status_id: UUID | None = None,
        loop_from: int | None = None,
        loop_to: int | None = None,
    ) -> AgentProcessStatus:
        return await self.agent_repository.create(
            process_status_id=process_status_id,
            name=name,
            parent_agent_process_status_id=parent_agent_process_status_id,
            loop_from=loop_from,
            loop_to=loop_to,
        )

    async def mark_agent_process_succeeded(
        self,
        *,
        agent_process_status: AgentProcessStatus,
        result: str | None = None,
    ) -> AgentProcessStatus:
        return await self._mark_agent_process(
            agent_process_status=agent_process_status,
            status="SUCCEEDED",
            result=result,
        )

    async def mark_agent_process_failed(
        self,
        *,
        agent_process_status: AgentProcessStatus,
        result: str | None = None,
    ) -> AgentProcessStatus:
        return await self._mark_agent_process(
            agent_process_status=agent_process_status,
            status="FAILED",
            result=result,
        )

    async def _mark_agent_process(
        self,
        *,
        agent_process_status: AgentProcessStatus,
        status: AgentProcessStatusState,
        result: str | None = None,
    ) -> AgentProcessStatus:
        updated_agent_process_status = await self.agent_repository.update_status(
            agent_process_status=agent_process_status,
            status=status,
            finished_at=utc_now(),
            result=result,
        )
        await self._sync_process_status(updated_agent_process_status.process_status_id)
        return updated_agent_process_status

    async def get_process_status(
        self,
        *,
        process_id: UUID,
        user_id: UUID,
    ) -> ProcessStatus | None:
        return await self.repository.get_by_id(process_id=process_id, user_id=user_id)

    async def list_process_statuses(
        self,
        *,
        user_id: UUID,
        term: str | None = None,
        limit: int = 100,
    ) -> list[ProcessStatusResponse]:
        process_statuses = await self.repository.list_by_user_id(
            user_id=user_id,
            term=term,
            limit=limit,
        )
        return [
            ProcessStatusResponse.from_process_status(process_status)
            for process_status in process_statuses
        ]

    async def get_process_with_agent_processes(
        self,
        *,
        process_id: UUID,
        user_id: UUID,
    ) -> ProcessStatusResponse | None:
        process_status = await self.get_process_status(
            process_id=process_id,
            user_id=user_id,
        )
        if process_status is None:
            return None

        agent_processes = await self.agent_repository.list_by_process_status_id(
            process_status.id
        )
        return self.build_status_response(process_status, agent_processes)

    async def get_agent_process_with_children(
        self,
        *,
        agent_process_id: UUID,
        user_id: UUID,
    ) -> AgentProcessStatusDetailResponse | None:
        agent_process = await self.agent_repository.get_by_id(agent_process_id)
        if agent_process is None:
            return None

        process_status = await self.get_process_status(
            process_id=agent_process.process_status_id,
            user_id=user_id,
        )
        if process_status is None:
            return None

        agent_processes = await self.agent_repository.list_by_process_status_id(
            process_status.id
        )
        children_by_parent = self._group_children(agent_processes)
        children = self._build_summary_children(agent_process.id, children_by_parent)
        return AgentProcessStatusDetailResponse.from_agent_process_status(
            agent_process,
            children=children,
        )

    async def save_process_status(self, process_status: ProcessStatus) -> ProcessStatus:
        return await self.repository.save(process_status)

    async def _sync_process_status(self, process_status_id: UUID) -> ProcessStatus | None:
        agent_processes = await self.agent_repository.list_by_process_status_id(
            process_status_id
        )
        status = self._derive_process_status(agent_processes)
        process_status = await self.repository.get_by_process_id(process_status_id)
        if process_status is None:
            return None

        if process_status.status == status:
            return process_status

        process_status.status = status
        return await self.repository.save(process_status)

    def build_status_response(
        self,
        process_status: ProcessStatus,
        agent_processes: list[AgentProcessStatus] | None = None,
    ) -> ProcessStatusResponse:
        agent_processes = agent_processes or []
        children_by_parent = self._group_children(agent_processes)
        data = self._build_summary_children(None, children_by_parent)
        return ProcessStatusResponse.from_process_status(process_status, data=data)

    @staticmethod
    def _derive_process_status(
        agent_processes: list[AgentProcessStatus],
    ) -> ProcessStatusState:
        if not agent_processes:
            return "IN_PROGRESS"

        statuses = [agent_process.status for agent_process in agent_processes]
        if "FAILED" in statuses:
            return "FAILED"
        if "IN_PROGRESS" in statuses:
            return "IN_PROGRESS"
        return "SUCCEEDED"

    @staticmethod
    def _group_children(
        agent_processes: list[AgentProcessStatus],
    ) -> dict[UUID | None, list[AgentProcessStatus]]:
        children_by_parent: dict[UUID | None, list[AgentProcessStatus]] = defaultdict(list)
        for agent_process in agent_processes:
            children_by_parent[agent_process.parent_agent_process_status_id].append(
                agent_process
            )
        return children_by_parent

    def _build_summary_children(
        self,
        parent_id: UUID | None,
        children_by_parent: dict[UUID | None, list[AgentProcessStatus]],
    ) -> list[AgentProcessStatusSummaryResponse]:
        responses: list[AgentProcessStatusSummaryResponse] = []
        for agent_process in children_by_parent.get(parent_id, []):
            responses.append(
                AgentProcessStatusSummaryResponse.from_agent_process_status(
                    agent_process,
                    children=self._build_summary_children(
                        agent_process.id,
                        children_by_parent,
                    ),
                )
            )
        return responses
