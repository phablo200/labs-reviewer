"""Persistence operations for agent process status documents."""

from uuid import UUID

from labs.process_status.models import (
    AgentProcessStatus,
    AgentProcessStatusState,
)


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
