# Software Requirements Specification (SRS)
**Project:** Omni-MCP: Frontend + Backend Safety-First AI Engineering System  
**Version:** 1.0.0  
**Domain:** React/Vite/TypeScript Frontend + FastAPI Backend + Retail Reservation Safety  
**Primary Goal:** Make AI coding agents work inside project rules, not hallucinate architecture like a caffeinated intern.

---

## 1. Introduction

### 1.1 Purpose

ระบบนี้คือ **Omni-MCP System** สำหรับช่วย AI Coding Agent ทำงานกับทั้งฝั่ง Frontend และ Backend โดยมีเป้าหมายหลักคือ:

1. ลดการเดาสุ่มของ AI
2. บังคับให้ AI ตรวจสอบข้อมูลจริงก่อนแก้โค้ด
3. ป้องกันการสร้าง component, prop, token, route, schema, transaction, หรือ side-effect แบบมั่ว
4. รักษา Data Integrity ในระบบ Retail Reservation
5. ทำให้ AI ทำงานผ่าน Manifest, Validator, และ Guardrail แทนการอ่านไฟล์สดแบบไร้ทิศทาง

ระบบนี้ไม่ได้สร้างมาเพื่อให้ AI “เขียนโค้ดเร็วขึ้นอย่างไร้สติ”  
แต่สร้างมาเพื่อให้ AI **ผิดพลาดยากขึ้น และตรวจจับความพลาดได้เร็วขึ้น**

---

## 2. Scope

### 2.1 Included

ระบบนี้ครอบคลุม:

- React + Vite + TypeScript frontend
- Component discovery
- Design token validation
- Icon / asset catalog
- Component prop signature extraction
- Component usage graph
- UI validation loop
- FastAPI backend
- SQLAlchemy AsyncSession
- PostgreSQL
- Transaction boundary validation
- Session flow graph
- Authorization map
- Reservation state machine
- Idempotency validation
- Outbox pattern validation
- AI Agent orchestration between Gemini CLI and Codex CLI

### 2.2 Excluded from MVP

ใน MVP ไม่รวม:

- Automated production deployment
- Destructive database operations
- Automated schema migrations
- Full visual regression system
- Full runtime browser inspection
- Full distributed tracing
- Automatic refactor across entire codebase
- AI editing business code without validator pass

เพราะเราทำวิศวกรรม ไม่ใช่เรียกปีศาจผ่าน YAML

---

## 3. System Architecture

```text
[ Project Codebase ]
        ↓
[ Indexers ]
    ├── Frontend Indexer
    │   ├── ts-morph
    │   ├── Storybook Scanner
    │   ├── Tailwind / Token Scanner
    │   └── Usage Graph Builder
    │
    └── Backend Indexer
        ├── LibCST Scanner
        ├── FastAPI Route Scanner
        ├── SQLAlchemy Metadata Scanner
        └── Session Flow Tracker
        ↓
[ Atomic Manifest Stores ]
    ├── .frontend-ai/*.json
    └── .backend-ai/*.json
        ↓
[ MCP Server ]
    ├── Frontend Tools
    ├── Backend Tools
    ├── Validation Tools
    └── Orchestration Tools
        ↓
[ AI Agents ]
    ├── Gemini CLI: Architect / Reviewer
    └── Codex CLI: Worker / Implementer
```

---

## 4. Shared Design Principles

### 4.1 Manifest First

AI must not inspect the full codebase blindly.

AI must query generated manifests first:

```text
.frontend-ai/
.backend-ai/
```

### 4.2 Validation Before Final Answer

AI must run relevant validators before claiming work is complete.

### 4.3 Confidence Policy

Any inferred data must include:

```json
{
  "confidence": 0.0,
  "provenance": "static-analysis | manual-jsdoc | manifest | runtime-introspection"
}
```

If confidence is below `0.75`, the tool must return:

```json
{
  "status": "needs_manual_review",
  "risk": "unknown"
}
```

AI must not report `safe` when analysis is incomplete.  
อย่าทำตัวเป็นหมอดูใส่ JSON

