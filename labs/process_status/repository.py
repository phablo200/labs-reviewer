"""Persistence operations for process status documents."""

from uuid import UUID

from labs.process_status.models import (
    AgentProcessStatus,
    AgentProcessStatusState,
    ProcessStatus,
)


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

    async def save(self, process_status: ProcessStatus) -> ProcessStatus:
        await process_status.save()
        return process_status


class AgentProcessStatusRepository:
    """Wrap Beanie operations for agent process status persistence."""

    async def create(
        self,
        *,
        process_status_id: UUID,
        name: str,
        parent_agent_process_status_id: UUID | None = None,
        loop_from: int | None = None,
        loop_to: int | None = None,
        result: str | None = None,
    ) -> AgentProcessStatus:
        agent_process_status = AgentProcessStatus(
            process_status_id=process_status_id,
            parent_agent_process_status_id=parent_agent_process_status_id,
            name=name,
            status="IN_PROGRESS",
            loop_from=loop_from,
            loop_to=loop_to,
            result=result,
        )
        await agent_process_status.insert()
        return agent_process_status

    async def get_by_id(self, agent_process_id: UUID) -> AgentProcessStatus | None:
        return await AgentProcessStatus.find_one(AgentProcessStatus.id == agent_process_id)

    async def list_by_process_status_id(
        self,
        process_status_id: UUID,
    ) -> list[AgentProcessStatus]:
        return await AgentProcessStatus.find(
            AgentProcessStatus.process_status_id == process_status_id
        ).to_list()

    async def list_children(
        self,
        parent_agent_process_status_id: UUID,
    ) -> list[AgentProcessStatus]:
        return await AgentProcessStatus.find(
            AgentProcessStatus.parent_agent_process_status_id
            == parent_agent_process_status_id
        ).to_list()

    async def update_status(
        self,
        *,
        agent_process_status: AgentProcessStatus,
        status: AgentProcessStatusState,
        finished_at=None,
        result: str | None = None,
    ) -> AgentProcessStatus:
        agent_process_status.status = status
        agent_process_status.finished_at = finished_at
        agent_process_status.result = result
        await agent_process_status.save()
        return agent_process_status
