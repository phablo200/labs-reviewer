# Process Status New Column Status Plan

## Source Spec

Implementation source of truth:

```text
docs/specs/process-status-new-column-status.md
```

This plan adds a persisted top-level `status` field to `ProcessStatus`, exposes it in the process status endpoint, and keeps it synchronized from related `AgentProcessStatus` records whenever an agent status changes.

## Decisions To Preserve

- Supported status values are:

```python
Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

- New `ProcessStatus` records start as `IN_PROGRESS`.
- Parent process status is derived from every related `AgentProcessStatus`, including parent and child agent records.
- Status precedence is:
  - `FAILED` wins when any related agent failed.
  - `IN_PROGRESS` wins when no agent failed and at least one related agent is still running.
  - `SUCCEEDED` applies only when every related agent succeeded.
- An empty agent list keeps the process status as `IN_PROGRESS`.
- Every agent status change must verify and persist the parent `ProcessStatus.status`.
- Do not recalculate parent process status on every status read; reads return the stored value.
- Do not run a MongoDB migration or backfill; existing MongoDB rows are test data only.

## Phase 1: Model Contract

Files:

```text
labs/process_status/models.py
tests/test_process_status_models.py
```

Steps:

1. Add a process-level status type in `labs/process_status/models.py`.

Recommended alias:

```python
ProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

2. Add `status` to `ProcessStatus` with a default:

```python
status: ProcessStatusState = "IN_PROGRESS"
```

3. Keep `AgentProcessStatusState` unchanged. If desired, share one common alias internally, but preserve existing imports used by tests and schemas.
4. Update test helpers that construct `ProcessStatus` to include `status`.
5. Add assertions that:
   - `ProcessStatus.status` exists.
   - default status is `IN_PROGRESS`.
   - collection name remains `process_status`.
   - `ProcessStatus` still does not persist `data`.

Deliverable:

- The persisted process document supports the new status field and remains backward-safe for existing test rows.

## Phase 2: Repository Creation Default

Files:

```text
labs/process_status/repository.py
tests/test_process_status_repository.py
```

Steps:

1. Ensure `ProcessStatusRepository.create` creates process records with `status="IN_PROGRESS"`.
2. Rely on the model default or pass the value explicitly; prefer explicit creation if it makes the behavior clearer in tests.
3. Keep repository methods async and keep Beanie query details inside the repository.
4. Update repository tests to assert created process records have `status == "IN_PROGRESS"`.

Deliverable:

- New process records always start in the running state.

## Phase 3: Response Schema

Files:

```text
labs/process_status/schemas.py
tests/test_process_status_models.py
tests/test_process_status_router.py
```

Steps:

1. Import the process status type into `schemas.py`.
2. Add `status` to `ProcessStatusResponse`.
3. Populate response status from `process_status.status` in `from_process_status`.
4. Update tests to assert process status responses include the top-level `status`.
5. Keep nested agent summary behavior unchanged:
   - include each agent `status`,
   - preserve recursive `children`,
   - exclude `result` from the process status endpoint.

Deliverable:

- `GET /labs/processes/{process_id}/status` can expose the parent process status without changing nested agent response behavior.

## Phase 4: Status Aggregation Service

Files:

```text
labs/process_status/service.py
tests/test_process_status_service.py
```

Steps:

1. Add a helper on `ProcessStatusService` to derive process status from related agent records.

Recommended behavior:

```text
if no agents: IN_PROGRESS
elif any agent.status == FAILED: FAILED
elif any agent.status == IN_PROGRESS: IN_PROGRESS
else: SUCCEEDED
```

2. Keep the helper deterministic and independent of tree nesting; it should inspect the flat list returned by `list_by_process_status_id`.
3. Add unit coverage for:
   - no agents returns `IN_PROGRESS`,
   - all succeeded returns `SUCCEEDED`,
   - any failed returns `FAILED`,
   - any in progress with no failures returns `IN_PROGRESS`,
   - child agents are included because aggregation uses all records for the process.

Deliverable:

- Service logic can calculate the parent state from agent state using the required precedence.

## Phase 5: Persist Parent Status On Agent Changes

Files:

```text
labs/process_status/service.py
tests/test_process_status_service.py
```

Steps:

1. After `_mark_agent_process` updates an `AgentProcessStatus`, list all agent records for `agent_process_status.process_status_id`.
2. Derive the parent status from those records.
3. Fetch the related `ProcessStatus`.
4. If the process exists and its stored status differs from the derived value:
   - assign the derived status,
   - save the process through `ProcessStatusRepository.save`.
5. Return the updated agent process status from the original mark method.
6. Keep `get_process_with_agent_processes` read-focused:
   - fetch process,
   - fetch agent records,
   - build the response,
   - do not recalculate or persist process status during reads.
7. Add unit tests proving:
   - marking one of multiple agents succeeded keeps parent `IN_PROGRESS` if another agent is still running,
   - marking the final running agent succeeded changes parent to `SUCCEEDED`,
   - marking any agent failed changes parent to `FAILED`,
   - reads return the stored parent status without saving the process.

Deliverable:

- Parent status is verified and persisted at the required write-time boundary.

## Phase 6: Router And API Shape

Files:

```text
labs/process_status/router.py
tests/test_process_status_router.py
```

Steps:

1. Keep endpoint path unchanged:

```text
GET /labs/processes/{process_id}/status
```

2. No router behavior change should be needed if `ProcessStatusResponse` contains `status`.
3. Update router fixtures/stubs to include process `status`.
4. Assert endpoint JSON includes:

```json
{
  "status": "IN_PROGRESS"
}
```

5. Keep existing authorization and `404` behavior unchanged.
6. Keep agent-process detail endpoint behavior unchanged.

Deliverable:

- API clients receive the top-level process status in the existing status endpoint response.

## Phase 7: Verification

Commands:

```bash
pytest tests/test_process_status_models.py
pytest tests/test_process_status_repository.py
pytest tests/test_process_status_service.py
pytest tests/test_process_status_router.py
```

Optional broader check:

```bash
pytest
```

Manual verification:

1. Start a review workflow.
2. Call `GET /labs/processes/{process_id}/status` while agents are running and confirm top-level `status` is `IN_PROGRESS`.
3. Let all agents finish and confirm top-level `status` becomes `SUCCEEDED`.
4. Simulate or force an agent failure and confirm top-level `status` becomes `FAILED`.

Deliverable:

- Focused tests validate the new model, response, aggregation, persistence, and endpoint behavior.

## Implementation Notes

- Do not add a migration file or backfill script.
- Do not add new status values.
- Do not remove or rename `AgentProcessStatusState` unless all existing imports are updated.
- Do not embed agent data back into `ProcessStatus`.
- Prefer small service helpers over duplicating status aggregation rules in multiple places.
- Keep the status recalculation path inside agent status write methods so the behavior is hard to bypass.

## Rollback Plan

1. Remove `status` from `ProcessStatusResponse`.
2. Remove service aggregation and parent status update calls.
3. Remove `status` from `ProcessStatus`.
4. Revert the related tests.

No database rollback is required because no migration is planned.
