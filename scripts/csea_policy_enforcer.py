from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SHELL_OPERATORS = {"|", ">", ">>", "<", ";", "&&", "||"}
BLACKLIST_PATTERNS = ("DROP", "TRUNCATE", "migrate:fresh")
POWERSHELL_COMMANDS = {"Get-Location", "Get-ChildItem", "Get-Content", "Select-String", "Get-Command"}
POSIX_COMMANDS = {"pwd", "ls", "cat", "grep"}
GIT_STATUS_FLAGS = {"--short", "-s", "--porcelain", "--branch"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)


def uncertainty(reason: str) -> dict[str, Any]:
    return {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": reason,
        "confidence": 0.0,
    }


def resolve_project_root(project_root: str | Path | None = None) -> Path:
    base = Path(project_root) if project_root else PROJECT_ROOT
    if not base.is_absolute():
        base = Path.cwd() / base
    return base.resolve()


def resolve_git_root(project_root: Path) -> Path:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=project_root,
            capture_output=True,
            text=True,
            shell=False,
            timeout=10,
            check=False,
        )
    except OSError:
        return project_root.resolve()

    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return project_root.resolve()


def is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def parse_command(command: str) -> tuple[list[str], str | None]:
    if not isinstance(command, str) or not command.strip():
        return [], "command is required."

    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        return [], f"command parse failed: {exc}"

    if not tokens:
        return [], "command is empty."
    return tokens, None


def contains_shell_operator(command: str, tokens: list[str]) -> str | None:
    for operator in SHELL_OPERATORS:
        if operator in tokens:
            return f"shell operator is blocked: {operator}"

    # Catch common chained forms without pretending this is a shell grammar.
    for operator in ("&&", "||", ">>"):
        if operator in command:
            return f"shell operator is blocked: {operator}"
    if ";" in command:
        return "shell operator is blocked: ;"
    if "|" in command:
        return "shell operator is blocked: |"
    if ">" in command or "<" in command:
        return "shell redirection is blocked."
    return None


def contains_blacklist(command: str, tokens: list[str]) -> str | None:
    upper_command = command.upper()
    for pattern in BLACKLIST_PATTERNS:
        if pattern.upper() in upper_command:
            return f"blacklisted pattern is blocked: {pattern}"

    if tokens and tokens[0].lower() == "rm":
        flags = {token for token in tokens[1:] if token.startswith("-")}
        if any("r" in flag and "f" in flag for flag in flags):
            return "blacklisted destructive rm command is blocked."

    return None


def normalize_path_token(token: str) -> str:
    return token.strip().strip('"').strip("'")


def token_looks_like_path(token: str) -> bool:
    value = normalize_path_token(token)
    if not value or value.startswith("-"):
        return False
    if value in {".", ".."}:
        return True
    if value.startswith("./") or value.startswith("../") or value.startswith(".\\") or value.startswith("..\\"):
        return True
    if "/" in value or "\\" in value:
        return True
    if Path(value).is_absolute():
        return True
    return False


def validate_path_tokens(tokens: list[str], git_root: Path) -> str | None:
    for token in tokens[1:]:
        if not token_looks_like_path(token):
            continue
        value = normalize_path_token(token)
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = git_root / candidate
        resolved = candidate.resolve(strict=False)
        if not is_relative_to(resolved, git_root):
            return f"path argument escapes Git root: {value}"
    return None


def validate_git(tokens: list[str]) -> str | None:
    if len(tokens) < 2:
        return "git subcommand is required."

    subcommand = tokens[1]
    args = tokens[2:]

    if subcommand == "status":
        invalid = [arg for arg in args if arg.startswith("-") and arg not in GIT_STATUS_FLAGS]
        if invalid:
            return f"git status flag is not allowlisted: {invalid[0]}"
        return None

    if subcommand == "diff":
        if not args or args[0] != "--stat":
            return "only git diff --stat is allowlisted."
        return None

    if subcommand == "rev-parse":
        if args == ["--show-toplevel"]:
            return None
        return "only git rev-parse --show-toplevel is allowlisted."

    return f"git subcommand is not allowlisted: {subcommand}"