### 4.4 Read-only MVP

MVP tools are read-only against:

- Source code
- Database records
- Migrations
- Configuration files

MVP tools may write generated manifest files under:

```text
.frontend-ai/
.backend-ai/
.agent_bus/
```

---

# Part A: Frontend MCP SRS

---

## 5. Frontend MCP Purpose

Frontend MCP ทำให้ AI เข้าใจระบบ UI จริงของโปรเจกต์ ไม่ใช่เดา component, prop, token, icon, หรือ layout เอง

เป้าหมาย:

- ใช้ existing components ก่อนสร้างใหม่
- ใช้ design tokens ถูกต้อง
- ใช้ prop / variant / icon ที่มีจริง
- copy usage pattern จาก codebase เดิม
- validate JSX หลังแก้โค้ด
- ลดการสร้าง `CustomButton`, `FancyCard`, `BetterTable` แบบเชื้อรา repo

---

## 6. Frontend Tech Stack

- React
- Vite
- TypeScript
- Tailwind CSS หรือ Design Token System
- Optional: Storybook
- Optional Phase 3: Playwright MCP

---

## 7. Frontend Atomic Manifests

ระบบต้องสร้าง directory:

```text
.frontend-ai/
├── index-meta.json
├── components.json
├── props.json
├── usages.json
├── tokens.json
├── assets.json
├── icons.json
├── layouts.json
├── stories.json
└── validation-rules.json
```

### 7.1 Manifest Requirements

ทุก manifest ต้องมี:

```json
{
  "schema_version": "1.0.0",
  "generated_at": "ISO-8601",
  "project_root": "...",
  "source_hash": "...",
  "confidence": 0.0
}
```

---

## 8. Frontend Indexer Requirements

### FR-FE-IDX-001: Index Project

Tool:

```text
frontend.index_project
```

ต้อง scan:

- `src/**/*.tsx`
- `src/**/*.ts`
- component exports
- prop types
- JSDoc metadata
- Storybook stories
- Tailwind config
- theme token files
- icon exports
- actual component usages

Output:

```json
{
  "status": "ok",
  "components": 128,
  "tokens": 214,
  "icons": 76,
  "warnings": [
    "12 components missing @ai.intent"
  ]
}
```

---

## 9. Frontend Metadata Convention

Component สำคัญควรมี metadata:

```tsx
/**
 * @ai.component ui.button
 * @ai.intent primary action, secondary action, form submit
 * @ai.avoid navigation link, row action menu
 * @ai.status stable
 * @ai.a11y icon-only usage requires aria-label
 */
export function Button(props: ButtonProps) {
  // ...
}
```

### 9.1 Metadata Fields

| Field | Required | Meaning |
|---|---:|---|
| `@ai.component` | yes | stable component id |
| `@ai.intent` | yes | when to use |
| `@ai.avoid` | recommended | when not to use |
| `@ai.status` | recommended | stable / beta / deprecated |
| `@ai.a11y` | optional | accessibility rules |
| `@ai.replaces` | optional | legacy replacement |

---

## 10. Frontend MCP Tools

### 10.1 `frontend.search_components`

Purpose:

ค้นหา component จาก intent ไม่ใช่ชื่อไฟล์

Input:

```json
{
  "intent": "delete action button in table row",
  "context_path": "src/features/inventory",
  "limit": 5
}
```

Output:

```json
{
  "results": [
    {
      "component_id": "ui.button",
      "name": "Button",
      "import_path": "@/components/ui/Button",
      "score": 0.91,
      "why": "Supports danger variant and is commonly used for destructive actions",
      "recommended_props": {
        "variant": "danger"
      },
      "confidence": 0.9
    }
  ]
}
```

---

### 10.2 `frontend.get_prop_signature`

Purpose:

ให้ AI เห็น props จริงก่อน import component

Input:

```json
{
  "component_id": "ui.button"
}
```

Output:

