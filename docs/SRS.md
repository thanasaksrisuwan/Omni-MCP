# Software Requirements Specification (SRS)
**Project:** FastAPI Backend MCP: Safety-First Reservation System  
**Version:** 1.0.1 (Final Lock)  
**Domain:** Retail Reservation (Booking, Stock Locking, Payments)  

## 1. Introduction

### 1.1 Purpose
ระบบนี้คือ **MCP Server + Indexer + Validator** สำหรับช่วย AI Coding Agent ทำงานกับ Backend FastAPI โดยมีเป้าหมายหลักคือ **การรักษา Data Integrity** ของระบบ Retail Reservation

เป้าหมายไม่ใช่ให้ AI "เขียนโค้ดได้เร็วขึ้น" แบบไร้สติ แต่เป็นการ **ลดโอกาส Hallucination ในจุด critical และบังคับให้ AI ตรวจสอบกับ MCP ก่อนแก้โค้ด** เพื่อให้ AI เข้าใจ Contract, Session Flow, Transaction Boundaries, Authorization, State Machine, Idempotency และ Business Invariants ก่อนลงมือแก้ไข

### 1.2 Tech Stack & Assumptions
* **Framework:** FastAPI (Async-first)
* **ORM:** SQLAlchemy 2.0 (เน้น `AsyncSession`)
* **Database:** PostgreSQL
* **Scanner Engine:** LibCST (Concrete Syntax Tree)
* **Worker Pattern:** Outbox-first pattern (Worker TBD: ARQ หรือ Celery)
* **Idempotency:** ผ่าน HTTP Header `X-Idempotency-Key`

### 1.3 Definitions
* **Transaction Owner:** Layer (มักจะเป็น Route หรือ Use-case) ที่มีหน้าที่ถือครอง `async with session.begin():`
* **Service Layer Commit:** Anti-pattern ที่ Service หรือ Repository แอบเรียก `session.commit()` เอง
* **Critical Side-effect:** งานที่ข้อมูลหายไม่ได้ เช่น Payment webhook, Inventory sync, Reservation confirmation (ต้องใช้ Outbox Pattern)
* **Non-critical Side-effect:** งานประเภท Best-effort เช่น ส่งอีเมลการตลาดทั่วไป อนุญาตให้ใช้ `BackgroundTasks` ได้ แต่ต้องทำหลัง Transaction จบเท่านั้น

---

## 2. Architecture Overview

สถาปัตยกรรมเป็นแบบ 3-Tier:

```text
[ FastAPI Codebase ]
        ↓
[ Indexer (LibCST & Metadata Scanners) ]
    ├── Route & Dependency Scanner
    ├── Session Flow Tracker
    └── Domain Invariant Scanner (Phase 2+)
        ↓
[ Atomic Manifest Store (.backend-ai/*.json) ]
        ↓
[ MCP Server ]
    ├── Discovery Tools
    ├── Session/Transaction Validators
    └── Security & Invariant Validators (Phase 2+)
        ↓
[ AI Agent ]
```

---

## 3. Atomic Manifest Files

ระบบต้องสร้าง Directory `.backend-ai/` และห้ามเก็บข้อมูลทั้งหมดรวมในไฟล์เดียว

* **MF-001:** Manifest ทุกไฟล์ต้องมี `generated_at`, `source_hash`, `project_root`, `schema_version`
* **MF-002:** ทุกข้อมูลที่ได้จากการ Infer หรือสแกนแบบไม่สมบูรณ์ ต้องมี `confidence`
* **MF-003:** Week 1 Manifests & Config ที่อนุญาตให้สร้างและเรียกใช้งาน:
  * `index-meta.json` (Manifest)
  * `routes.json` (Manifest)
  * `dependencies.json` (Manifest)
  * `session-flow.json` (Manifest - เริ่มทำ Day 2)
  * `transaction-boundaries.json` (Manifest - เริ่มทำ Day 2)
  * `validation-rules.json` (Configuration)

---

## 4. Functional Requirements

### 4.1 Project Indexing & Discovery
* **FR-IDX-001 [Index Project]:** Tool `backend.index_project` สแกนโปรเจกต์ด้วย LibCST เพื่อสร้าง Manifests
* **FR-API-001 [API Contract - Phase 2]:** Tool `backend.get_api_contract` ดึง Schema จาก Pydantic Model  
  *หมายเหตุ: ใน Week 1 จะบันทึกแค่ชื่อ Request/Response model หากมองเห็นได้ชัดเจนเท่านั้น การ Extract Full JSON Schema ถูกยกไป Phase 2*

