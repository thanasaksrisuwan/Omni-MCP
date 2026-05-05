[CmdletBinding()]
param(
    [string]$ReportPath,
    [string]$TaskName,
    [string]$Model,
    [switch]$DryRun,
    [switch]$NoSkipTrust
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function ConvertTo-SafeName {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $safe = [regex]::Replace($Name.ToLowerInvariant(), "[^a-z0-9._-]+", "_")
    $safe = $safe.Trim("._-")

    if ([string]::IsNullOrWhiteSpace($safe)) {
        return "latest_task"
    }

    return $safe
}

function Get-LatestWorkerReport {
    $reportsDir = ".agent_bus/reports"

    if (-not (Test-Path -LiteralPath $reportsDir)) {
        return $null
    }

    return Get-ChildItem -LiteralPath $reportsDir -Filter "*_worker_report.md" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-ReviewVerdict {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $inline = [regex]::Match($Text, "(?im)^\s*(?:##\s*)?Verdict\s*:?\s*(approve|revise|reject)\b")
    if ($inline.Success) {
        return $inline.Groups[1].Value.ToLowerInvariant()
    }

    $heading = [regex]::Match($Text, "(?ims)^##\s*Verdict\s*\r?\n\s*(approve|revise|reject)\b")
    if ($heading.Success) {
        return $heading.Groups[1].Value.ToLowerInvariant()
    }

    return $null
}

function Get-OptionalFileContent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        return Get-Content -LiteralPath $Path -Raw
    }

    return "File not found: $Path"
}

function Get-LatestDailyStatus {
    $dailyDir = ".agent_bus/daily"

    if (-not (Test-Path -LiteralPath $dailyDir)) {
        return $null
    }

    return Get-ChildItem -LiteralPath $dailyDir -Filter "*.md" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Get-CleanReviewText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $match = [regex]::Match($Text, "(?ims)#\s*Review:.*$")
    if ($match.Success) {
        return $match.Value.Trim()
    }

    return $Text.Trim()
}

function Write-FailedReview {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ReviewPath,

        [Parameter(Mandatory = $true)]
        [string]$TaskName,

        [Parameter(Mandatory = $true)]
        [string]$Reason,

        [string]$RawOutputPath
    )

    $rawLine = "None"
    if (-not [string]::IsNullOrWhiteSpace($RawOutputPath)) {
        $rawLine = $RawOutputPath
    }

    $content = @"
# Review Request Failed: $TaskName

## Verdict
reject

## Blocking Issues

- Gemini review did not complete successfully, so architect review remains pending.
- $Reason

## Non-blocking Issues

None.

## SRS Compliance

Unknown. Gemini did not complete the review.

## Scope Compliance

Unknown. Gemini did not complete the review.

## Artifact Check

Unknown. Gemini did not complete the review.

## Test Check

Unknown. Gemini did not complete the review.

## Confidence

Low

## Raw Output

$rawLine

## Next Action

Fix the blocking issue and rerun `powershell -ExecutionPolicy Bypass -File scripts/ai_review_gemini.ps1`.
"@

    Set-Content -LiteralPath $ReviewPath -Value $content -Encoding utf8
}

New-Item -ItemType Directory -Force -Path ".agent_bus/prompts", ".agent_bus/reviews", ".agent_bus/logs" | Out-Null

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $latestReport = Get-LatestWorkerReport

    if (-not $latestReport) {
        Write-Error "No worker report found under .agent_bus/reports/*_worker_report.md"
        exit 2
    }

    $ReportPath = $latestReport.FullName
}

if (-not (Test-Path -LiteralPath $ReportPath)) {
    Write-Error "Worker report not found: $ReportPath"
    exit 2
}

$resolvedReport = Resolve-Path -LiteralPath $ReportPath

if ([string]::IsNullOrWhiteSpace($TaskName)) {
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedReport.Path)
    $TaskName = $baseName -replace "_worker_report$", ""
}

$safeTaskName = ConvertTo-SafeName -Name $TaskName
$promptPath = ".agent_bus/prompts/${safeTaskName}_review_prompt.md"
$reviewPath = ".agent_bus/reviews/${safeTaskName}_review.md"
$rawOutputPath = ".agent_bus/logs/${safeTaskName}_gemini_review.raw.md"
$currentStatusText = Get-OptionalFileContent -Path ".agent_bus/status/current.md"
$taskLedgerText = Get-OptionalFileContent -Path ".agent_bus/status/task-ledger.json"
$workerReportText = Get-OptionalFileContent -Path $resolvedReport.Path
$latestDaily = Get-LatestDailyStatus
$latestDailyPath = "No daily status file found"
$latestDailyText = "No daily status file found"

if ($latestDaily) {
    $latestDailyPath = $latestDaily.FullName
    $latestDailyText = Get-OptionalFileContent -Path $latestDaily.FullName
}

$prompt = @"
You are Gemini CLI acting only as Architect / Reviewer for the Omni-MCP project.

