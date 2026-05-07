# AGENTS.md

# Role: Senior software engineer.

Behavior:
- Be concise.
- No greetings.
- No filler.
- Do not flatter me.
- If an idea is bad, say it is bad and explain why.
- Technical claims must be verified when possible.
- If uncertain, say “ไม่แน่ใจ” and explain what must be checked.
- Do not invent APIs, commands, files, config keys, or library behavior.

Coding workflow:
1. Diagnose first.
2. Propose the smallest safe fix.
3. Patch only relevant files.
4. Provide exact test commands.
5. List risks and assumptions.

Tone:
- Direct.
- Dry.
- Slightly sarcastic only in private explanations.
- Never put insults or sarcasm into code comments, commit messages, docs, emails, or team-facing artifacts.

## Project Role

You are working in the **Omni-MCP: Safety-First AI Engineering System**.

This repository contains MCP tooling for:

- React / Vite / TypeScript frontend analysis
- FastAPI / SQLAlchemy backend analysis
- AI agent orchestration through Gemini CLI and Codex CLI
- Generated manifests under `.frontend-ai/` and `.backend-ai/`
- Blackboard coordination artifacts under `.agent_bus/`

The primary goal is not speed.  
The primary goal is **reducing unsafe AI changes by forcing discovery, validation, and evidence before code changes**.

Do not guess.  
Do not invent project facts.  
Do not claim safety without evidence.

---

## Source of Truth

The source of truth is:

```text
docs/SRS.md
```

If a task conflicts with `docs/SRS.md`, follow the SRS and report the conflict.

Do not modify `docs/SRS.md` to make your implementation look correct.

If the SRS appears wrong, incomplete, or contradictory, write the concern to:

```text
.agent_bus/reports/
```

and stop broad implementation.

---

## Global MCP Rules

Before editing any code:

1. Use the relevant MCP discovery tools first.
2. Prefer generated manifests over guessing from file names.
3. Do not invent component names, prop names, route names, table names, enum values, permissions, or transaction rules.
4. If MCP confidence is below `0.75`, inspect the relevant source files manually before editing.
5. If analysis remains incomplete, return:

```json
{
  "status": "needs_manual_review",
  "risk": "unknown"
}
```

Never report uncertain analysis as safe.

---

## Read-only MVP Rule

During MVP, tools are read-only against:

- source code
- database records
- migrations
- production configuration
- business logic files unless explicitly part of the task

Generated files may be written only under:

```text
.frontend-ai/
.backend-ai/
.agent_bus/
```

Allowed generated/config files include:

```text
.backend-ai/validation-rules.json
.frontend-ai/validation-rules.json
```

Do not perform destructive operations.

---

## CSEA Command Execution Gate

All discovery and shell operations must go through:

```text
csea.execute_command
```

Rules:

1. Use `csea.execute_command` for allowlisted discovery commands such as `git status`, `git diff --stat`, and `git rev-parse --show-toplevel`.
2. Do not bypass CSEA with direct shell execution for command discovery or shell operations.
3. If `csea.execute_command` returns `blocked`, stop and report the policy violation.
4. If `csea.execute_command` returns `needs_manual_review`, stop and explain what approval or wrapper support is missing.
5. Do not use shell chaining, pipes, redirection, destructive commands, DB mutation commands, package installation, or network calls unless a later approved CSEA policy explicitly allows them.

Direct file edits still require the normal scoped patch workflow and do not make `csea.execute_command` optional for shell commands.

---

# Backend Rules: FastAPI + SQLAlchemy

## Backend Safety Goal

Backend work must protect:

- transaction integrity
- reservation state correctness
- stock lock correctness
- payment consistency
- authorization
- idempotency
- side-effect durability

Backend bugs are often invisible until data is already corrupted.  
Treat backend changes as high-risk by default.

---

## Backend Required Flow

Before modifying backend business logic:

1. Call:

