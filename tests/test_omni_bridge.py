from __future__ import annotations

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mcp_server, omni_bridge


FRONTEND_MANIFEST_DIR = "tests/fixtures/.frontend-ai"
BACKEND_MANIFEST_DIR = "tests/fixtures/.backend-ai"


def test_pack_frontend_component_context() -> None:
    result = omni_bridge.bridge_pack_context(
        "ui.button",
        target_type="frontend_component",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir=FRONTEND_MANIFEST_DIR,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert result["status"] == "ok"
    assert result["target"]["type"] == "frontend_component"
    assert result["target"]["component_id"] == "ui.button"
    assert result["context"]["props"]["props"]["variant"]["allowed_values"] == [
        "primary",
        "secondary",
        "ghost",
        "danger",
    ]
    assert result["context"]["usages"][0]["file"] == "tests/fixtures/frontend/pages/InventoryPage.tsx"
    assert result["risk"] == "low"
    assert result["confidence"] >= 0.75


def test_pack_backend_route_context() -> None:
    result = omni_bridge.bridge_pack_context(
        "POST /reservations",
        target_type="backend_route",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir=FRONTEND_MANIFEST_DIR,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert result["status"] == "ok"
    assert result["target"]["type"] == "backend_route"
    assert result["target"]["route"] == "POST /reservations"
    assert result["context"]["dependencies"][1]["scopes"] == ["reservation:create"]
    assert result["context"]["session_flow"]["transaction_pattern"] == "async with session.begin()"
    assert result["impact"]["critical_models_touched"] == ["Reservation", "StockLock"]
    assert result["risk"] == "medium"


def test_auto_target_uses_exact_manifest_match() -> None:
    frontend = omni_bridge.bridge_pack_context(
        "Button",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir=FRONTEND_MANIFEST_DIR,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert frontend["status"] == "ok"
    assert frontend["target"]["type"] == "frontend_component"

    backend = omni_bridge.bridge_pack_context(
        "/reservations",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir=FRONTEND_MANIFEST_DIR,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert backend["status"] == "ok"
    assert backend["target"]["type"] == "backend_route"


def test_missing_manifests_are_conservative() -> None:
    result = omni_bridge.bridge_pack_context(
        "ui.button",
        target_type="frontend_component",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir="tests/fixtures/bridge_missing/.frontend-ai",
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert result["status"] == "needs_manual_review"
    assert result["risk"] == "unknown"
    assert "Missing required manifest" in result["reason"]


def test_low_confidence_manifest_is_conservative() -> None:
    result = omni_bridge.bridge_pack_context(
        "ui.button",
        target_type="frontend_component",
        project_root=PROJECT_ROOT,
        frontend_manifest_dir="tests/fixtures/bridge_low_confidence/.frontend-ai",
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert result["status"] == "needs_manual_review"
    assert result["risk"] == "unknown"
    assert any("confidence" in blocker for blocker in result["details"]["blockers"])


def test_mcp_tool_registration_and_direct_call() -> None:
    assert "omni.bridge_pack_context" in mcp_server.EXPECTED_TOOL_NAMES
    result = mcp_server.omni_bridge_pack_context(
        "ui.button",
        target_type="frontend_component",
        frontend_manifest_dir=FRONTEND_MANIFEST_DIR,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
    )
    assert result["status"] == "ok"
    assert result["target"]["component_id"] == "ui.button"


def test_mcp_server_call_tool() -> None:
    async def run() -> None:
        server = mcp_server.create_server()
        _content, structured = await server.call_tool(
            "omni.bridge_pack_context",
            {
                "target": "POST /reservations",
                "target_type": "backend_route",
                "frontend_manifest_dir": FRONTEND_MANIFEST_DIR,
                "backend_manifest_dir": BACKEND_MANIFEST_DIR,
            },
        )
        assert structured["status"] == "ok"
        assert structured["target"]["route"] == "POST /reservations"

    asyncio.run(run())


def main() -> int:
    test_pack_frontend_component_context()
    test_pack_backend_route_context()
    test_auto_target_uses_exact_manifest_match()
    test_missing_manifests_are_conservative()
    test_low_confidence_manifest_is_conservative()
    test_mcp_tool_registration_and_direct_call()
    test_mcp_server_call_tool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
