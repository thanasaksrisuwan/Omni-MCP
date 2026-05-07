from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import csea_policy_enforcer


def test_git_status_is_allowed() -> None:
    result = csea_policy_enforcer.validate_command("git status", PROJECT_ROOT)
    assert result["status"] == "ok"
    assert result["allowed"] is True
    assert result["allowed_family"] == "git"


def test_blacklisted_rm_is_blocked() -> None:
    result = csea_policy_enforcer.validate_command("rm -rf .", PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "rm" in result["reason"]


def test_chained_command_is_blocked() -> None:
    result = csea_policy_enforcer.validate_command("git status; rm -rf .", PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "shell operator" in result["reason"]


def test_path_escape_is_blocked() -> None:
    result = csea_policy_enforcer.validate_command("ls ../", PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "escapes Git root" in result["reason"]


def test_git_diff_requires_stat() -> None:
    result = csea_policy_enforcer.validate_command("git diff --name-only", PROJECT_ROOT)
    assert result["status"] == "blocked"
    assert "git diff --stat" in result["reason"]


def test_denied_attempt_is_logged(tmp_path: Path) -> None:
    result = csea_policy_enforcer.validate_command("rm -rf .", tmp_path)
    assert result["status"] == "blocked"
    csea_policy_enforcer.append_denied_log(tmp_path, result)
    log_path = tmp_path / ".agent_bus" / "logs" / "csea_denied.log"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["command"] == "rm -rf ."
    assert "rm" in payload["reason"]


def test_cli_check_json_output() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/csea_policy_enforcer.py",
            "--check",
            "git rev-parse --show-toplevel",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"


def test_cli_run_git_status() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/csea_policy_enforcer.py",
            "--run",
            "git status",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["returncode"] == 0


def test_powershell_discovery_is_allowed() -> None:
    result = csea_policy_enforcer.validate_command("Get-Content docs/SRS.md", PROJECT_ROOT)
    assert result["status"] == "ok"
    assert result["allowed"] is True
    assert result["allowed_family"] == "powershell-discovery"


def test_cli_run_powershell_discovery() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/csea_policy_enforcer.py",
            "--run",
            "Get-Content docs/CSEA-SRS.md",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"
    assert payload["returncode"] == 0
    assert "Controlled Semi-Autonomous" in payload["stdout"]


def test_agent_orchestration_is_allowed() -> None:
    result = csea_policy_enforcer.validate_command("gemini --version", PROJECT_ROOT)
    assert result["status"] == "ok"
    assert result["allowed"] is True
    assert result["allowed_family"] == "agent-orchestration"

    result = csea_policy_enforcer.validate_command("codex status", PROJECT_ROOT)
    assert result["status"] == "ok"
    assert result["allowed"] is True
    assert result["allowed_family"] == "agent-orchestration"


def main() -> int:
    test_git_status_is_allowed()
    test_blacklisted_rm_is_blocked()
    test_chained_command_is_blocked()
    test_path_escape_is_blocked()
    test_git_diff_requires_stat()
    test_denied_attempt_is_logged(PROJECT_ROOT / ".agent_bus" / "logs" / "csea_policy_test_tmp")
    test_cli_check_json_output()
    test_cli_run_git_status()
    test_powershell_discovery_is_allowed()
    test_cli_run_powershell_discovery()
    test_agent_orchestration_is_allowed()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