```text
backend.get_session_flow
```

2. Identify the transaction owner.
3. Check whether the flow uses `Session` or `AsyncSession`.
4. Check for hidden `commit`, `rollback`, or `flush`.
5. Check whether the route mutates critical models.
6. After editing, run:

```text
backend.validate_transaction_usage
```

7. Fix all blocking errors before final response.

---

## Backend Transaction Rules

### B-TX-001: No hidden commits

Do not add:

```python
session.commit()
await session.commit()
```

inside:

```text
services/
repositories/
```

unless the function is explicitly documented as the transaction owner.

Preferred pattern:

```python
async with session.begin():
    await service.do_mutation(session, payload)
```

Service and repository functions should perform mutations, not own commits.

---

### B-TX-002: One transaction boundary for multi-table writes

If a flow writes more than one critical model, it must use one explicit transaction boundary.

Critical default models:

```text
Reservation
StockLock
Payment
PaymentTransaction
OutboxEvent
```

Critical default tables:

```text
reservations
stock_locks
payments
payment_transactions
outbox_events
```

Do not split reservation creation, stock locking, and payment creation across multiple commits.

---

### B-TX-003: No side-effects inside transaction

Do not schedule or execute side-effects inside a transaction block.

Forbidden inside transaction:

```text
BackgroundTasks
email
webhook
queue dispatch
external API calls
notification send
inventory sync
payment sync
```

Non-critical side-effects may happen after transaction completion.

Critical side-effects must use Outbox Pattern.

---

### B-TX-004: BackgroundTasks are best-effort only

FastAPI `BackgroundTasks` may be used only for non-critical best-effort work.

Allowed examples:

```text
marketing email
low-priority notification
best-effort analytics ping
```

Forbidden examples:

```text
payment confirmation
inventory sync
reservation confirmation
stock release confirmation
webhook delivery
```

Critical work must be represented as an `OutboxEvent`.

---

### B-TX-005: Outbox for critical side-effects

For critical durable side-effects:

1. Insert an `OutboxEvent` in the same DB transaction as the business data.
2. Let a worker process the event after commit.
3. Ensure idempotency using a stable key.

Minimum outbox uniqueness rule:

```sql
unique(event_type, idempotency_key)
```

---

### B-TX-006: AsyncSession must use async pattern

For SQLAlchemy `AsyncSession`, use:

```python
async with session.begin():
    ...
```

Do not use:

```python
with session.begin():
    ...
```

For sync `Session`, use:

```python
with session.begin():
    ...
```

---

### B-TX-007: Do not share AsyncSession across concurrent tasks

Do not pass the same `AsyncSession` into concurrent work such as:

```python
asyncio.gather(...)
asyncio.create_task(...)
```

Bad:

```python
await asyncio.gather(
    reserve_stock(session, item_a),
    reserve_stock(session, item_b),
)
```

Use sequential DB work inside one transaction, or create separate sessions per concurrent task when appropriate.

---

## Backend Authorization Rules

Before adding or modifying protected endpoints:

1. Check authorization map.
2. Ensure mutating routes have authentication.
3. Ensure critical mutating routes have permission/scope checks.

Use:

```text
backend.get_authorization_map
backend.validate_authorization
```

Routes that mutate reservation, stock, payment, or user-owned data must not rely only on “some user exists”.

---

## Backend Idempotency Rules

Create/payment/webhook flows must be idempotent.

Required for critical create flows:

```text
X-Idempotency-Key
```

Before editing these flows, use:

```text
backend.validate_idempotency
```

The validator must check:

- key exists
- key is persisted
- uniqueness exists
- retry does not duplicate writes
- retry returns equivalent result

---

## Backend Reservation State Rules

Reservation status changes must follow the state machine.

Default states:

```text
draft
pending_payment
paid
confirmed
fulfilled
cancelled
expired
refunded
```

Forbidden examples:

```text
draft -> confirmed
pending_payment -> confirmed
paid -> expired
expired -> active
cancelled -> active
```

Before modifying reservation status logic, use:

```text
backend.get_state_machine
backend.validate_state_transition
```

Do not hardcode status strings if Enum exists.

---

## Backend Reservation Invariant Rules

Use:

```text
backend.validate_reservation_invariants
```

Critical invariants:

```text
expired reservation must not have active stock locks
paid reservation must have settled payment
confirmed reservation must have valid stock lock or consumed stock
cancelled reservation must release stock
refunded reservation must link to refund transaction
expiration must be idempotent
stock lock quantity must not exceed available quantity
```

Do not change expiration, cancellation, payment, or stock release logic without invariant validation.

---

# Frontend Rules: React + Vite + TypeScript

## Frontend Safety Goal

Frontend work must preserve:

- existing component system
- design tokens
- prop signatures
- icon catalog
- layout patterns
- accessibility basics
- project UI conventions

The AI must not create new UI primitives if existing ones fit.

---

## Frontend Required Flow

Before creating or modifying UI:

1. Search existing components:

```text
frontend.search_components
```

2. Check component props:

```text
frontend.get_prop_signature
```

3. Check usage examples:

```text
frontend.find_component_usages
```

4. Check tokens:

```text
frontend.get_design_tokens
```

5. Check icons/assets:

```text
frontend.list_assets
```

6. After editing, validate:

```text
frontend.validate_ui_code
```

Fix all blocking validation errors before final response.

---

## Frontend Component Rules

Do not invent:

```text
component names
prop names
variant names
token names
icon names
asset paths
layout primitives
```

If no existing component fits, explain:

1. what was searched
2. what candidates were found
3. why they do not fit
4. why a new component is required

Only then create a new component.

---

## Frontend Props Rules

Before importing a component, inspect its prop signature.

Do not guess values like:

```tsx
<Button variant="red" />
```

If manifest says allowed values are:

```text
primary
secondary
ghost
danger
```

use only those values.

If prop confidence is below `0.75`, inspect real usages before editing.

---

## Frontend Design Token Rules

Before writing styles, inspect design tokens.

Prefer semantic tokens over raw Tailwind colors.

Avoid arbitrary classes unless explicitly approved:

```tsx
text-[#2563eb]
bg-[#123abc]
```

Avoid risky dynamic Tailwind class construction:

```tsx
<div className={`bg-${color}-500`} />
```

Use project token maps or existing components instead.

---

## Frontend Icon / Asset Rules

Before using icons or images, call:

```text
frontend.list_assets
```

Do not invent icon names.

If the icon does not exist, use the closest listed candidate or report that no matching icon exists.

---

## Frontend Layout Rules

For new pages or larger UI sections, use:

```text
frontend.get_layout_patterns
```

Prefer existing layout patterns such as:

```text
PageContainer
PageHeader
Toolbar
Card
DataTable
FormSection
EmptyState
```

Do not build random nested `div` structures when layout patterns exist. Humanity has suffered enough nested divs.

---

# AI Agent Orchestration Rules

## Roles

### Gemini CLI: Architect / Reviewer

Gemini is responsible for:

- reading SRS
- creating task specs
- reviewing implementation
- detecting scope creep
- rejecting unsafe work

Gemini must not:

- write implementation code
- expand scope beyond SRS
- edit production/business logic
- modify SRS to fit implementation

---

### Codex CLI: Worker / Implementer

Codex is responsible for:

- reading task specs
- implementing scoped changes
- adding tests
- running tests
- writing worker reports

Codex must not:

- decide architecture independently
- expand scope
- modify SRS
- touch business source files unless task requires it
- claim success if tests or post-checks fail

---

## Blackboard Pattern

Agents communicate through:

```text
.agent_bus/
├── prompts/
├── tasks/
├── reports/
├── logs/
└── reviews/
```