```json
{
  "component_id": "ui.button",
  "props_type": "ButtonProps",
  "props": {
    "variant": {
      "type": "\"primary\" | \"secondary\" | \"ghost\" | \"danger\"",
      "required": false,
      "allowed_values": ["primary", "secondary", "ghost", "danger"],
      "default": "primary"
    },
    "loading": {
      "type": "boolean",
      "required": false
    }
  },
  "confidence": 0.95
}
```

---

### 10.3 `frontend.find_component_usages`

Purpose:

หา usage จริงใน codebase เพื่อให้ AI copy pattern เดิม

Input:

```json
{
  "component_id": "ui.button",
  "context": "destructive action",
  "limit": 5
}
```

Output:

```json
{
  "usages": [
    {
      "file": "src/features/assets/DeleteAssetButton.tsx",
      "line": 42,
      "summary": "Danger button inside confirm dialog footer",
      "props_used": {
        "variant": "danger",
        "loading": "isDeleting"
      },
      "confidence": 0.88
    }
  ]
}
```

---

### 10.4 `frontend.get_design_tokens`

Purpose:

ให้ AI ใช้ token จริง ไม่ใช่ `bg-blue-500` ตามใจจักรวาล

Input:

```json
{
  "groups": ["color", "spacing", "radius", "typography"]
}
```

Output:

```json
{
  "colors": {
    "primary": {
      "class": "text-primary",
      "background_class": "bg-primary",
      "usage": "Main brand actions"
    },
    "destructive": {
      "class": "text-destructive",
      "background_class": "bg-destructive",
      "usage": "Danger actions"
    }
  }
}
```

---

### 10.5 `frontend.list_assets`

Purpose:

กัน AI hallucinate icon หรือ asset path

Input:

```json
{
  "query": "chevron right next arrow",
  "kind": "icon",
  "limit": 10
}
```

Output:

```json
{
  "assets": [
    {
      "name": "IconArrowRight",
      "kind": "icon",
      "import_path": "@/components/icons",
      "aliases": ["next", "chevron right", "forward"]
    }
  ]
}
```

---

### 10.6 `frontend.get_layout_patterns`

Purpose:

ให้ AI ใช้ layout pattern เดิมของ project

Input:

```json
{
  "intent": "management list page"
}
```

Output:

```json
{
  "patterns": [
    {
      "pattern_id": "page.list-management",
      "tree": [
        "PageContainer",
        "PageHeader",
        "Toolbar",
        "Card",
        "DataTable"
      ],
      "examples": [
        "src/features/assets/AssetListPage.tsx"
      ]
    }
  ]
}
```

---

### 10.7 `frontend.validate_ui_code`

Purpose:

ตรวจ code ที่ AI แก้ก่อนส่งงาน

Checks:

- import path
- component existence
- prop required
- prop allowed values
- design token usage
- icon existence
- deprecated component
- accessibility basic rules

Output:

```json
{
  "status": "failed",
  "issues": [
    {
      "severity": "error",
      "code": "INVALID_PROP_VALUE",
      "file": "src/features/inventory/InventoryPage.tsx",
      "line": 57,
      "component_id": "ui.button",
      "message": "Button variant \"red\" does not exist.",
      "suggested_fix": "Use variant=\"danger\""
    }
  ]
}
```

---

## 11. Frontend Validation Rules

### FE001 Unknown Component

AI imported a component that does not exist.

### FE002 Invalid Import Path

Import path does not match manifest.

### FE003 Invalid Prop Value

Prop literal value does not match allowed union.

### FE004 Missing Required Prop

Required prop missing.

### FE005 Unknown Icon

Icon is not exported from icon catalog.

### FE006 Unknown Token

Tailwind class or token is not in token registry.

### FE007 Deprecated Component

Component status is deprecated.

### FE008 Dynamic Tailwind Class Risk

Detected dynamic class construction:

```tsx
<div className={`bg-${color}-500`} />
```

Validator should warn or fail depending on config.

---

## 12. Frontend Week 1 Scope

Frontend Week 1 MVP:

```text
frontend.index_project
frontend.search_components
frontend.get_prop_signature
frontend.validate_ui_code
```

Out of scope:

- visual screenshot validation
- Playwright MCP
- Storybook runtime render
- full AST code modification
- design token migration
- automatic component refactor

