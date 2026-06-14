# Process Status And Agent Process Status Integration

## Objective

Integrate the existing `labs/process_status` persistence layer with the `labs/agents` workflow so each `/labs/review` request creates a process record, and each agent invocation creates an agent-process record linked by `process_status_id`.

This spec defines the intended integration and endpoint contracts. It does not implement code.

## Background / Current Behavior

The current workflow is:

- `POST /labs/review` is handled by `labs/agents/router.py`.
- The router delegates to `LabPostService.enqueue_markdown_organization(...)`.
- `LabPostService` validates the uploaded Markdown file and schedules `MarkdownHelper.process_and_save_markdown(...)` as a FastAPI background task.
- `MarkdownHelper.process_and_save_markdown(...)` runs:
  - `writer_agent.organize_notes(...)`
  - `metadata_agent.generate(...)`
  - `translator_agent.translate(...)`
  - Markdown/PDF output persistence

Inside `LabPostWriterAgent.organize_notes(...)`, the writer currently invokes nested agents:

- `LabCodeExampleAgent.extract_examples(...)`
- `LabReviewerAgent.revise(...)`, up to three review loops

The current `labs/process_status` setup has:

- `ProcessStatus`
- `AgentStatus`
- `ProcessStatusRepository`
- `ProcessStatusService`
- `GET /labs/processes/{process_id}/status`

This spec changes that model. Agent execution should no longer be embedded directly in `ProcessStatus`. Agent executions become separate persisted records named `AgentProcessStatus`.

## Scope

In scope:

- Rename `AgentStatus` to `AgentProcessStatus`.
- Make agent process records separate MongoDB documents.
- Add `process_status_id` to `AgentProcessStatus`.
- Add a parent id field for nested agent process records.
- Create one `ProcessStatus` record for every `/labs/review` request.
- Create one `AgentProcessStatus` record for every tracked agent invocation.
- Return process status with related agent process records nested under `data`.
- Keep `GET /labs/processes/{process_id}/status`.
- Add `GET /labs/agent-process/{agent_process_id}`.
- Return `result` only from the agent-process detail endpoint.
- Keep user scoping on process and agent-process reads.

Out of scope:

- Changing prompt content or agent behavior.
- Changing Markdown/PDF output format.
- Creating a separate analytics/history collection.
- Adding retries, queues, or distributed tracing.
- Returning agent `result` from the process endpoint.

## Data Model

### ProcessStatus

`ProcessStatus` represents the user request and uploaded file.

Recommended persisted fields:

```python
class ProcessStatus(Document):
    id: UUID
    file: str
    created_at: datetime
    user_id: UUID

    class Settings:
        name = "process_status"
```

`ProcessStatus` should not persist a `data` array. The `data` response field should be assembled by querying `AgentProcessStatus` documents with the matching `process_status_id`.

### AgentProcessStatus

`AgentProcessStatus` represents one invocation of an agent or sub-agent.

Recommended persisted fields:

```python
class AgentProcessStatus(Document):
    id: UUID
    process_status_id: UUID
    parent_agent_process_status_id: UUID | None = None
    name: str
    status: Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
    loop_from: int | None = None
    loop_to: int | None = None
    finished_at: datetime | None = None
    result: str | None = None

    class Settings:
        name = "agent_process_status"
```

Notes:

- `process_status_id` is a plain UUID reference, not a Beanie `Link`.
- `parent_agent_process_status_id` is needed to build `children` for nested agents.
- The writer agent can be represented as a parent record.
- Reviewer and code-example invocations inside writer can be child records.
- `result` is persisted but hidden from the process endpoint.

## Endpoint Contracts

### Get Process

Endpoint:

```text
GET /labs/processes/{process_id}/status
```

Purpose:

- Return the process and all related agent process statuses.
- Exclude every `result` field.
- Include only agent process records whose `process_status_id` matches the process id.
- Nest child agent process records using `parent_agent_process_status_id`.

