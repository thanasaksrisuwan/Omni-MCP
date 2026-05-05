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

Backend Day 1: Route & Dependency Scanner

## Phase List

### Phase 1: Backend Day 1 - Route & Dependency Scanner

Status: `in_progress`

Tasks:

- [ ] Create valid `.backend-ai/validation-rules.json`
- [ ] Implement LibCST route scanner
- [ ] Extract `@router.get/post/put/patch/delete`
- [ ] Extract route method/path/handler/is_async
- [ ] Extract `Depends(...)`
- [ ] Extract `Security(..., scopes=[...])`
- [ ] Detect `AsyncSession` annotation
- [ ] Generate `.backend-ai/index-meta.json`
- [ ] Generate `.backend-ai/routes.json`
- [ ] Generate `.backend-ai/dependencies.json`
- [ ] Add fixture tests
- [ ] Run pytest
- [ ] Generate worker report
- [ ] Generate architect review

Definition of Done:

- [ ] All expected files exist
- [ ] All generated JSON is valid
- [ ] Tests pass or skipped with documented reason
- [ ] Worker report is complete
- [ ] Architect review verdict is `approve`

---

### Phase 2: Backend Day 2 - Session Flow + Transaction Boundary

Status: `not_started`

Tasks:

- [ ] Generate `.backend-ai/session-flow.json`
- [ ] Generate `.backend-ai/transaction-boundaries.json`
- [ ] Implement `backend.get_session_flow`
- [ ] Detect `session.begin()`
- [ ] Detect `session.commit()`
- [ ] Detect `session.flush()`
- [ ] Detect `session.rollback()`
- [ ] Detect transaction owner
- [ ] Implement TX001-TX007 validator
- [ ] Run validator and tests
- [ ] Generate worker report
- [ ] Generate architect review

Start condition:

- Phase 1 review verdict is `approve`.

---

### Phase 3: Backend Reservation Safety

Status: `not_started`

Tasks:

- [ ] Implement state machine manifest/tooling
- [ ] Implement `backend.validate_state_transition`
- [ ] Implement `backend.validate_idempotency`
- [ ] Implement `backend.validate_outbox_usage`
- [ ] Implement `backend.validate_reservation_invariants`
- [ ] Validate reservation/payment/stock safety rules
- [ ] Generate worker report
- [ ] Generate architect review

Start condition:

- Phase 2 review verdict is `approve`.

---

### Phase 4: Frontend MCP Week 1

Status: `not_started`

Tasks:

- [ ] Generate `.frontend-ai/index-meta.json`
- [ ] Generate `.frontend-ai/components.json`
- [ ] Generate `.frontend-ai/props.json`
- [ ] Generate `.frontend-ai/tokens.json`
- [ ] Generate `.frontend-ai/assets.json`
- [ ] Implement `frontend.index_project`
- [ ] Implement `frontend.search_components`
- [ ] Implement `frontend.get_prop_signature`
- [ ] Implement `frontend.validate_ui_code`
- [ ] Generate worker report
- [ ] Generate architect review

Start condition:

- Backend priority work has an approved task spec or explicit architect approval to switch tracks.

---

### Phase 5: Frontend Usage + Layout

Status: `not_started`

Tasks:

- [ ] Generate `.frontend-ai/usages.json`
- [ ] Generate `.frontend-ai/layouts.json`
- [ ] Implement `frontend.find_component_usages`
- [ ] Implement `frontend.get_layout_patterns`
- [ ] Validate existing layout/component patterns
- [ ] Generate worker report
- [ ] Generate architect review

Start condition:

- Phase 4 review verdict is `approve`.

---

### Phase 6: Runtime / Visual Validation

Status: `not_started`

Tasks:

- [ ] Add optional Storybook integration
- [ ] Add optional Playwright MCP integration
- [ ] Add accessibility snapshot support
- [ ] Add visual check support
- [ ] Generate worker report
- [ ] Generate architect review

Start condition:

- Phase 5 review verdict is `approve`.
