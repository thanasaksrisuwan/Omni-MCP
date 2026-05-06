# Project Roadmap

This roadmap tracks implementation progress against `docs/SRS.md`.

`docs/SRS.md` remains the source of truth. If this roadmap conflicts with the SRS, follow the SRS and write the concern under `.agent_bus/reports/`.

## Status Values

Use only these task statuses:

- `not_started`
- `in_progress`
- `blocked`
- `needs_review`
- `done`
- `rejected`

Do not mark a task as `done` without evidence.

## Current Phase

Complete / Awaiting Commit

## Phase List

### Phase 1: Backend Day 1 - Route & Dependency Scanner

Status: `done`

Tasks:

- [x] Create valid `.backend-ai/validation-rules.json`
- [x] Implement route scanner using `ast` fallback because `libcst` is unavailable
- [x] Extract `@router.get/post/put/patch/delete`
- [x] Extract route method/path/handler/is_async
- [x] Extract `Depends(...)`
- [x] Extract `Security(..., scopes=[...])`
- [x] Detect `AsyncSession` annotation
- [x] Generate `.backend-ai/index-meta.json`
- [x] Generate `.backend-ai/routes.json`
- [x] Generate `.backend-ai/dependencies.json`
- [x] Add fixture tests
- [x] Run fallback test script because `pytest` is unavailable
- [x] Generate worker report
- [x] Generate architect review

Definition of Done:

- [x] All expected files exist
- [x] All generated JSON is valid
- [x] Tests pass or skipped with documented reason
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

### Phase 2: Backend Day 2 - Session Flow + Transaction Boundary

Status: `done`

Next required action:

- [x] Gemini creates `.agent_bus/tasks/day2_task.md`

Tasks:

- [x] Generate `.backend-ai/session-flow.json`
- [x] Generate `.backend-ai/transaction-boundaries.json`
- [x] Implement `backend.get_session_flow`
- [x] Detect `session.begin()`
- [x] Detect `session.commit()`
- [x] Detect `session.flush()`
- [x] Detect `session.rollback()`
- [x] Detect transaction owner
- [x] Implement TX001-TX007 validator
- [x] Run validator and tests
- [x] Generate worker report
- [x] Generate architect review

Start condition:

- Phase 1 review verdict is `approve`.

Definition of Done:

- [x] Expected Day 2 generated files exist
- [x] Generated JSON is valid
- [x] Fixture tests passed using plain Python assertions
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

### Phase 3: Backend Reservation Safety

Status: `done`

Tasks:

- [x] Gemini creates `.agent_bus/tasks/be_rs_001_task.md`
- [x] Implement state machine manifest/tooling
- [x] Implement `backend.get_state_machine`
- [x] Implement `backend.validate_state_transition`
- [x] Implement `backend.validate_idempotency`
- [x] Implement `backend.validate_outbox_usage`
- [x] Implement `backend.validate_reservation_invariants`
- [x] Validate reservation/payment/stock safety rules
- [x] Generate `.backend-ai/state-machines.json`
- [x] Generate `.backend-ai/outbox-events.json`
- [x] Generate `.backend-ai/invariants.json`
- [x] Add safe/unsafe fixture tests
- [x] Run validator and tests
- [x] Generate worker report
- [x] Generate architect review

Start condition:

- Phase 2 review verdict is `approve`.

Definition of Done:

- [x] Expected Phase 3 generated files exist
- [x] Generated JSON is valid
- [x] Fixture tests passed using plain Python assertions
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

### Phase 4: Frontend MCP Week 1

Status: `done`

Next required action:

- [x] Gemini creates Frontend Week 1 task spec

Tasks:

- [x] Generate `.frontend-ai/index-meta.json`
- [x] Generate `.frontend-ai/components.json`
- [x] Generate `.frontend-ai/props.json`
- [x] Generate `.frontend-ai/tokens.json`
- [x] Generate `.frontend-ai/assets.json`
- [x] Implement `frontend.index_project`
- [x] Implement `frontend.search_components`
- [x] Implement `frontend.get_prop_signature`
- [x] Implement `frontend.validate_ui_code`
- [x] Add fixture tests for FE001-FE008
- [x] Run validator and tests
- [x] Generate worker report
- [x] Generate architect review

Start condition:

- Backend priority work has an approved task spec or explicit architect approval to switch tracks.

Definition of Done:

- [x] Expected Frontend Week 1 generated files exist
- [x] Generated JSON is valid
- [x] Fixture tests passed using plain Python assertions
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

### Phase 5: Frontend Usage + Layout

Status: `done`

Next required action:

- [x] Gemini creates Frontend Usage + Layout task spec

Tasks:

- [x] Generate `.frontend-ai/usages.json`
- [x] Generate `.frontend-ai/layouts.json`
- [x] Implement `frontend.find_component_usages`
- [x] Implement `frontend.get_layout_patterns`
- [x] Validate existing layout/component patterns
- [x] Add fixture tests
- [x] Run validator and tests
- [x] Generate worker report
- [x] Generate architect review

Start condition:

- Phase 4 review verdict is `approve`.

Definition of Done:

- [x] Expected Phase 5 generated files exist
- [x] Generated JSON is valid
- [x] Fixture tests passed using plain Python assertions
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

### Phase 6: Runtime / Visual Validation

Status: `done`

Next required action:

- [x] Gemini creates Runtime / Visual task spec
- [x] Gemini reviews Runtime / Visual worker output

Tasks:

- [x] Add optional Storybook integration
- [x] Add optional Playwright MCP integration
- [x] Add accessibility snapshot support
- [x] Add visual check support
- [x] Generate worker report
- [x] Generate architect review

Start condition:

- Phase 5 review verdict is `approve`.

Definition of Done:

- [x] Expected Phase 6 generated files exist
- [x] Generated JSON is valid
- [x] Fixture tests passed using plain Python assertions
- [x] Worker report is complete
- [x] Architect review verdict is `approve`

---

## Next Recommended Action

- Commit approved changes when ready.