Response shape:

```json
{
  "id": "UUID",
  "file": "notes.md",
  "created_at": "2026-06-09T09:45:00Z",
  "user_id": "UUID",
  "data": [
    {
      "id": "UUID",
      "name": "Labs Writer",
      "status": "IN_PROGRESS",
      "finished_at": null,
      "children": [
        {
          "id": "UUID",
          "name": "Labs Reviewer",
          "status": "IN_PROGRESS",
          "loop_from": 1,
          "loop_to": 3,
          "finished_at": null,
          "children": []
        },
        {
          "id": "UUID",
          "name": "Labs Code Examples",
          "status": "SUCCEEDED",
          "loop_from": 1,
          "loop_to": 1,
          "finished_at": "2026-06-09T09:59:00Z",
          "children": []
        }
      ]
    },
    {
      "id": "UUID",
      "name": "Labs Translator",
      "status": "SUCCEEDED",
      "finished_at": "2026-06-09T10:02:00Z",
      "children": []
    },
    {
      "id": "UUID",
      "name": "Labs Metadata",
      "status": "FAILED",
      "finished_at": "2026-06-09T10:03:00Z",
      "children": []
    }
  ]
}
```

### Get Agent Process

Endpoint:

```text
GET /labs/agent-process/{agent_process_id}
```

Purpose:

- Return a single agent process by id.
- Include nested child agent process statuses.
- Include `result`.
- Ensure the agent process belongs to a process owned by the authenticated user.

Response shape:

```json
{
  "id": "UUID",
  "name": "Labs Writer",
  "status": "IN_PROGRESS",
  "finished_at": null,
  "children": [
    {
      "id": "UUID",
      "name": "Labs Reviewer",
      "status": "IN_PROGRESS",
      "loop_from": 1,
      "loop_to": 3,
      "finished_at": null,
      "children": []
    },
    {
      "id": "UUID",
      "name": "Labs Code Examples",
      "status": "SUCCEEDED",
      "loop_from": 1,
      "loop_to": 1,
      "finished_at": "2026-06-09T09:59:00Z",
      "children": []
    }
  ],
  "result": "MARKDOWN_CONTENT"
}
```

## Proposed Approach

### Repository Layer

Create separate repository responsibilities:

- `ProcessStatusRepository`
  - create process
  - get process by id and user id
  - save process if future fields are added

- `AgentProcessStatusRepository`
  - create agent process
  - get agent process by id
  - list agent processes by `process_status_id`
  - list child agent processes by `parent_agent_process_status_id`
  - update status/result/finished_at

### Service Layer

Create service methods that compose process and agent-process data:

- `create_process_for_review(file, user_id)`
- `create_agent_process(process_status_id, name, parent_agent_process_status_id=None, loop_from=None, loop_to=None)`
- `mark_agent_process_succeeded(agent_process_id, result=None)`
- `mark_agent_process_failed(agent_process_id, result=None)`
- `get_process_with_agent_processes(process_id, user_id)`
- `get_agent_process_with_children(agent_process_id, user_id)`

The service should own response assembly:

- Fetch `ProcessStatus`.
- Fetch all `AgentProcessStatus` documents for `process_status_id`.
- Build a tree by grouping records by `parent_agent_process_status_id`.
- Return top-level agent records under `data`.

### Workflow Integration

When `/labs/review` receives a valid Markdown request:

1. Create a `ProcessStatus` record immediately.
2. Return the `process_id` in the `/labs/review` response.
3. Schedule background processing with the `process_status_id`.
4. During background processing, create agent process records as agents are invoked.

Expected `/labs/review` response change:

```json
{
  "message": "Processing started.",
  "process_id": "UUID",
  "output_file": "public/markdown/notes_reviewd.md"
}
```

### Agent Invocation Tracking

Each tracked agent invocation should create a record with `status="IN_PROGRESS"` before the agent call starts.

On success:

- Set `status="SUCCEEDED"`.
- Set `finished_at`.
- Store the full Markdown/content result from the agent in `result`.

On failure:

- Set `status="FAILED"`.
- Set `finished_at`.
- Store the resulting fallback content or error message in `result`.
- Preserve the current fallback behavior. A failed child agent does not automatically force the parent process to fail if the current workflow can continue.

Initial tracked agent names:

- `Labs Writer`
- `Labs Reviewer`
- `Labs Code Examples`
- `Labs Metadata`
- `Labs Translator`

## Design Pattern Analysis

The current codebase has synchronous agent methods and direct nested calls. `LabPostWriterAgent.organize_notes(...)` calls both `LabCodeExampleAgent.extract_examples(...)` and `LabReviewerAgent.revise(...)`. The background task helper also directly calls metadata and translator agents.

The integration needs to create MongoDB records around each invocation without turning every agent into a persistence-aware class.

### Option A: Explicit Orchestration Calls

Add `ProcessStatusService` calls directly before and after every agent invocation.

Pros:

- Simple to understand.
- Easy to test in the short term.
- No abstraction overhead.

Cons:

- Persistence logic spreads through `MarkdownHelper`, `LabPostService`, and agent methods.
- Nested writer/reviewer/code-example tracking requires editing `LabPostWriterAgent`.
- Harder to keep agent code focused on LLM behavior.

### Option B: Proxy Around Agents

Wrap each agent with a tracking proxy that creates and updates `AgentProcessStatus` around method calls.

Pros:

- Keeps core agent methods mostly focused on agent behavior.
- Centralizes status create/succeed/fail logic.
- Fits the current synchronous method style.
- Can be introduced incrementally per agent.

Cons:

- Nested calls still need parent context propagation.
- Method-specific result extraction is needed because each agent returns a different schema.
- Requires careful typing to avoid hiding agent interfaces.

### Option C: Observer / Domain Events

Emit domain events like `agent_started`, `agent_succeeded`, and `agent_failed`; subscribe with a MongoDB status recorder.

Pros:

- Strong separation between workflow events and persistence.
- Flexible for future logging, metrics, and analytics.
- Cleanest long-term architecture if the workflow grows.

Cons:

- More infrastructure than the current codebase has.
- Requires an event bus or dispatcher.
- Async persistence from sync agent methods needs careful handling.
- More moving pieces for the immediate feature.

### Recommendation

Use **Option B: Proxy Around Agents** for the first implementation.

Reasoning:

- The current codebase is small and direct, so a full event system would be premature.
- Explicit status writes would work, but would couple MongoDB tracking to agent logic quickly.
- A tracking proxy can centralize status lifecycle while preserving current agent APIs.
- A proxy is more appropriate than a decorator here because tracking does not need to enhance or transform the returned agent result.
- Parent-child context can be passed through a lightweight workflow context object.

Proxy classes should live outside the concrete agent classes and should not make agent implementations persistence-aware.

## Milestones

### Milestone 1: Model Migration

Files:

```text
labs/process_status/models.py
labs/process_status/schemas.py
labs/process_status/repository.py
labs/process_status/service.py
labs/process_status/router.py
tests/test_process_status_*.py
```

Steps:

1. Rename `AgentStatus` to `AgentProcessStatus`.
2. Convert `AgentProcessStatus` into a Beanie `Document`.
3. Add `process_status_id`.
4. Add `parent_agent_process_status_id`.
5. Remove persisted `data` from `ProcessStatus`.
6. Update schemas so process responses assemble `data` from related agent process records.

### Milestone 2: Repository And Service Split

Steps:

1. Keep `ProcessStatusRepository` focused on process records.
2. Add `AgentProcessStatusRepository`.
3. Add service methods for:
   - creating process records,
   - creating agent process records,
   - updating agent status/result,
   - retrieving process tree,
   - retrieving agent process detail.
4. Ensure user scoping is enforced when reading both process and agent-process endpoints.

