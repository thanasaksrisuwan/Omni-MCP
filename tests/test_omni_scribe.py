from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mcp_server, omni_scribe


ARTIFACT_DIR = ".agent_bus/scribes/core002_test"


def artifact_path(result: dict[str, object]) -> Path:
    path = result.get("artifact_path")
    assert isinstance(path, str)
    return PROJECT_ROOT / path


def test_valid_frontend_plan_writes_artifact_only() -> None:
    target = PROJECT_ROOT / "src/__omni_scribe_should_not_write__.tsx"
    result = omni_scribe.plan_write(
        "src/__omni_scribe_should_not_write__.tsx",
        "export function SafePanel() {\n  return <div />;\n}\n",
        project_root=PROJECT_ROOT,
        artifact_dir=ARTIFACT_DIR,
    )

    assert result["status"] == "ok"
    assert result["risk"] == "low"
    assert not target.exists()

    artifact = artifact_path(result)
    assert artifact.exists()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["target_file_path"] == "src/__omni_scribe_should_not_write__.tsx"
    assert payload["proposed_content"].startswith("export function SafePanel")
    assert payload["note"].startswith("This artifact is a plan only.")


def test_invalid_frontend_plan_is_blocked() -> None:
    result = omni_scribe.plan_write(
        "src/__omni_scribe_invalid__.tsx",
        "export function BadPanel() {\n  return <UnknownWidget />;\n}\n",
        project_root=PROJECT_ROOT,
        artifact_dir=ARTIFACT_DIR,
    )

    assert result["status"] == "blocked"
    assert result["artifact_path"] is None
    assert "FE001" in {issue["code"] for issue in result["issues"]}


def test_invalid_backend_plan_is_blocked_by_transaction_validator() -> None:
    result = omni_scribe.plan_write(
        "services/reservation_service.py",
        (
            "from sqlalchemy.orm import Session\n\n"
            "def unsafe_reservation_update(session: Session) -> None:\n"
            "    session.commit()\n"
        ),
        project_root=PROJECT_ROOT,
        artifact_dir=ARTIFACT_DIR,
    )

    assert result["status"] == "blocked"
    assert result["artifact_path"] is None
    assert "TX001" in {issue["code"] for issue in result["issues"]}


def test_mcp_direct_registration_and_call() -> None:
    assert "omni.scribe_plan_write" in mcp_server.EXPECTED_TOOL_NAMES
    result = mcp_server.omni_scribe_plan_write(
        "src/__omni_scribe_mcp__.tsx",
        "export function ViaMcp() {\n  return <div />;\n}\n",
        artifact_dir=ARTIFACT_DIR,
    )
    assert result["status"] == "ok"
    assert artifact_path(result).exists()


def test_mcp_server_call_tool() -> None:
    async def run() -> None:
        server = mcp_server.create_server()
        _content, structured = await server.call_tool(
            "omni.scribe_plan_write",
            {
                "target_file_path": "src/__omni_scribe_call_tool__.tsx",
                "proposed_content": "export function CallToolPlan() {\n  return <div />;\n}\n",
                "artifact_dir": ARTIFACT_DIR,
            },
        )
        assert structured["status"] == "ok"
        assert artifact_path(structured).exists()

    asyncio.run(run())


def main() -> int:
    test_valid_frontend_plan_writes_artifact_only()
    test_invalid_frontend_plan_is_blocked()
    test_invalid_backend_plan_is_blocked_by_transaction_validator()
    test_mcp_direct_registration_and_call()
    test_mcp_server_call_tool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
