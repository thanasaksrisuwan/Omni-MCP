$ErrorActionPreference = "Stop"

$Root = git rev-parse --show-toplevel 2>$null
if (-not $Root) { $Root = Get-Location }
Set-Location $Root

$Bus = ".agent_bus"
$DryRun = $env:DRY_RUN

New-Item -ItemType Directory -Force "$Bus/prompts", "$Bus/tasks", "$Bus/reports", "$Bus/logs", "$Bus/reviews" | Out-Null
New-Item -ItemType Directory -Force ".backend-ai" | Out-Null

if (-not (Get-Command gemini -ErrorAction SilentlyContinue)) {
    throw "gemini CLI not found"
}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "codex CLI not found"
}

if (-not (Test-Path "docs/SRS.md")) {
    throw "docs/SRS.md not found"
}

"==> Tool versions"
gemini --version 2>$null
codex --version 2>$null
python --version

"==> Checking git status"
git status --short | Tee-Object "$Bus/logs/git-status-before.txt"

if ((git status --porcelain).Length -gt 0) {
    Write-Warning "Working tree is not clean."
    $answer = Read-Host "Continue? [y/N]"
    if ($answer -ne "y") {
        throw "Aborted."
    }
}

if (-not (Test-Path ".backend-ai/validation-rules.json")) {
@'
{
  "schema_version": "1.0.1",
  "confidence_threshold": 0.75,
  "critical_models": [
    { "model": "Reservation", "table": "reservations" },
    { "model": "StockLock", "table": "stock_locks" },
    { "model": "Payment", "table": "payments" },
    { "model": "PaymentTransaction", "table": "payment_transactions" },
    { "model": "OutboxEvent", "table": "outbox_events" }
  ],
  "transaction_rules": [
    { "code": "TX001", "name": "Service/Repository Commit", "severity": "error" },
    { "code": "TX002", "name": "Multi-table Write Without TX", "severity": "error" },
    { "code": "TX003", "name": "Side-effect Inside TX", "severity": "error" },
    { "code": "TX004", "name": "Commit Before Complete", "severity": "error" },
    { "code": "TX005", "name": "Multiple Owners", "severity": "error" },
    { "code": "TX006", "name": "Async/Sync Mismatch", "severity": "error" },
    { "code": "TX007", "name": "Shared AsyncSession", "severity": "error" }
  ]
}
'@ | Set-Content ".backend-ai/validation-rules.json" -Encoding UTF8
}

@'
You are the Architect/Orchestrator.

Read docs/SRS.md and AGENTS.md if present.

Create a strict Day 1 implementation task for the Worker.

Scope:
- Build Route & Dependency Scanner only
- Use LibCST
- Generate .backend-ai/index-meta.json, routes.json, dependencies.json, validation-rules.json
- Extract router method/path/handler/is_async/Depends/Security/AsyncSession/source_file/line/confidence

Hard exclusions:
- No DB introspection
- No state machine validator
- No outbox worker
- No call graph

Output:
1. Files to create or modify
2. Expected CLI commands
3. Acceptance criteria
4. Test fixture requirements
5. Out-of-scope list
'@ | Set-Content "$Bus/prompts/day1_architect.md" -Encoding UTF8

gemini -p (Get-Content "$Bus/prompts/day1_architect.md" -Raw) `
    1> "$Bus/tasks/day1_task.md" `
    2> "$Bus/logs/gemini_task.stderr.log"

if ($DryRun -eq "1") {
    "==> DRY_RUN=1, stopping after task generation"
    Get-Content "$Bus/tasks/day1_task.md"
    exit 0
}

@'
You are the Worker.

Read:
- .agent_bus/tasks/day1_task.md
- docs/SRS.md
- AGENTS.md if present

Implement Day 1 only.

Rules:
- Do not broaden scope.
- Do not implement DB introspection.
- Do not implement outbox/state machine/domain invariant validators.
- Do not modify docs/SRS.md.
- Do not modify AGENTS.md.
- Do not modify existing business source files except files needed to add scanner package/tests.
- Add tests/fixtures for route scanning.
- Run tests before final response.

Write report to .agent_bus/reports/day1_worker_report.md.
'@ | Set-Content "$Bus/prompts/day1_worker.md" -Encoding UTF8

codex exec (Get-Content "$Bus/prompts/day1_worker.md" -Raw) |
    Tee-Object "$Bus/logs/codex_worker.stdout.log"

if (Get-Command pytest -ErrorAction SilentlyContinue) {
    pytest | Tee-Object "$Bus/logs/pytest.log"
} else {
    "pytest not found, skipping" | Tee-Object "$Bus/logs/pytest.log"
}

$RequiredFiles = @(
    ".backend-ai/index-meta.json",
    ".backend-ai/routes.json",
    ".backend-ai/dependencies.json",
    ".backend-ai/validation-rules.json",
    ".agent_bus/reports/day1_worker_report.md"
)

foreach ($file in $RequiredFiles) {
    if (-not (Test-Path $file)) {
        throw "Required file missing: $file"
    }
}

python -m json.tool .backend-ai/index-meta.json | Out-Null
python -m json.tool .backend-ai/routes.json | Out-Null
python -m json.tool .backend-ai/dependencies.json | Out-Null
python -m json.tool .backend-ai/validation-rules.json | Out-Null

@'
You are the Architect/Reviewer.

Read:
- docs/SRS.md
- AGENTS.md
- .agent_bus/tasks/day1_task.md
- .agent_bus/reports/day1_worker_report.md
- .backend-ai/

Review implementation against SRS v1.0.1.

Return:
1. Verdict: approve | revise | reject
2. Blocking issues
3. Non-blocking issues
4. Exact next action for Codex
'@ | Set-Content "$Bus/prompts/day1_review.md" -Encoding UTF8

gemini -p (Get-Content "$Bus/prompts/day1_review.md" -Raw) `
    1> "$Bus/reviews/day1_review.md" `
    2> "$Bus/logs/gemini_review.stderr.log"

Get-Content "$Bus/reviews/day1_review.md"