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

CORE-005 Rebranding / Protocol Finalized

## Phase List

### Phase 1: Backend Day 1 - Route & Dependency Scanner
Status: `done`

### Phase 2: Backend Day 2 - Session Flow + Transaction Boundary
Status: `done`

### Phase 3: Backend Reservation Safety
Status: `done`

### Phase 4: Frontend MCP Week 1
Status: `done`

### Phase 5: Frontend Usage + Layout
Status: `done`

### Phase 6: Runtime / Visual Validation
Status: `done`

### Phase 7: MCP Server Wrapper
Status: `done`

---

### Phase 8: CORE-001 Omni-Bridge Context Pack
Status: `done`
- [x] Implement read-only `scripts/omni_bridge.py`
- [x] Expose `omni.bridge_pack_context`
- [x] Add fixture manifest tests
- [x] Generate worker report & architect review

---

### Phase 9: CORE-002 Omni-Scribe Write Planning Tool
Status: `done`
- [x] Create validation-locked `scripts/omni_scribe.py`
- [x] Expose `omni.scribe_plan_write`
- [x] Add write-plan fixture tests
- [x] Generate worker report & architect review

---

### Phase 10: CORE-003 Omni-Vision Semantic Trace
Status: `done`
- [x] Implement manifest-linked `scripts/omni_vision.py`
- [x] Expose `omni.vision_trace_route`
- [x] Add trace fixture tests
- [x] Generate worker report & architect review

---

### Phase 11: CORE-004 Omni-Vault Transactional Sandbox
Status: `done`
- [x] Implement transactional sandbox `scripts/omni_vault.py`
- [x] Expose `omni.vault_sandbox_run`
- [x] Add sandbox fixture tests (Mock SQLAlchemy)
- [x] Generate worker report & architect review

---

### Phase 12: CORE-005 Rebranding (Protocol Finalization)
Status: `done`
- [x] Update `AGENTS.md` with Omni-Series instructions
- [x] Finalize `scripts/mcp_server.py` branding
- [x] Synchronize progress tracking files
- [x] Final worker report

---

## Evolution Complete: Omni-MCP v2.0
The transition from a Static Auditor to a Secure Execution Engine (The Core Protocol) is complete. The system now supports discovery, secure writing, semantic tracing, and transactional sandboxing.
