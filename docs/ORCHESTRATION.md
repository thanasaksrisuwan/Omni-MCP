# AI Agent Orchestration Protocol

## Purpose

This document defines how Gemini CLI and Codex CLI coordinate work on this project using a Blackboard Pattern.

The goal is to separate architectural planning and implementation work:

- Gemini CLI acts as Architect / Reviewer
- Codex CLI acts as Worker / Implementer
- `.agent_bus/` acts as the shared blackboard and audit trail
- `docs/SRS.md` acts as the source of truth

## Blackboard Structure

```text
.agent_bus/
├── prompts/
├── tasks/
├── reports/
├── logs/
└── reviews/
```

## Role Definition

### Gemini CLI: Architect / Reviewer

Gemini is responsible for:

- reading `docs/SRS.md`
- creating strict task specifications
- reviewing implementation output
- identifying scope violations
- identifying requirement mismatches

Gemini must not:

- write implementation code
- broaden scope beyond the SRS
- request business logic modifications outside the task
- edit `docs/SRS.md` to fit implementation

### Codex CLI: Worker / Implementer

Codex is responsible for:

- reading task specs from `.agent_bus/tasks/`
- implementing only the requested scope
- adding tests and fixtures
- running tests
- writing implementation reports

Codex must not:

- decide architecture independently
- broaden scope
- touch business source files unless explicitly required
- edit `docs/SRS.md`
- claim success if tests or post-checks fail

## Required Artifacts

Each orchestration run must produce:

```text
.agent_bus/tasks/day1_task.md
.agent_bus/reports/day1_worker_report.md
.agent_bus/reviews/day1_review.md
.agent_bus/logs/
```

## Day 1 Orchestration Flow

```text
Gemini creates task spec
        ↓
Codex implements scanner
        ↓
Codex writes worker report
        ↓
Script verifies output files and JSON validity
        ↓
Gemini reviews against SRS
```

## Confidence Rule

If confidence is below `0.75`, the agent must not report the result as safe.

It must report:

```json
{
  "status": "needs_manual_review",
  "risk": "unknown"
}
```

## Runtime Artifact Rule

`.agent_bus/` is runtime-only and must not be committed.

Generated manifests under `.backend-ai/` are runtime artifacts except `.backend-ai/validation-rules.json`, which may be versioned as project configuration.