### 4.2 Session Flow & Transaction Safety (Week 1 Core)
* **FR-SES-001 [Session Flow]:** Tool `backend.get_session_flow` ต้องตอบได้ว่า Route รับ Session จาก Dependency ไหน, Session เป็น Sync หรือ Async, และใครคือ Transaction Owner
* **FR-TX-001 [Transaction Validator]:** Tool `backend.validate_transaction_usage` ต้องตรวจสอบกฎเกณฑ์ต่อไปนี้ พร้อมคืนค่า **Structured Fix**

| Rule Code | Severity | Description & Logic |
| :--- | :--- | :--- |
| **TX001** | ERROR | **Service/Repository Commit:** พบ `session.commit()` ในชั้น `services/` หรือ `repositories/` |
| **TX002** | ERROR | **Multi-table Write Without TX:** เขียน Critical Tables มากกว่า 1 ตารางโดยไม่มี Transaction boundary ครอบ |
| **TX003** | ERROR | **Side-effect Inside TX:** พบ `background_tasks.add_task()` หรือการเรียก side-effect ภายใต้บล็อก Transaction |
| **TX004** | ERROR | **Commit Before Complete:** Commit เกิดขึ้นก่อนที่ Critical Mutation จะครบ *(Week 1 Best-effort: ถ้า confidence < 0.75 ให้ return needs_manual_review)* |
| **TX005** | ERROR | **Multiple Owners:** พบการเปิด/ปิด Transaction หลายระดับใน Flow เดียวกัน |
| **TX006** | ERROR | **Async/Sync Mismatch:** ตรวจจับโดยใช้ `cst.With.asynchronous is not None` เพื่อหาการใช้ `AsyncSession` ร่วมกับ `with` ธรรมดา หรือสลับกัน |
| **TX007** | ERROR | **Shared AsyncSession:** ตรวจพบการส่ง `AsyncSession` ตัวเดียวกันเข้าไปใน Concurrent tasks เช่น `asyncio.gather()` |

### 4.3 Domain Safety Requirements (Phase 2+)
* **FR-AUTH-001:** `backend.validate_authorization` ตรวจสอบ Route ที่ Mutate ข้อมูลสำคัญว่ามี Security Scope ครบถ้วน
* **FR-STATE-001:** `backend.validate_state_transition` ป้องกันการเปลี่ยนสถานะข้ามสเต็ป เช่น Draft -> Confirmed
* **FR-IDEMP-001:** `backend.validate_idempotency` ตรวจสอบ Endpoint สร้างข้อมูลว่ารองรับ `X-Idempotency-Key`
* **FR-OUTBOX-001:** `backend.validate_outbox_usage` ตรวจสอบว่า Critical side-effects ใช้ OutboxEvent เสมอ ห้ามใช้ BackgroundTasks
* **FR-INV-001:** `backend.validate_reservation_invariants` ตรวจสอบ Business Invariants เช่น Cancelled = Released Stock

---

## 5. Outbox Data Requirement (FR-OUTBOX-DATA-001)

ตาราง `outbox_events` ต้องมี Schema ดังนี้:

* `id` (PK)
* `event_type` (str)
* `aggregate_type` (str)
* `aggregate_id` (str/UUID)
* `idempotency_key` (str)
* `payload_json` (JSONB)
* `status` (Enum: pending, processing, processed, failed)
* **Unique Constraint:** ต้องมีการบังคับใช้อย่างน้อย `unique(event_type, idempotency_key)`

---

## 6. Non-Functional Requirements (NFRs)

* **NFR-001:** MCP Tools ต้องทำงานแบบ **Read-only ต่อ Source Code, Database, Migrations, และ Configuration Files ใน MVP** เครื่องมือสามารถเขียนหรืออัปเดต Generated Manifest Files ภายใต้ `.backend-ai/` ได้เท่านั้น
* **NFR-002:** Validation Output ต้องเป็น **Structured JSON** เพื่อให้ AI ทำ Self-correction ได้
* **NFR-003:** Tool Response ต้องพ่วงค่า `confidence` หากเป็นข้อมูล Inferred Data
* **NFR-004:** LibCST Scanner must not modify source files in MVP. If future codemod tools are added, they must preserve formatting, whitespace, and comments.

---

## 7. AGENTS.md Requirements

กฎการใช้งาน Agent ที่ต้องฝังไว้ใน Repository:

```markdown
## FastAPI Backend MCP Rules (Safety-First)

1. Before changing business logic, call `backend.get_session_flow`.
2. Identify the transaction owner before editing.
3. Do not add `session.commit()` inside services or repositories.
4. Multi-table reservation, stock, or payment writes must use one explicit transaction boundary.
5. Use `async with session.begin():` for SQLAlchemy `AsyncSession`.
6. Do not schedule `BackgroundTasks`, email, webhook, or queue calls inside transaction blocks.
7. Do not use `BackgroundTasks` for critical durable side-effects. Use OutboxEvent.
8. Do not share one `AsyncSession` across concurrent tasks.
9. After editing, run `backend.validate_transaction_usage`.
10. Fix all blocking TX errors before final response.
11. If MCP confidence is below 0.75, inspect the relevant files manually before editing.
```

