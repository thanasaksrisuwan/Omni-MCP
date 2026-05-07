$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

Set-StrictMode -Version Latest

$AllowedCommands = @(
    "git rev-parse --show-toplevel",
    "git status --short",
    "git diff --stat",
    "Get-Location",
    "Get-ChildItem",
    "Get-Content",
    "Select-String",
    "Get-Command"
)

$SecretFileNames = @(
    ".env",
    ".env.local",
    ".env.production",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519"
)

$SecretExtensions = @(
    ".pem",
    ".key",
    ".p12",
    ".pfx"
)

function Get-GitRoot {
    $root = & git rev-parse --show-toplevel 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $root) {
        throw "Unable to resolve Git root with allowed command: git rev-parse --show-toplevel"
    }

    return (Resolve-Path -LiteralPath $root.Trim()).Path
}

function Resolve-InGitRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitRoot,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $candidate = $Path
    if (-not [System.IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path -Path $GitRoot -ChildPath $candidate
    }

    $fullPath = [System.IO.Path]::GetFullPath($candidate)
    $rootWithSeparator = $GitRoot.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar) + [System.IO.Path]::DirectorySeparatorChar

    if ($fullPath -ne $GitRoot -and -not $fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Resolved path is outside Git root: $fullPath"
    }

    return $fullPath
}

function Get-RelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitRoot,

        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $rootPath = [System.IO.Path]::GetFullPath($GitRoot).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)

    if ($fullPath.Equals($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return "."
    }

    $rootWithSeparator = $rootPath + [System.IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($rootWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside Git root: $fullPath"
    }

    return $fullPath.Substring($rootWithSeparator.Length)
}

function Test-SecretCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [System.IO.FileInfo]$File
    )

    $name = $File.Name
    $extension = $File.Extension

    if ($SecretFileNames -contains $name) {
        return "secret_filename"
    }

    if ($name -like ".env.*" -and $name -notin @(".env.example", ".env.sample")) {
        return "env_file"
    }

    if ($SecretExtensions -contains $extension) {
        return "private_key_or_certificate"
    }

    if ($name -like "secrets*") {
        return "secret_named_file"
    }

    return $null
}

function Find-SecretPaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitRoot
    )

    $excludedDirs = @(
        ".git",
        ".agent_bus",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".venv",
        "venv"
    )

    $results = New-Object System.Collections.Generic.List[object]
    $files = Get-ChildItem -LiteralPath $GitRoot -Recurse -Force -File -ErrorAction SilentlyContinue

    foreach ($file in $files) {
        $relative = Get-RelativePath -GitRoot $GitRoot -Path $file.FullName
        $parts = $relative -split "[\\/]+"
        if ($parts | Where-Object { $excludedDirs -contains $_ }) {
            continue
        }

        $riskType = Test-SecretCandidate -File $file
        if ($riskType) {
            $results.Add([ordered]@{
                path = $relative
                risk_type = $riskType
            }) | Out-Null
        }
    }

    return $results.ToArray()
}

function Get-CommandAvailability {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Names
    )

    $results = New-Object System.Collections.Generic.List[object]
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        $results.Add([ordered]@{
            name = $name
            available = [bool]$command
            source = if ($command) { $command.Source } else { $null }
            version = if ($name -eq "powershell") { $PSVersionTable.PSVersion.ToString() } elseif ($name -eq "pwsh") { "not_run: version command outside CSEA Phase 0 allowlist" } else { "not_run: version command outside CSEA Phase 0 allowlist" }
        }) | Out-Null
    }

    return $results.ToArray()
}

function Get-ManifestFiles {
    param(
        [Parameter(Mandatory = $true)]
        [string]$GitRoot
    )

    $manifestNames = @(
        "package.json",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "pyproject.toml",
        "requirements.txt",
        "Pipfile",
        "poetry.lock",
        "composer.json",
        "go.mod",
        "Cargo.toml"
    )

    $results = New-Object System.Collections.Generic.List[object]
    foreach ($name in $manifestNames) {
        $path = Join-Path -Path $GitRoot -ChildPath $name
        if (Test-Path -LiteralPath $path) {
            $results.Add($name) | Out-Null
        }
    }

    return $results.ToArray()
}

function Get-PackageManagers {
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$ManifestFiles,

        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [object[]]$CommandAvailability
    )

    $availableCommands = @{}
    foreach ($item in $CommandAvailability) {
        $availableCommands[$item.name] = $item.available
    }

    $results = New-Object System.Collections.Generic.List[object]

    if ($ManifestFiles -contains "package.json") {
        $results.Add([ordered]@{
            name = "npm"
            inferred_from = "package.json"
            available = [bool]$availableCommands["npm"]
        }) | Out-Null
    }

    if ($ManifestFiles -contains "pnpm-lock.yaml") {
        $results.Add([ordered]@{
            name = "pnpm"
            inferred_from = "pnpm-lock.yaml"
            available = [bool]$availableCommands["pnpm"]
        }) | Out-Null
    }

    if ($ManifestFiles -contains "yarn.lock") {
        $results.Add([ordered]@{
            name = "yarn"
            inferred_from = "yarn.lock"
            available = [bool]$availableCommands["yarn"]
        }) | Out-Null
    }

    if (($ManifestFiles -contains "pyproject.toml") -or ($ManifestFiles -contains "requirements.txt")) {
        $results.Add([ordered]@{
            name = "python"
            inferred_from = ($ManifestFiles | Where-Object { $_ -in @("pyproject.toml", "requirements.txt") }) -join ", "
            available = [bool]$availableCommands["python"]
        }) | Out-Null
    }

    return $results.ToArray()
}