### Milestone 3: Endpoint Changes

Steps:

1. Keep `GET /labs/processes/{process_id}/status`.
2. Add `GET /labs/agent-process/{agent_process_id}`.
3. Ensure `/labs/processes/{process_id}/status` excludes `result`.
4. Ensure `/labs/agent-process/{agent_process_id}` includes `result`.

### Milestone 4: Workflow Entry Integration

Steps:

1. Update `/labs/review` flow to create `ProcessStatus` after file validation.
2. Return `process_id` in the response.
3. Pass `process_status_id` into background processing.
4. Do not change the Markdown/PDF output behavior.

### Milestone 5: Agent Invocation Tracking

Steps for the selected proxy approach:

1. Add a workflow context object that carries:
   - `process_status_id`,
   - current parent `agent_process_status_id`,
   - loop metadata when available.
2. Add tracking wrappers for:
   - writer,
   - reviewer,
   - code examples,
   - metadata,
   - translator.
3. Ensure nested reviewer/code-example records use writer's agent process id as parent.
4. Store result values from each agent response.
5. Preserve existing fallback behavior for failures.

## Acceptance Criteria

- `AgentStatus` is renamed to `AgentProcessStatus`.
- `AgentProcessStatus` includes `process_status_id`.
- `AgentProcessStatus` supports parent-child nesting.
- `AgentProcessStatus` uses collection name `agent_process_status`.
- `ProcessStatus` no longer stores embedded agent status `data`.
- `/labs/review` creates a `ProcessStatus` record.
- `/labs/review` response includes `process_id`.
- Each tracked agent invocation creates an `AgentProcessStatus` record.
- Agent process records are updated to `SUCCEEDED` or `FAILED`.
- `GET /labs/processes/{process_id}/status` returns only agent process records related to that process.
- `GET /labs/processes/{process_id}/status` excludes `result`.
- `GET /labs/agent-process/{agent_process_id}` includes `result`.
- `AgentProcessStatus.result` stores the full Markdown/content result from the agent.
- Failed child agents reflect the current fallback behavior instead of automatically failing the parent.
- Reads are scoped to the authenticated user.

## Test Plan

Add or update tests for:

- Model rename and imports.
- `AgentProcessStatus` collection name and required fields.
- Process records without embedded `data`.
- Repository create/read/update for process records.
- Repository create/read/update for agent process records.
- Service tree assembly from flat agent process records.
- Process status endpoint excludes `result`.
- Agent-process endpoint includes `result`.
- User A cannot read User B's process.
- User A cannot read User B's agent process.
- `/labs/review` creates a process record after validation.
- `/labs/review` returns `process_id`.
- Agent tracking creates parent/child records for writer, reviewer, and code examples.
- Metadata and translator tracking create top-level records.
- Failed agent invocations are marked `FAILED` where the invocation itself fails, while parent status follows existing fallback behavior.

## Risks And Mitigations

- Risk: Agent tracking code spreads across agent implementations.
  Mitigation: use a proxy and workflow context instead of direct MongoDB calls inside each agent.

- Risk: Sync agent methods with async MongoDB writes can complicate background processing.
  Mitigation: move workflow orchestration toward an async service boundary or use a controlled async bridge inside the background task.

- Risk: Storing full Markdown in `result` can create large MongoDB documents.
  Mitigation: store results initially as required, then evaluate moving large content to file references if document size becomes a problem.

## Resolved Decisions

1. Tracking pattern:
   Use a proxy around agents. Do not use decorators or an observer/domain-event system for the first implementation.

2. Process status endpoint:
   Keep only `GET /labs/processes/{process_id}/status`. Do not add `GET /labs/process/{process_id}`.

3. Agent process result:
   Store the full Markdown/content result from the agent.

4. Parent/child failure behavior:
   Parent status should reflect current fallback behavior. A failed child does not automatically fail the parent if the existing workflow continues.

5. Agent process collection:
   Use `agent_process_status`.
