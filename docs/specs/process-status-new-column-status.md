# Add Status to ProcessStatus

## Objective
- Add a top-level `status` key to each `ProcessStatus` so clients can read the overall workflow state without calculating it from nested agent records.
- Support these process states:

```python
Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]
```

## Background
- The first process-status implementation added status tracking to `AgentProcessStatus` but did not add a status field to the parent `ProcessStatus` entity.
- Today, `labs/process_status/models.py` defines `AgentProcessStatus.status`, while `ProcessStatus` only stores `id`, `file`, `created_at`, and `user_id`.
- `ProcessStatusResponse` currently returns process metadata and nested agent process summaries under `data`, but it does not expose the aggregate process status.
- The frontend needs the parent process state to reflect the state of all related `AgentProcessStatus` records.

## Scope
### In Scope
- Add `status` to the persisted `ProcessStatus` document.
- Add `status` to `ProcessStatusResponse`.
- Derive the parent process status from all related `AgentProcessStatus` records.
- Keep `ProcessStatus.status` current when agent process statuses change.
- Update focused unit tests for the model, schema, repository, service, and router behavior.

### Out of Scope
- Adding new process status values beyond `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.
- Changing `AgentProcessStatus` status values or endpoint paths.
- Changing how agent process records are nested under `data`.
- Reworking background job orchestration beyond the status synchronization required here.
- Running a MongoDB backfill migration; existing MongoDB rows are test data only.

## Proposed Approach
- In `labs/process_status/models.py`, introduce a parent process status type and add `status` to `ProcessStatus`.
- Reuse the same literal value set used by `AgentProcessStatusState`, either by sharing a common alias or defining `ProcessStatusState = Literal["IN_PROGRESS", "FAILED", "SUCCEEDED"]`.
- Default new `ProcessStatus` records to `IN_PROGRESS`.
- In `labs/process_status/schemas.py`, add `status` to `ProcessStatusResponse` and populate it from `process_status.status`.
- In `labs/process_status/service.py`, add a small aggregation helper that derives the parent status from the related agent process records:
  - If any agent status is `FAILED`, the process status is `FAILED`.
  - Else, if any agent status is `IN_PROGRESS`, the process status is `IN_PROGRESS`.
  - Else, if all agent statuses are `SUCCEEDED`, the process status is `SUCCEEDED`.
  - If there are no agent process records yet, keep the process status as `IN_PROGRESS`.
- Persist the derived value to `ProcessStatus.status` after agent status changes. The natural update points are `mark_agent_process_succeeded` and `mark_agent_process_failed`, because both already receive the updated agent record and know the parent `process_status_id`.
- Every agent status change must verify the parent process status by listing all related agent process records, deriving the aggregate value, and saving the parent `ProcessStatus` when the value changed.
- `get_process_with_agent_processes` should return the stored `ProcessStatus.status`; it should not be responsible for recalculating status on every read.
- In `labs/process_status/repository.py`, ensure `create` initializes `ProcessStatus(status="IN_PROGRESS")` if the model default alone is not enough for tests or clarity.

## Milestones
1. Update the data contract.
   - Add `ProcessStatus.status` in `labs/process_status/models.py`.
   - Add `status` to `ProcessStatusResponse` in `labs/process_status/schemas.py`.
   - Update model construction helpers in tests to include the new field.

2. Add status aggregation.
   - Add a service helper to derive the parent status from a list of `AgentProcessStatus` records.
   - Define deterministic precedence for mixed states: `FAILED` first, then `IN_PROGRESS`, then `SUCCEEDED`.
   - Treat an empty agent list as `IN_PROGRESS`.

3. Persist parent status updates.
   - After an agent process is marked `SUCCEEDED` or `FAILED`, list all agent process records for the same `process_status_id`.
   - Derive the parent status.
   - Fetch and save the related `ProcessStatus` with the derived status when the value changed.
   - Do not defer this recalculation to process-status reads.

4. Return the status through the API.
   - Include top-level `status` in `GET /labs/processes/{process_id}/status`.
   - Keep nested agent statuses unchanged.

5. Update tests.
   - Cover model/schema serialization.
   - Cover aggregation rules for all-succeeded, any-failed, any-in-progress, and empty agent lists.
   - Cover router JSON shape including top-level `status`.

## Edge Cases
- A process exists before any agent records are created: status should remain `IN_PROGRESS`.
- One agent is `FAILED` while another is still `IN_PROGRESS`: status should be `FAILED` to surface terminal failure immediately.
- Parent and child agent records should both participate in aggregation; do not only check root-level agents.
- Existing MongoDB documents without `status` may deserialize without the new required field unless the model supplies a default.

## Acceptance Criteria
- [ ] `ProcessStatus` has a `status` field with values limited to `IN_PROGRESS`, `FAILED`, and `SUCCEEDED`.
- [ ] New process records start with `status="IN_PROGRESS"`.
- [ ] `ProcessStatusResponse` includes top-level `status`.
- [ ] If any related `AgentProcessStatus.status` is `FAILED`, the parent `ProcessStatus.status` is `FAILED`.
- [ ] If no related agent failed and any related `AgentProcessStatus.status` is `IN_PROGRESS`, the parent `ProcessStatus.status` is `IN_PROGRESS`.
- [ ] If every related `AgentProcessStatus.status` is `SUCCEEDED`, the parent `ProcessStatus.status` is `SUCCEEDED`.
- [ ] Each agent status change verifies and persists the correct parent `ProcessStatus.status`.
- [ ] Nested agent status response behavior remains unchanged.
- [ ] Existing process documents without a stored `status` can still be read with a default `IN_PROGRESS`.
- [ ] No migration is required for existing MongoDB test rows.

## Test Plan
- Unit:
  - `tests/test_process_status_models.py`
    - Assert `ProcessStatus` exposes `status`.
    - Assert `ProcessStatusResponse.from_process_status` includes `status`.
  - `tests/test_process_status_service.py`
    - Assert status aggregation returns `SUCCEEDED` when all agents succeeded.
    - Assert status aggregation returns `FAILED` when any agent failed.
    - Assert status aggregation returns `IN_PROGRESS` when any agent is still in progress and no agent failed.
    - Assert empty agent list keeps `IN_PROGRESS`.
    - Assert marking an agent succeeded or failed updates the parent process status.
  - `tests/test_process_status_repository.py`
    - Assert process creation persists the default `IN_PROGRESS` status.

- Integration:
  - `tests/test_process_status_router.py`
    - Assert `GET /labs/processes/{process_id}/status` returns top-level `status`.
    - Assert nested agent status payloads remain unchanged and still exclude `result`.

- Manual verification:
  - Start a review workflow.
  - Call `GET /labs/processes/{process_id}/status` while agents are running and confirm `status` is `IN_PROGRESS`.
  - Confirm the same endpoint returns `SUCCEEDED` when all agents finish successfully.
  - Force or simulate an agent failure and confirm the endpoint returns `FAILED`.

## Risks and Mitigations
- Risk: Existing MongoDB process documents do not contain `status`.
  - Mitigation: Give `ProcessStatus.status` a default of `IN_PROGRESS` so existing test documents can still be loaded; no migration is required.

- Risk: Parent status can become stale if future code updates `AgentProcessStatus` outside the service methods.
  - Mitigation: Keep agent status writes centralized through service methods that must recalculate and persist parent status immediately after each agent status change.

- Risk: Mixed `FAILED` and `IN_PROGRESS` agent states are ambiguous.
  - Mitigation: Use deterministic precedence where `FAILED` wins over `IN_PROGRESS`, because failure is the most important terminal state for clients.

## Open Questions
- None.
