# Daily Progress Protocol

This protocol lets agents resume from files instead of chat memory.

Source-of-truth priority:

1. `AGENTS.md`
2. `docs/SRS.md`
3. `docs/ROADMAP.md`
4. `.agent_bus/status/current.md`
5. `.agent_bus/status/task-ledger.json`
6. Latest file in `.agent_bus/daily/`
7. Current task spec in `.agent_bus/tasks/`

If any file conflicts with `docs/SRS.md`, follow the SRS and write a concern under `.agent_bus/reports/`.

## Required Runtime Files

Agents must maintain:

```text
.agent_bus/status/current.md
.agent_bus/status/task-ledger.json
.agent_bus/daily/YYYY-MM-DD.md
.agent_bus/reports/<task>_worker_report.md
```

`.agent_bus/` is runtime-only and must not be committed.

## Start-of-Day Resume

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ai_status.ps1
```

Then read:

- `docs/SRS.md`
- `docs/ROADMAP.md`
- `AGENTS.md`
- `.agent_bus/status/current.md`
- `.agent_bus/status/task-ledger.json`
- latest `.agent_bus/daily/*.md`
- current task spec in `.agent_bus/tasks/`

Determine:

- current phase
- completed tasks
- next incomplete task
- blockers
- whether the next phase is allowed

## Gemini Resume Prompt

```text
Read:
- docs/SRS.md
- docs/ROADMAP.md
- AGENTS.md
- .agent_bus/status/current.md
- .agent_bus/status/task-ledger.json
- latest file in .agent_bus/daily/

Determine:
1. What phase we are in
2. What tasks are done
3. What task is next
4. Whether any blocker exists
5. Whether we are allowed to proceed

Return:
- current status
- next task spec
- files Codex is allowed to modify
- files Codex must not modify
- acceptance criteria
```

## Codex Resume Prompt

```text
Read:
- docs/SRS.md
- docs/ROADMAP.md
- AGENTS.md
- .agent_bus/status/current.md
- .agent_bus/status/task-ledger.json
- .agent_bus/tasks/latest task spec

Implement only the next approved task.

Do not skip ahead.
Do not modify docs/SRS.md.
Do not modify unrelated business source files.
After implementation, update progress files and write worker report.
```

## End-of-Task Update

After completing any task, update:

- `.agent_bus/status/current.md`
- `.agent_bus/status/task-ledger.json`
- `.agent_bus/daily/YYYY-MM-DD.md`
- `.agent_bus/reports/<task>_worker_report.md`

The worker report must include:

- files changed
- commands run
- tests run
- generated artifacts
- known limitations
- unresolved questions
- next recommended task

## Automated Gemini Review

After Codex writes a worker report, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ai_review_gemini.ps1
```

The script:

- finds the latest `.agent_bus/reports/*_worker_report.md` by default
- writes a review prompt under `.agent_bus/prompts/`
- runs Gemini CLI in review-only plan mode
- writes the result under `.agent_bus/reviews/`
- exits with a status code that blocks unsafe progress

Exit codes:

- `0`: Gemini returned `approve`
- `10`: Gemini returned `revise`
- `20`: Gemini returned `reject`
- `2`: Gemini CLI failed or was unavailable
- `3`: Gemini returned invalid review format

If Gemini does not return `approve`, do not proceed to the next phase.

To preview the handoff without calling Gemini:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/ai_review_gemini.ps1 -DryRun
```

## Completion Rule

A task is not complete unless evidence exists. Evidence can be:

- valid generated JSON
- test output
- worker report
- architect review
- committed source or configuration change

Never treat an empty placeholder file as implementation evidence.