---

# Part B: Backend MCP SRS

---

## 13. Backend MCP Purpose

Backend MCP ป้องกัน AI ทำ data state พัง

เป้าหมาย:

- ตรวจ session flow
- ตรวจ transaction boundary
- ตรวจ hidden commit
- ตรวจ authorization
- ตรวจ idempotency
- ตรวจ state transition
- ตรวจ reservation invariants
- ตรวจ side-effect timing
- บังคับใช้ outbox pattern สำหรับงาน critical

---

## 14. Backend Tech Stack

- FastAPI
- SQLAlchemy 2.0
- AsyncSession-first
- PostgreSQL
- LibCST
- Pydantic v2
- Outbox-first side-effect processing
- Worker TBD: ARQ หรือ Celery

---

## 15. Backend Atomic Manifests

```text
.backend-ai/
├── index-meta.json
├── routes.json
├── dependencies.json
├── session-flow.json
├── transaction-boundaries.json
├── validation-rules.json
├── api-contracts.json
├── pydantic-models.json
├── sqlalchemy-models.json
├── authorization-map.json
├── capabilities.json
├── state-machines.json
├── side-effects.json
├── outbox-events.json
└── invariants.json
```

Week 1 allowed:

```text
.backend-ai/
├── index-meta.json
├── routes.json
├── dependencies.json
├── validation-rules.json
```

Day 2 starts:

```text
.backend-ai/
├── session-flow.json
└── transaction-boundaries.json
```

---

## 16. Backend Session Flow Requirements

### FR-BE-SES-001: `backend.get_session_flow`

Tool must answer:

- route receives session from which dependency
- session type: `Session` or `AsyncSession`
- route handler async or sync
- transaction owner
- session operations:
  - `add`
  - `delete`
  - `execute`
  - `flush`
  - `commit`
  - `rollback`
  - `begin`
- whether operation is inside transaction block
- whether side-effect is inside transaction block

Output:

```json
{
  "entrypoint": "POST /reservations",
  "handler": "app.api.reservations.create_reservation",
  "session_dependency": "get_session",
  "session_type": "AsyncSession",
  "transaction_owner": "app.api.reservations.create_reservation",
  "transaction_pattern": "async with session.begin()",
  "commits_found": [],
  "flushes_found": [
    {
      "file": "app/services/reservation.py",
      "line": 22,
      "context": "await session.flush()",
      "risk": "allowed_if_inside_transaction"
    }
  ],
  "risk": "low",
  "confidence": 0.82
}
```

---

## 17. Backend Transaction Rules

Tool:

```text
backend.validate_transaction_usage
```

### TX001 Service / Repository Commit

Error if `session.commit()` found inside:

```text
services/
repositories/
```

Suggested fix:

```text
Remove commit from service/repository. Let route/use-case own transaction boundary.
```

### TX002 Multi-table Write Without Transaction

Error if writes touch more than one critical model without transaction boundary.

Critical models come from:

```text
.backend-ai/validation-rules.json
```

### TX003 Side-effect Inside Transaction

Error if any of these occurs inside transaction:

- `background_tasks.add_task`
- email call
- webhook call
- queue dispatch
- external API call

### TX004 Commit Before Complete

Best-effort in Week 1.

If confidence < 0.75, return:

```json
{
  "status": "needs_manual_review"
}
```

### TX005 Multiple Transaction Owners

Error if route and service/repository both begin/commit transaction.

### TX006 Async / Sync Mismatch

Must inspect:

```python
cst.With.asynchronous is not None
```

Rules:

- `AsyncSession` requires `async with session.begin():`
- sync `Session` requires `with session.begin():`

### TX007 Shared AsyncSession in Concurrent Tasks

Error if one `AsyncSession` is passed into:

```python
asyncio.gather(...)
asyncio.create_task(...)
```

---

## 18. Backend Authorization Requirements

### FR-BE-AUTH-001: `backend.get_authorization_map`

Must extract:

- `Depends(...)`
- `Security(...)`
- scopes
- current user dependencies
- route-level dependencies
- router-level dependencies where visible

Output:

```json
{
  "route": "POST /reservations",
  "dependencies": ["get_current_user"],
  "security": [
    {
      "type": "scope",
      "value": "reservation:create"
    }
  ],
  "authorization_status": "protected"
}
```

### FR-BE-AUTH-002: `backend.validate_authorization`

Critical mutating routes must not be unprotected.

---

## 19. Backend Idempotency Requirements

### FR-BE-IDEMP-001: `backend.validate_idempotency`

Must verify:

- Create reservation endpoint accepts `X-Idempotency-Key`
- Payment webhook / confirmation flow is idempotent
- Key is persisted in durable store
- Unique constraint exists
- Retry returns same result, not duplicate write

---

## 20. Backend State Machine Requirements

### Reservation States

Default state model:

```text
draft
→ pending_payment
→ paid
→ confirmed
→ fulfilled
```

Special terminal or side states:

```text
cancelled
expired
refunded
```

### FR-BE-STATE-001: `backend.validate_state_transition`

Must prevent:

- `draft -> confirmed`
- `pending_payment -> confirmed`
- `paid -> expired`
- terminal state returning active
- hardcoded status strings if Enum exists

---

## 21. Backend Reservation Invariants

Tool:

```text
backend.validate_reservation_invariants
```

Rules:

| Code | Rule |
|---|---|
| INV001 | expired reservation must not have active stock locks |
| INV002 | paid reservation must have settled payment |
| INV003 | confirmed reservation must have valid stock lock or consumed stock |
| INV004 | cancelled reservation must release stock |
| INV005 | refunded reservation must link to refund transaction |
| INV006 | expiration must be idempotent |
| INV007 | stock lock quantity must not exceed available quantity |

---

## 22. Backend Outbox Requirements

Critical side-effects must use Outbox Pattern.

### `outbox_events` Schema

```text
id
event_type
aggregate_type
aggregate_id
idempotency_key
payload_json
status
attempt_count
next_retry_at
processed_at
created_at
updated_at
last_error
```

Minimum unique constraint:

```sql
unique(event_type, idempotency_key)
```

### Critical Side-effects

Must use outbox:

- payment confirmation
- inventory sync
- reservation confirmation
- stock release confirmation
- webhook delivery

### Non-critical Side-effects

May use `BackgroundTasks` after transaction completion:

- marketing email
- low priority notification
- best-effort analytics ping

---

# Part C: Shared AGENTS Rules

---

## 23. `AGENTS.md`

```markdown
## Omni-MCP Rules

1. Use MCP tools before editing.
2. Do not guess component names, prop names, table names, route names, permissions, or transaction rules.
3. If confidence is below 0.75, inspect files manually before editing.
4. Never report unsafe or incomplete analysis as safe.

## Frontend Rules

1. Before creating or modifying UI, call `frontend.search_components`.
2. Before importing a component, call `frontend.get_prop_signature`.
3. Before using icons/assets, call `frontend.list_assets`.
4. Before writing styles, call `frontend.get_design_tokens`.
5. Prefer existing components over new UI primitives.
6. After editing UI, run `frontend.validate_ui_code`.
7. Fix all blocking frontend validation errors before final response.

## Backend Rules

1. Before changing business logic, call `backend.get_session_flow`.
2. Identify the transaction owner before editing.
3. Do not add `session.commit()` inside services or repositories.
4. Multi-table reservation, stock, or payment writes must use one explicit transaction boundary.
5. Use `async with session.begin():` for SQLAlchemy `AsyncSession`.
6. Do not schedule `BackgroundTasks`, email, webhook, or queue calls inside transaction blocks.
7. Do not use `BackgroundTasks` for critical durable side-effects. Use OutboxEvent.
8. Do not share one `AsyncSession` across concurrent tasks.
9. After editing backend code, run `backend.validate_transaction_usage`.
10. Fix all blocking backend validation errors before final response.
```

---

# Part D: AI Agent Orchestration SRS

---

## 24. Orchestration Purpose