def validate_command(command: str, project_root: str | Path | None = None) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    git_root = resolve_git_root(root)
    tokens, parse_error = parse_command(command)
    if parse_error:
        return blocked(command, parse_error, git_root)

    for check in (
        contains_shell_operator(command, tokens),
        contains_blacklist(command, tokens),
        validate_path_tokens(tokens, git_root),
    ):
        if check:
            return blocked(command, check, git_root)

    executable = tokens[0]
    if executable == "git":
        git_error = validate_git(tokens)
        if git_error:
            return blocked(command, git_error, git_root)
        allowed_family = "git"
    elif executable in POWERSHELL_COMMANDS:
        allowed_family = "powershell-discovery"
    elif executable in POSIX_COMMANDS:
        allowed_family = "posix-discovery"
    elif executable == "command":
        if len(tokens) >= 3 and tokens[1] == "-v":
            allowed_family = "posix-discovery"
        else:
            return blocked(command, "only command -v is allowlisted.", git_root)
    elif executable == "uname":
        if tokens[1:] == ["-a"]:
            allowed_family = "posix-discovery"
        else:
            return blocked(command, "only uname -a is allowlisted.", git_root)
    else:
        return blocked(command, f"command is not allowlisted: {executable}", git_root)

    return {
        "status": "ok",
        "risk": "low",
        "allowed": True,
        "command": command,
        "argv": tokens,
        "git_root": str(git_root),
        "allowed_family": allowed_family,
        "confidence": 0.9,
        "provenance": "csea-command-policy",
    }


def blocked(command: str, reason: str, git_root: Path) -> dict[str, Any]:
    return {
        "status": "blocked",
        "risk": "high",
        "allowed": False,
        "command": command,
        "reason": reason,
        "git_root": str(git_root),
        "confidence": 0.95,
        "provenance": "csea-command-policy",
    }


def append_denied_log(project_root: Path, result: dict[str, Any]) -> None:
    log_path = project_root / ".agent_bus" / "logs" / "csea_denied.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": utc_now(),
        "command": result.get("command"),
        "reason": result.get("reason"),
        "risk": result.get("risk"),
    }
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=True, sort_keys=True) + "\n")


def run_command(command: str, project_root: str | Path | None = None) -> dict[str, Any]:
    validation = validate_command(command, project_root)
    root = resolve_project_root(project_root)
    git_root = Path(validation.get("git_root", resolve_git_root(root))).resolve()
    if validation.get("status") != "ok":
        append_denied_log(root, validation)
        return validation

    argv = validation["argv"]
    if validation.get("allowed_family") == "powershell-discovery":
        return {
            **validation,
            "status": "needs_manual_review",
            "risk": "unknown",
            "reason": "PowerShell cmdlet execution requires an approved host wrapper; use --check for policy validation.",
        }

    try:
        completed = subprocess.run(
            argv,
            cwd=git_root,
            capture_output=True,
            text=True,
            shell=False,
            timeout=30,
            check=False,
        )
    except OSError as exc:
        return {
            **validation,
            "status": "failed",
            "risk": "unknown",
            "reason": str(exc),
        }

    return {
        **validation,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "status": "ok" if completed.returncode == 0 else "failed",
        "risk": "low" if completed.returncode == 0 else "unknown",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CSEA command policy enforcer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", help="Validate a command without executing it.")
    group.add_argument("--run", help="Validate and execute an allowlisted command.")
    parser.add_argument("--project-root", default=".", help="Project root or any path inside the Git root.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check:
        result = validate_command(args.check, args.project_root)
        if result.get("status") != "ok":
            append_denied_log(resolve_project_root(args.project_root), result)
    else:
        result = run_command(args.run, args.project_root)

    print(stable_json(result))
    return 0 if result.get("status") == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