---

## 8. Implementation Boundaries

### 8.1 Week 1 Scope
Week 1 ถูกจำกัดขอบเขตอยู่แค่ Route scanning, Dependency scanning, Session-flow extraction และ Transaction usage validation

**สิ่งที่อยู่นอกขอบเขต (Out of Scope) สำหรับ Week 1:**

* Full Pydantic JSON Schema extraction (FR-API-001 ฉบับเต็ม)
* Live database introspection
* Outbox worker implementation
* State machine validator
* Full domain invariant validator
* Automated code modification

### 8.2 Confidence Policy
หากผลการวิเคราะห์ (Analysis Confidence) มีค่าต่ำกว่า 0.75, Validator **ห้ามรายงานผลเป็น Safe โดยเด็ดขาด**

ระบบจะต้อง Return:

* `status: "needs_manual_review"`
* `risk: "unknown"`
* ระบุ Warning ชี้แจงส่วนที่ไม่สามารถ Resolve ได้อย่างชัดเจน

### 8.3 Critical Model Configuration
Transaction Validation Rules (FR-TX-001) ต้องอ้างอิงจาก Configured List เสมอ (ห้ามเดาเอง)

สร้างไฟล์ `.backend-ai/validation-rules.json` โดยมีค่า Default Critical Models ดังนี้:

* `Reservation` (Table: `reservations`)
* `StockLock` (Table: `stock_locks`)
* `Payment` (Table: `payments`)
* `PaymentTransaction` (Table: `payment_transactions`)
* `OutboxEvent` (Table: `outbox_events`)

### 8.4 Read-only MVP
MCP Tools ทั้งหมดใน Week 1 เป็น Read-only ต่อ Source Code และ Database

เครื่องมือสามารถอ่าน Source Files และสร้างหรืออัปเดต Manifest Files ภายใต้ `.backend-ai/` ได้

แต่ห้ามแก้ไข Source Files, Database Records, Migrations, หรือ Configuration Files โดยเด็ดขาด

---

## 9. Operational Readiness Requirements

### 9.1 Runtime Artifacts
`.agent_bus/` is runtime-only and MUST NOT be committed.

Generated manifests under `.backend-ai/` are runtime artifacts except `.backend-ai/validation-rules.json`, which MAY be versioned as project configuration.

### 9.2 Script Post-conditions
Day 1 orchestration scripts MUST verify that the following files exist after worker execution:

* `.backend-ai/index-meta.json`
* `.backend-ai/routes.json`
* `.backend-ai/dependencies.json`
* `.backend-ai/validation-rules.json`
* `.agent_bus/reports/day1_worker_report.md`

Generated JSON files MUST be valid JSON.

### 9.3 Tool Smoke Tests
Before running implementation, orchestration scripts SHOULD verify that Gemini CLI, Codex CLI, Python, and pytest are available.

### 9.4 SRS Integrity
Worker agents MUST NOT modify `docs/SRS.md` to match their implementation. If the worker finds a contradiction, it must report it in `.agent_bus/reports/`.

---

## 10. Acceptance Criteria for Day 1

### AC-001 Route Detection
The scanner must detect FastAPI route decorators:

* `@router.get`
* `@router.post`
* `@router.put`
* `@router.patch`
* `@router.delete`

### AC-002 Route Metadata
For each detected route, scanner must extract:

* HTTP method
* path
* handler name
* whether handler is async
* source file
* line number
* confidence

### AC-003 Dependency Detection
Scanner must extract direct parameter-level dependencies:

* `Depends(...)`
* `Security(...)`

### AC-004 Session Detection
Scanner must detect SQLAlchemy session parameter annotation:

* `AsyncSession`
* `Session`

### AC-005 Security Scope Detection
Scanner must extract scopes from direct `Security(..., scopes=[...])` usage where statically visible.

### AC-006 Read-only Guarantee
The scanner must not modify source files.

### AC-007 Output Files
At the end of Day 1, the following files must exist:

```text
.backend-ai/
├── index-meta.json
├── routes.json
├── dependencies.json
└── validation-rules.json
```

---

## 11. Day 1 Definition of Done

Day 1 is complete only when:

* Route fixture test passes
* `routes.json` is valid JSON
* `dependencies.json` is valid JSON
* `index-meta.json` is valid JSON
* `validation-rules.json` is valid JSON
* Each route record includes `source_file`, `line`, and `confidence`
* No source code outside scanner implementation/tests is modified
* `.agent_bus/reports/day1_worker_report.md` exists after orchestration run