AI agent orchestration uses blackboard pattern to coordinate Gemini CLI and Codex CLI.

```text
Gemini = Architect / Reviewer
Codex = Worker / Implementer
.agent_bus = shared blackboard
docs/SRS.md = law
AGENTS.md = runtime discipline
```

---

## 25. Blackboard Directory

```text
.agent_bus/
├── prompts/
├── tasks/
├── reports/
├── logs/
└── reviews/
```

`.agent_bus/` must not be committed.

---

## 26. Role Definition

### Gemini CLI

Responsibilities:

- read SRS
- create task spec
- review implementation
- detect scope creep
- reject unsafe implementation

Forbidden:

- writing implementation code
- expanding scope
- editing SRS to match implementation

### Codex CLI

Responsibilities:

- implement task spec
- add tests
- run tests
- generate reports

Forbidden:

- deciding architecture
- expanding scope
- modifying SRS
- touching business code unless task requires it

---

## 27. Day 1 Backend Orchestration Output

Expected:

```text
.backend-ai/
├── index-meta.json
├── routes.json
├── dependencies.json
└── validation-rules.json

.agent_bus/
├── tasks/day1_task.md
├── reports/day1_worker_report.md
├── reviews/day1_review.md
└── logs/
```

---

## 28. Operational Readiness Requirements

### OR-001

Scripts must verify required files exist.

### OR-002

Scripts must validate generated JSON.

### OR-003

Scripts must support dry-run mode.

### OR-004

Scripts must warn when git working tree is dirty.

### OR-005

Scripts must not claim success if post-conditions fail.

---

# Part E: Roadmap

---

## 29. Phase 1: Backend Day 1

Goal:

```text
Route & Dependency Scanner
```

Deliverables:

```text
routes.json
dependencies.json
index-meta.json
validation-rules.json
```

---

## 30. Phase 2: Backend Session Safety

Goal:

```text
Session Flow + Transaction Boundary
```

Deliverables:

```text
session-flow.json
transaction-boundaries.json
backend.get_session_flow
backend.validate_transaction_usage
```

---

## 31. Phase 3: Backend Reservation Safety

Goal:

```text
State + Idempotency + Outbox + Invariants
```

Deliverables:

```text
backend.validate_state_transition
backend.validate_idempotency
backend.validate_outbox_usage
backend.validate_reservation_invariants
```

---

## 32. Phase 4: Frontend Week 1

Goal:

```text
Component Semantic Graph
```

Deliverables:

```text
components.json
props.json
tokens.json
assets.json
frontend.search_components
frontend.get_prop_signature
frontend.validate_ui_code
```

---

## 33. Phase 5: Frontend Usage + Layout

Goal:

```text
Usage graph + layout patterns
```

Deliverables:

```text
usages.json
layouts.json
frontend.find_component_usages
frontend.get_layout_patterns
```

---

## 34. Phase 6: Runtime / Visual

Goal:

```text
Optional visual/runtime validation
```

Deliverables:

```text
Storybook integration
Playwright MCP
a11y snapshot
visual check
```

---

# Part F: Final Acceptance Criteria

---

## 35. Global Acceptance Criteria

The Omni-MCP system is acceptable when:

- AI can query existing frontend components before creating UI
- AI can validate prop/token/icon usage
- AI can trace backend route/session flow
- AI can detect service-layer commit
- AI can detect unsafe transaction pattern
- AI can detect missing idempotency on critical flows
- AI can detect critical side-effect without outbox
- all validator outputs are structured JSON
- confidence below 0.75 blocks safe claims
- orchestration logs are stored in `.agent_bus/`
- generated manifests are valid JSON
- no MVP tool modifies business source code or production DB

---

## 36. Final Rule

If the MCP system is unsure, it must say:

```json
{
  "status": "needs_manual_review",
  "risk": "unknown"
}
```

It must never pretend uncertainty is safety.

เพราะการบอกว่า “น่าจะปลอดภัย” โดยไม่มีหลักฐาน คือวิธีที่ระบบ production ใช้เขียนจดหมายลาตายล่วงหน้า