"""Helper functions for Labs process status services."""

from collections import defaultdict
from uuid import UUID

from core.utils.datetime import utc_now
from labs.process_status.models import (
    AgentProcessStatus,
    AgentProcessStatusState,
    ProcessStatus,
    ProcessStatusState,
)
from labs.process_status.schemas import AgentProcessStatusSummaryResponse
from labs.process_status.schemas import ProcessStatusResponse


async def mark_agent_process(
    *,
    agent_repository,
    process_repository,
    agent_process_status: AgentProcessStatus,
    status: AgentProcessStatusState,
    result: str | None = None,
) -> AgentProcessStatus:
    updated_agent_process_status = await agent_repository.update_status(
        agent_process_status=agent_process_status,
        status=status,
        finished_at=utc_now(),
        result=result,
    )
    await sync_process_status(
        process_status_id=updated_agent_process_status.process_status_id,
        agent_repository=agent_repository,
        process_repository=process_repository,
    )
    return updated_agent_process_status


async def sync_process_status(
    *,
    process_status_id: UUID,
    agent_repository,
    process_repository,
) -> ProcessStatus | None:
    agent_processes = await agent_repository.list_by_process_status_id(
        process_status_id
    )
    status = derive_process_status(agent_processes)
    process_status = await process_repository.get_by_process_id(process_status_id)
    if process_status is None:
        return None

    if process_status.status == status:
        return process_status

    process_status.status = status
    return await process_repository.save(process_status)


def derive_process_status(
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


def group_children(
    agent_processes: list[AgentProcessStatus],
) -> dict[UUID | None, list[AgentProcessStatus]]:
    children_by_parent: dict[UUID | None, list[AgentProcessStatus]] = defaultdict(list)
    for agent_process in agent_processes:
        children_by_parent[agent_process.parent_agent_process_status_id].append(
            agent_process
        )
    return children_by_parent


def build_summary_children(
    parent_id: UUID | None,
    children_by_parent: dict[UUID | None, list[AgentProcessStatus]],
) -> list[AgentProcessStatusSummaryResponse]:
    responses: list[AgentProcessStatusSummaryResponse] = []
    for agent_process in children_by_parent.get(parent_id, []):
        responses.append(
            AgentProcessStatusSummaryResponse.from_agent_process_status(
                agent_process,
                children=build_summary_children(
                    agent_process.id,
                    children_by_parent,
                ),
            )
        )
    return responses


async def mark_process_failed(
    *,
    process_repository,
    process_status_id: UUID,
    result: str | None = None,
) -> ProcessStatus | None:
    process_status = await process_repository.get_by_process_id(process_status_id)
    if process_status is None:
        return None

    process_status.status = "FAILED"
    return await process_repository.save(process_status)


def build_status_response(
    process_status: ProcessStatus,
    agent_processes: list[AgentProcessStatus] | None = None,
) -> ProcessStatusResponse:
    agent_processes = agent_processes or []
    children_by_parent = group_children(agent_processes)
    data = build_summary_children(None, children_by_parent)
    return ProcessStatusResponse.from_process_status(process_status, data=data)
