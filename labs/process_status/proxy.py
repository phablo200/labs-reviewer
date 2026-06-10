"""Proxy wrappers for tracking agent invocations in MongoDB."""

from collections.abc import Callable
from collections.abc import Coroutine
import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from labs.process_status.models import AgentProcessStatus
from labs.process_status.service import ProcessStatusService


@dataclass(frozen=True)
class AgentProcessContext:
    """Carries process and parent-agent linkage for tracked agent calls."""

    process_status_id: UUID
    parent_agent_process_status_id: UUID | None = None
    loop_from: int | None = None
    loop_to: int | None = None


class AgentInvocationProxy:
    """Proxy an agent and persist status around selected method calls."""

    def __init__(
        self,
        *,
        agent: Any,
        agent_name: str,
        context: AgentProcessContext,
        status_service: ProcessStatusService,
        tracked_methods: set[str],
        loop_to: int | None = None,
        child_proxy_factory: Callable[[AgentProcessStatus], None] | None = None,
        async_runner: Callable[[Coroutine[Any, Any, Any]], Any] | None = None,
    ) -> None:
        self._agent = agent
        self._agent_name = agent_name
        self._context = context
        self._status_service = status_service
        self._tracked_methods = tracked_methods
        self._loop_to = loop_to
        self._child_proxy_factory = child_proxy_factory
        self._invocation_count = 0
        self._async_runner = async_runner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._agent, name)
        if name not in self._tracked_methods or not callable(attr):
            return attr

        def _tracked_call(*args: Any, **kwargs: Any) -> Any:
            return self._invoke_tracked(attr, *args, **kwargs)

        return _tracked_call

    def _invoke_tracked(self, method: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self._invocation_count += 1
        loop_from = self._context.loop_from
        loop_to = self._context.loop_to or self._loop_to
        if self._loop_to is not None:
            loop_from = self._invocation_count
            loop_to = self._loop_to

        agent_process_status = self._run_async(
            self._create_agent_process(loop_from, loop_to)
        )
        if self._child_proxy_factory is not None:
            self._child_proxy_factory(agent_process_status)

        try:
            response = method(*args, **kwargs)
        except Exception as exc:
            self._run_async(
                self._mark_agent_process_failed(agent_process_status, str(exc))
            )
            raise

        self._run_async(
            self._mark_agent_process_succeeded(
                agent_process_status,
                self._extract_result(response),
            )
        )
        return response

    def _run_async(self, coroutine: Coroutine[Any, Any, Any]) -> Any:
        if self._async_runner is not None:
            return self._async_runner(coroutine)
        return asyncio.run(coroutine)

    async def _create_agent_process(
        self,
        loop_from: int | None,
        loop_to: int | None,
    ) -> AgentProcessStatus:
        return await self._status_service.create_agent_process(
            process_status_id=self._context.process_status_id,
            parent_agent_process_status_id=(
                self._context.parent_agent_process_status_id
            ),
            name=self._agent_name,
            loop_from=loop_from,
            loop_to=loop_to,
        )

    async def _mark_agent_process_succeeded(
        self,
        agent_process_status: AgentProcessStatus,
        result: str | None,
    ) -> AgentProcessStatus:
        return await self._status_service.mark_agent_process_succeeded(
            agent_process_status=agent_process_status,
            result=result,
        )

    async def _mark_agent_process_failed(
        self,
        agent_process_status: AgentProcessStatus,
        result: str | None,
    ) -> AgentProcessStatus:
        return await self._status_service.mark_agent_process_failed(
            agent_process_status=agent_process_status,
            result=result,
        )

    @staticmethod
    def _extract_result(response: Any) -> str:
        for attr in ("reviewed_markdown", "translated_markdown", "revised_post"):
            value = getattr(response, attr, None)
            if value is not None:
                return str(value)

        model_dump_json = getattr(response, "model_dump_json", None)
        if callable(model_dump_json):
            return str(model_dump_json())

        return str(response)