Review the latest Codex worker output against:
- AGENTS.md
- docs/SRS.md
- docs/ROADMAP.md
- docs/DAILY_PROTOCOL.md
- docs/ORCHESTRATION.md
- .agent_bus/status/current.md
- .agent_bus/status/task-ledger.json
- $($resolvedReport.Path)

Important:
- Some `.agent_bus/` files may be ignored by Gemini's file tools.
- The required runtime evidence is embedded below.
- Use the embedded evidence if file tool access is blocked.
- If embedded evidence is insufficient, do not approve.

Rules:
- Do not edit files.
- Do not implement code.
- Do not expand scope.
- Do not modify docs/SRS.md.
- Do not approve uncertain work.
- If evidence is missing, use verdict revise or reject.
- If generated JSON is required, verify it is valid before approve.
- If tests are required but missing, do not approve unless the worker report gives an acceptable no-test reason.
- If the work touches source-of-truth files or business code without scope, reject.

Required output format:

# Review: $TaskName

## Verdict
approve | revise | reject

## Blocking Issues
List blocking issues, or "None".

## Non-blocking Issues
List non-blocking issues, or "None".

## SRS Compliance
State whether the work matches docs/SRS.md.

## Scope Compliance
State whether the work stayed inside scope.

## Artifact Check
State whether expected artifacts exist and are valid.

## Test Check
State whether tests passed or were skipped with acceptable reason.

## Confidence
High | Medium | Low

## Next Action
Give the exact next action for Codex or the human.

---

## Embedded Runtime Evidence

### Current Status: .agent_bus/status/current.md

~~~~markdown
$currentStatusText
~~~~

### Task Ledger: .agent_bus/status/task-ledger.json

~~~~json
$taskLedgerText
~~~~

### Latest Daily Status: $latestDailyPath

~~~~markdown
$latestDailyText
~~~~

### Worker Report: $($resolvedReport.Path)

~~~~markdown
$workerReportText
~~~~
"@

Set-Content -LiteralPath $promptPath -Value $prompt -Encoding utf8

if ($DryRun) {
    Write-Host "Dry run complete."
    Write-Host "Worker report: $($resolvedReport.Path)"
    Write-Host "Prompt path: $promptPath"
    Write-Host "Review path: $reviewPath"
    exit 0
}

$geminiCommand = Get-Command gemini -ErrorAction SilentlyContinue

if (-not $geminiCommand) {
    Write-FailedReview -ReviewPath $reviewPath -TaskName $TaskName -Reason "Gemini CLI was not found on PATH." -RawOutputPath ""
    Write-Host "Gemini CLI was not found. Wrote blocking review to $reviewPath"
    exit 2
}

$geminiArgs = @("--approval-mode", "plan", "--output-format", "text")

if (-not $NoSkipTrust) {
    $geminiArgs += "--skip-trust"
}

if (-not [string]::IsNullOrWhiteSpace($Model)) {
    $geminiArgs += @("--model", $Model)
}

$geminiArgs += @("-p", "Review the instructions provided on stdin.")

$resolvedPrompt = Resolve-Path -LiteralPath $promptPath
$resolvedRawOutput = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($rawOutputPath)
$quotedPrompt = '"' + $resolvedPrompt.Path + '"'
$quotedRawOutput = '"' + $resolvedRawOutput + '"'
$quotedGeminiArgs = ($geminiArgs | ForEach-Object {
    if ($_ -match '\s|["&|<>]') {
        '"' + ($_ -replace '"', '\"') + '"'
    } else {
        $_
    }
}) -join " "

$commandLine = "type $quotedPrompt | gemini $quotedGeminiArgs > $quotedRawOutput 2>&1"
& cmd.exe /d /c $commandLine
$geminiExitCode = $LASTEXITCODE
$geminiText = ""

if (Test-Path -LiteralPath $rawOutputPath) {
    $geminiText = (Get-Content -LiteralPath $rawOutputPath -Raw).Trim()
}

if ($geminiExitCode -ne 0) {
    Write-FailedReview -ReviewPath $reviewPath -TaskName $TaskName -Reason "Gemini CLI exited with code $geminiExitCode." -RawOutputPath $rawOutputPath
    Write-Host "Gemini review failed. Wrote blocking review to $reviewPath"
    exit 2
}

$cleanReviewText = Get-CleanReviewText -Text $geminiText
$verdict = Get-ReviewVerdict -Text $cleanReviewText

if ([string]::IsNullOrWhiteSpace($verdict)) {
    Write-FailedReview -ReviewPath $reviewPath -TaskName $TaskName -Reason "Gemini output did not include a valid verdict: approve, revise, or reject." -RawOutputPath $rawOutputPath
    Write-Host "Gemini review format was invalid. Wrote blocking review to $reviewPath"
    exit 3
}

Set-Content -LiteralPath $reviewPath -Value $cleanReviewText -Encoding utf8

Write-Host "Gemini review complete."
Write-Host "Verdict: $verdict"
Write-Host "Review path: $reviewPath"

switch ($verdict) {
    "approve" { exit 0 }
    "revise" { exit 10 }
    "reject" { exit 20 }
    default { exit 3 }
}