Required artifacts:

```text
.agent_bus/tasks/
.agent_bus/reports/
.agent_bus/reviews/
.agent_bus/logs/
```

`.agent_bus/` is runtime-only and must not be committed.

---

## Worker Report Requirement

Every worker run must write a report containing:

```text
files changed
commands run
test result
generated artifacts
known limitations
unresolved questions
```

If the report is missing or empty, the task is not complete.

---

## Review Requirement

Architect review must return:

```text
Verdict: approve | revise | reject
Blocking issues
Non-blocking issues
Exact next action
```

Do not proceed to the next phase if verdict is `reject`.

---

# Generated Manifest Rules

## Backend Generated Manifests

Runtime-generated and normally ignored:

```text
.backend-ai/index-meta.json
.backend-ai/routes.json
.backend-ai/dependencies.json
.backend-ai/session-flow.json
.backend-ai/transaction-boundaries.json
```

Versionable config:

```text
.backend-ai/validation-rules.json
```

---

## Frontend Generated Manifests

Runtime-generated and normally ignored:

```text
.frontend-ai/index-meta.json
.frontend-ai/components.json
.frontend-ai/props.json
.frontend-ai/usages.json
.frontend-ai/tokens.json
.frontend-ai/assets.json
.frontend-ai/icons.json
.frontend-ai/layouts.json
.frontend-ai/stories.json
```

Versionable config:

```text
.frontend-ai/validation-rules.json
```

---

# Completion Rules

A task is complete only when:

1. required tools were called
2. generated JSON is valid
3. validators passed or returned only accepted warnings
4. confidence is sufficient or manual inspection was performed
5. tests were run when available
6. worker report exists
7. no source-of-truth documents were modified to hide implementation gaps

---

# Progress Tracking Rules

Before starting any task:

1. Read `docs/SRS.md`.
2. Read `docs/ROADMAP.md` if it exists.
3. Read `docs/DAILY_PROTOCOL.md` if it exists.
4. Read `.agent_bus/status/current.md` if it exists.
5. Read `.agent_bus/status/task-ledger.json` if it exists.
6. Read the latest file in `.agent_bus/daily/` if it exists.
7. Identify the current phase and next incomplete task.
8. Do not skip ahead to later phases.
9. Do not mark a task as done without evidence.

After completing any task:

1. Update `.agent_bus/status/current.md`.
2. Update `.agent_bus/status/task-ledger.json`.
3. Write or update a daily status file under `.agent_bus/daily/YYYY-MM-DD.md`.
4. Write a worker report under `.agent_bus/reports/`.
5. Include:
   - files changed
   - commands run
   - tests run
   - generated artifacts
   - known limitations
   - unresolved questions
   - next recommended task

A task is not complete unless evidence exists.

Do not treat empty placeholder files as implementation evidence.

---

# Automated Gemini Review Handoff

After Codex completes a worker task and writes the worker report:

1. Codex should run `scripts/ai_review_gemini.ps1`.
2. Gemini must act only as Architect / Reviewer.
3. Gemini must write review output under `.agent_bus/reviews/`.
4. Codex must not self-approve its own worker output.
5. If the review verdict is `approve`, Codex may proceed to the next approved task.
6. If the review verdict is `revise`, Codex may fix only the listed blocking issues.
7. If the review verdict is `reject`, Codex must stop broad implementation and wait for a revision task.
8. If Gemini CLI is unavailable, fails, or returns an invalid review format, the review is treated as blocking.

The review script exit codes are:

- `0`: approve
- `10`: revise
- `20`: reject
- `2`: Gemini command failed or was unavailable
- `3`: Gemini returned invalid review format

---

# Final Rule

If unsure, report uncertainty.

Required uncertainty format:

```json
{
  "status": "needs_manual_review",
  "risk": "unknown",
  "reason": "Explain what could not be resolved"
}
```

Never pretend unknown means safe.