function Write-EnvironmentReport {
    param(
        [Parameter(Mandatory = $true)]
        [string]$OutputPath,

        [Parameter(Mandatory = $true)]
        [hashtable]$Data
    )

    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# CSEA Phase 0 Environment Discovery") | Out-Null
    $lines.Add("") | Out-Null
    $lines.Add("| Field | Value |") | Out-Null
    $lines.Add("|---|---|") | Out-Null
    $lines.Add("| Generated At | $($Data.generated_at) |") | Out-Null
    $lines.Add("| OS | $($Data.os) |") | Out-Null
    $lines.Add("| Shell | $($Data.shell) |") | Out-Null
    $lines.Add("| Git Root | $($Data.git_root) |") | Out-Null
    $lines.Add("| Current Directory | $($Data.current_directory) |") | Out-Null
    $lines.Add("| Git Status Entries | $($Data.git_status_count) |") | Out-Null
    $lines.Add("") | Out-Null

    $lines.Add("## Allowed Discovery Commands Used") | Out-Null
    $lines.Add("") | Out-Null
    foreach ($command in $Data.allowed_commands_used) {
        $lines.Add("- ``$command``") | Out-Null
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Runtime Commands") | Out-Null
    $lines.Add("") | Out-Null
    foreach ($runtime in $Data.runtime_commands) {
        $source = if ($runtime.source) { $runtime.source } else { "not_found" }
        $lines.Add("- ``$($runtime.name)``: available=$($runtime.available); source=$source; version=$($runtime.version)") | Out-Null
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Package Managers") | Out-Null
    $lines.Add("") | Out-Null
    if ($Data.package_managers.Count -eq 0) {
        $lines.Add("- none detected from root manifests") | Out-Null
    } else {
        foreach ($manager in $Data.package_managers) {
            $lines.Add("- ``$($manager.name)``: inferred_from=$($manager.inferred_from); available=$($manager.available)") | Out-Null
        }
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Manifest Files") | Out-Null
    $lines.Add("") | Out-Null
    if ($Data.manifest_files.Count -eq 0) {
        $lines.Add("- none detected at Git root") | Out-Null
    } else {
        foreach ($manifest in $Data.manifest_files) {
            $lines.Add("- ``$manifest``") | Out-Null
        }
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Test And Build Commands") | Out-Null
    $lines.Add("") | Out-Null
    $lines.Add("- ``python tests/test_*.py`` style plain assertion tests are used in this repository.") | Out-Null
    $lines.Add("- ``python -m pytest ...`` is not assumed because prior evidence says pytest may be unavailable.") | Out-Null
    $lines.Add("- Build command: unknown from root manifests.") | Out-Null
    $lines.Add("") | Out-Null

    $lines.Add("## Git Preflight") | Out-Null
    $lines.Add("") | Out-Null
    if ($Data.git_status.Count -eq 0) {
        $lines.Add("- Working tree clean.") | Out-Null
    } else {
        foreach ($entry in $Data.git_status) {
            $lines.Add("- ``$entry``") | Out-Null
        }
    }
    $lines.Add("") | Out-Null
    $lines.Add('```text') | Out-Null
    if ($Data.git_diff_stat) {
        foreach ($entry in $Data.git_diff_stat) {
            $lines.Add($entry) | Out-Null
        }
    } else {
        $lines.Add("No tracked diff.") | Out-Null
    }
    $lines.Add('```') | Out-Null
    $lines.Add("") | Out-Null

    $lines.Add("## Secret Scan") | Out-Null
    $lines.Add("") | Out-Null
    $lines.Add("- No secret-like file paths detected during Phase 0 path scan.") | Out-Null

    $parent = Split-Path -Parent $OutputPath
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent | Out-Null
    }

    Set-Content -LiteralPath $OutputPath -Value $lines -Encoding UTF8
}

$gitRoot = Get-GitRoot
$outputPath = Resolve-InGitRoot -GitRoot $gitRoot -Path ".agent/environment.local.md"

$secretPaths = @(Find-SecretPaths -GitRoot $gitRoot)
if ($secretPaths.Count -gt 0) {
    Write-Error "CSEA kill switch: secret-like paths detected. Types and paths: $($secretPaths | ConvertTo-Json -Compress)"
    exit 2
}

$runtimeCommands = @(Get-CommandAvailability -Names @("python", "node", "npm", "pnpm", "yarn", "git", "powershell", "pwsh"))
$manifestFiles = @(Get-ManifestFiles -GitRoot $gitRoot)
$packageManagers = @(Get-PackageManagers -ManifestFiles $manifestFiles -CommandAvailability $runtimeCommands)
$gitStatus = @(& git status --short 2>$null)
try {
    $gitDiffStat = @(& git diff --stat 2>$null)
} catch {
    $gitDiffStat = @("git diff --stat produced a native warning; status entries are still recorded.")
}
$now = [System.DateTimeOffset]::UtcNow.ToString("o")

$reportData = @{
    generated_at = $now
    os = [System.Environment]::OSVersion.VersionString
    shell = "PowerShell $($PSVersionTable.PSVersion.ToString())"
    git_root = $gitRoot
    current_directory = (Get-Location).Path
    runtime_commands = $runtimeCommands
    manifest_files = $manifestFiles
    package_managers = $packageManagers
    git_status = $gitStatus
    git_status_count = $gitStatus.Count
    git_diff_stat = $gitDiffStat
    allowed_commands_used = $AllowedCommands
}

Write-EnvironmentReport -OutputPath $outputPath -Data $reportData
Write-Output "CSEA Phase 0 environment report written to .agent/environment.local.md"
