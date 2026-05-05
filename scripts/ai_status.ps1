$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

function Write-Section {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title
    )

    Write-Host ""
    Write-Host "==> $Title"
}

function Write-FileIfExists {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$MissingMessage
    )

    if (Test-Path -LiteralPath $Path) {
        Get-Content -LiteralPath $Path
    } else {
        Write-Host $MissingMessage
    }
}

Write-Section "Current status"
Write-FileIfExists -Path ".agent_bus/status/current.md" -MissingMessage "No .agent_bus/status/current.md found"

Write-Section "Task ledger"
Write-FileIfExists -Path ".agent_bus/status/task-ledger.json" -MissingMessage "No .agent_bus/status/task-ledger.json found"

Write-Section "Latest daily status"
if (Test-Path -LiteralPath ".agent_bus/daily") {
    $latest = Get-ChildItem -LiteralPath ".agent_bus/daily" -Filter "*.md" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($latest) {
        Get-Content -LiteralPath $latest.FullName
    } else {
        Write-Host "No daily status found"
    }
} else {
    Write-Host "No .agent_bus/daily directory found"
}

Write-Section "Git status"
$gitOutput = & cmd.exe /d /c "git status --short 2>&1"
$gitExitCode = $LASTEXITCODE

if ($gitExitCode -eq 0) {
    if ($gitOutput) {
        $gitOutput
    } else {
        Write-Host "Working tree clean"
    }
} else {
    Write-Host "Unable to read git status. Git exited with code $gitExitCode."
    $gitOutput
}
