# Process Status And Agent Process Status Integration Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/process-status-and-agent-process-status-integration.md
```

This plan integrates `labs/process_status` with the `labs/agents` workflow so `/labs/review` creates a process record and each tracked agent invocation creates an agent-process record linked by `process_status_id`.

## Decisions To Preserve

- Rename `AgentStatus` to `AgentProcessStatus`.
- Store agent process records in MongoDB collection `agent_process_status`.
- Do not embed agent status data in `ProcessStatus`.
- Relate `AgentProcessStatus` to `ProcessStatus` through `process_status_id`.
- Represent nested agent calls with `parent_agent_process_status_id`.
- Keep process status endpoint as `GET /labs/processes/{process_id}/status`.
- Add `GET /labs/agent-process/{agent_process_id}`.
- Exclude `result` from the process status endpoint.
- Include `result` in the agent-process detail endpoint.
- Store full Markdown/content result from each agent.
- Use a **Proxy** around agents, not a decorator or event system.
- Preserve current fallback behavior; failed child agents do not automatically fail the parent if the workflow continues.

## Phase 1: Model Migration

Files:

```text
labs/process_status/models.py
labs/process_status/schemas.py
labs/process_status/__init__.py
tests/test_process_status_models.py
```

Steps:

1. Rename `AgentStatus` to `AgentProcessStatus`.
2. Change `AgentProcessStatus` from embedded `BaseModel` to Beanie `Document`.
3. Add fields:

```text
process_status_id
parent_agent_process_status_id
name
status
loop_from
loop_to
finished_at
result
```

4. Set collection name:

```text
agent_process_status
```

5. Remove persisted `data` from `ProcessStatus`.
6. Keep `ProcessStatus` fields:

```text
id
file
created_at
user_id
```

7. Update exports/imports from `AgentStatus` to `AgentProcessStatus`.

Deliverable:

- Process and agent-process documents are modeled as separate collections.

## Phase 2: Beanie Registration

Files:

```text
core/database/mongodb.py
```

Steps:

1. Register both document models in Beanie:

```text
ProcessStatus
AgentProcessStatus
```

2. Keep MongoDB lifecycle ownership in `core/database/mongodb.py`.
3. Do not add workflow behavior in database lifecycle code.

Deliverable:

- App startup initializes both MongoDB document models.

## Phase 3: Repository Split

Files:

```text
labs/process_status/repository.py
```

Steps:

1. Keep `ProcessStatusRepository` focused on process records:
   - create process
   - get process by id and user id
   - save process if needed

2. Add `AgentProcessStatusRepository`:
   - create agent process
   - get agent process by id
   - list agent processes by `process_status_id`
   - list children by `parent_agent_process_status_id`
   - update status/result/finished_at

3. Keep all Beanie query syntax inside repositories.
4. Keep repositories async.

Deliverable:

- Persistence operations are separated by collection and ready for service composition.

## Phase 4: Service Composition

Files:

```text
labs/process_status/service.py
```

Steps:

1. Update `ProcessStatusService` to depend on both repositories.
2. Add `create_process_for_review(file, user_id)`.
3. Add `create_agent_process(...)`.
4. Add status update methods:
   - `mark_agent_process_succeeded(agent_process_id, result=None)`
   - `mark_agent_process_failed(agent_process_id, result=None)`
5. Add read methods:
   - `get_process_with_agent_processes(process_id, user_id)`
   - `get_agent_process_with_children(agent_process_id, user_id)`
6. Build response trees in the service:
   - fetch all agent process records for a process,
   - group by `parent_agent_process_status_id`,
   - return top-level records under process `data`.
7. Enforce user scoping by checking the owning `ProcessStatus` before returning agent process details.

Deliverable:

- Service layer can create process/agent-process records and assemble nested response trees.

## Phase 5: Response Schemas

Files:

```text
labs/process_status/schemas.py
```

Steps:

1. Update process response schemas to assemble `data` from `AgentProcessStatus`.
2. Ensure process status response excludes `result`.
3. Add agent-process detail response schema that includes `result`.
4. Preserve recursive `children`.

Recommended schemas:

```text
AgentProcessStatusSummaryResponse
AgentProcessStatusDetailResponse
ProcessStatusResponse
```

Deliverable:

- API serialization matches both endpoint contracts.

## Phase 6: Endpoint Updates

Files:

```text
labs/process_status/router.py
tests/test_process_status_router.py
```

Steps:

1. Keep:

```text
GET /labs/processes/{process_id}/status
```

2. Add:

```text
GET /labs/agent-process/{agent_process_id}
```

3. Protect both endpoints with `get_current_user`.
4. Use `parse_user_id` from `core/auth/service.py`.
5. Return `404` when:
   - process does not exist,
   - process belongs to another user,
   - agent process does not exist,
   - agent process belongs to a process owned by another user.
6. Verify process endpoint never returns `result`.
7. Verify agent-process endpoint returns `result`.

Deliverable:

- Authenticated users can read process status trees and individual agent-process results.

## Phase 7: Workflow Context

Recommended files:

```text
labs/process_status/context.py
labs/process_status/proxy.py
```

Steps:

1. Add a lightweight workflow context carrying:

```text
process_status_id
parent_agent_process_status_id
loop_from
loop_to
```

2. Keep context explicit and testable.
3. Do not store request content in the context.

Deliverable:

- Agent proxies can know which process and parent agent-process they belong to.

## Phase 8: Agent Proxy

Recommended file:

```text
labs/process_status/proxy.py
```

Steps:

1. Implement proxy classes or one generic proxy factory around agent methods.
2. Proxy responsibilities:
   - create `AgentProcessStatus` with `IN_PROGRESS`,
   - invoke the wrapped agent method,
   - extract full Markdown/content result from the response,
   - mark the agent process `SUCCEEDED`,
   - on exception, mark it `FAILED` and re-raise or preserve existing fallback behavior according to the wrapped call site.
3. Keep concrete agent classes persistence-unaware.
4. Preserve existing agent method names and return values.
5. Support parent-child tracking by accepting workflow context.

Initial tracked invocations:

```text
LabPostWriterAgent.organize_notes
LabCodeExampleAgent.extract_examples
LabReviewerAgent.revise
LabPostMetadataAgent.generate
LabPostTranslatorAgent.translate
```

Deliverable:

- Status lifecycle is centralized in proxy code rather than scattered across agent implementations.

## Phase 9: Workflow Entry Integration

Files:

```text
labs/agents/router.py
labs/agents/service.py
labs/helpers/markdown_helper.py
tests/test_service.py
tests/test_auth_routes.py
```

Steps:

1. Update the authenticated `/labs/review` route to pass the current user into service orchestration.
2. After file validation, create a `ProcessStatus` record.
3. Return `process_id` in the `/labs/review` response.
4. Pass `process_status_id` into the background task.
5. Preserve existing response fields:

```text
message
output_file
```

6. Add:

```text
process_id
```

7. Do not change generated Markdown/PDF file behavior.

Deliverable:

- Every accepted review request has a process record before background processing starts.

## Phase 10: Agent Invocation Integration

Files likely affected:

```text
labs/helpers/markdown_helper.py
labs/agents/service.py
labs/agents/labs_post_writer/agent.py
```

Steps:

1. Wrap top-level writer invocation with the proxy.
2. Ensure writer proxy creates the parent `Labs Writer` agent-process record.
3. Make nested writer dependencies trackable:
   - code-example invocation becomes a child of writer,
   - reviewer invocations become children of writer,
   - reviewer loop metadata is set with `loop_from` and `loop_to`.
4. Wrap metadata invocation as a top-level agent process.
5. Wrap translator invocation as a top-level agent process.
6. Store full Markdown/content result for each completed agent.
7. Preserve current fallback behavior:
   - metadata fallback still works,
   - reviewer fallback still works,
   - Markdown/PDF persistence behavior is unchanged.

Deliverable:

- Each tracked agent invocation creates and updates an `AgentProcessStatus` document.

## Phase 11: Tests

New or updated test files:

```text
tests/test_process_status_models.py
tests/test_process_status_repository.py
tests/test_process_status_service.py
tests/test_process_status_router.py
tests/test_service.py
tests/test_auth_routes.py
tests/test_helper.py
tests/test_labs_post_writer_agent.py
```

Model tests:

- `AgentProcessStatus` uses collection `agent_process_status`.
- `AgentProcessStatus` requires `process_status_id`.
- `AgentProcessStatus` supports parent-child ids.
- `ProcessStatus` no longer persists embedded `data`.

Repository/service tests:

- process creation works,
- agent-process creation works,
- status/result update works,
- process tree assembly works,
- agent-process detail tree assembly works,
- user scoping is enforced.

Router tests:

- `GET /labs/processes/{process_id}/status` returns process tree without `result`.
- `GET /labs/agent-process/{agent_process_id}` returns detail with `result`.
- other users receive `404`.
- missing auth returns `401`.

Workflow tests:

- `/labs/review` creates a process after validation.
- `/labs/review` returns `process_id`.
- writer invocation creates parent agent process.
- code-example/reviewer invocations create child agent processes.
- metadata and translator invocations create top-level agent processes.
- fallback paths keep current behavior.

## Phase 12: Verification

Focused commands:

```bash
venv/bin/python -m pytest -q tests/test_process_status_models.py
venv/bin/python -m pytest -q tests/test_process_status_repository.py
venv/bin/python -m pytest -q tests/test_process_status_service.py
venv/bin/python -m pytest -q tests/test_process_status_router.py
venv/bin/python -m pytest -q tests/test_service.py tests/test_auth_routes.py tests/test_helper.py
```

Full verification:

```bash
venv/bin/python -m pytest -q
```

Manual verification:

1. Start the app with MongoDB reachable.
2. Submit a Markdown file to `POST /labs/review`.
3. Confirm response includes `process_id`.
4. Call `GET /labs/processes/{process_id}/status`.
5. Confirm the response includes related agent processes under `data`.
6. Confirm no `result` key appears in the process status response.
7. Call `GET /labs/agent-process/{agent_process_id}`.
8. Confirm the response includes `result`.
9. Confirm another user cannot read the process or agent-process.

## Rollback Strategy

1. Keep the existing `ProcessStatus` collection intact.
2. If agent proxy integration breaks workflow execution, temporarily bypass proxy wrapping and keep process creation only.
3. If endpoint behavior breaks, unregister the new `/labs/agent-process/{agent_process_id}` route first.
4. If model migration causes startup issues, revert Beanie registration of `AgentProcessStatus`.
5. Preserve current Markdown/PDF output behavior throughout rollback.

## Definition Of Done

- `AgentStatus` is fully replaced by `AgentProcessStatus`.
- `AgentProcessStatus` is a separate document in `agent_process_status`.
- `ProcessStatus` does not persist embedded `data`.
- `/labs/review` creates a process and returns `process_id`.
- Agent invocations create/update agent-process records through proxies.
- Nested writer children are represented with `parent_agent_process_status_id`.
- `GET /labs/processes/{process_id}/status` returns process tree without `result`.
- `GET /labs/agent-process/{agent_process_id}` returns agent process detail with `result`.
- User scoping is enforced for both endpoints.
- Existing Markdown/PDF output behavior remains intact.
- Targeted and full tests pass.
