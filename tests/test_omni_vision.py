from __future__ import annotations

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mcp_server, omni_vision


BACKEND_MANIFEST_DIR = "tests/fixtures/.backend-ai"
TRACE_FILE = "tests/fixtures/vision_trace_fixtures.json"


def test_trace_route_links_transaction_trace_to_manifests() -> None:
    result = omni_vision.trace_route(
        "POST /reservations",
        project_root=PROJECT_ROOT,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
        trace_file=TRACE_FILE,
    )

    assert result["status"] == "ok"
    assert result["target"]["route"] == "POST /reservations"
    assert result["target"]["handler"] == "create_reservation"
    assert result["target"]["trace_id"] == "trace-reservation-001"
    assert result["manifest_links"]["transaction_boundaries"][0]["pattern"] == "async with session.begin()"
    assert result["runtime_summary"]["runtime_models"] == ["Reservation", "StockLock"]
    assert result["runtime_summary"]["static_models"] == ["Reservation", "StockLock"]
    assert result["risk"] == "low"
    assert result["confidence"] >= 0.75


def test_trace_route_maps_path_to_route_manifest() -> None:
    result = omni_vision.trace_route(
        "/reservations",
        project_root=PROJECT_ROOT,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
        trace_file=TRACE_FILE,
    )

    assert result["status"] == "ok"
    assert result["target"]["route"] == "POST /reservations"
    assert "request.start" in result["trace"]["event_names"]
    assert "session.begin" in result["trace"]["event_names"]


def test_unknown_trace_or_route_is_conservative() -> None:
    result = omni_vision.trace_route(
        "GET /unlinked",
        project_root=PROJECT_ROOT,
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
        trace_file=TRACE_FILE,
    )

    assert result["status"] == "needs_manual_review"
    assert result["risk"] == "unknown"
    assert "No exact backend route match" in result["reason"]


def test_missing_manifests_are_conservative() -> None:
    result = omni_vision.trace_route(
        "POST /reservations",
        project_root=PROJECT_ROOT,
        backend_manifest_dir="tests/fixtures/vision_missing/.backend-ai",
        trace_file=TRACE_FILE,
    )

    assert result["status"] == "needs_manual_review"
    assert result["risk"] == "unknown"
    assert any("routes.json" in blocker for blocker in result["details"]["blockers"])


def test_mcp_direct_registration_and_call() -> None:
    assert "omni.vision_trace_route" in mcp_server.EXPECTED_TOOL_NAMES
    result = mcp_server.omni_vision_trace_route(
        "POST /reservations",
        backend_manifest_dir=BACKEND_MANIFEST_DIR,
        trace_file=TRACE_FILE,
    )
    assert result["status"] == "ok"
    assert result["target"]["trace_id"] == "trace-reservation-001"


def test_mcp_server_call_tool() -> None:
    async def run() -> None:
        server = mcp_server.create_server()
        _content, structured = await server.call_tool(
            "omni.vision_trace_route",
            {
                "target": "POST /reservations",
                "backend_manifest_dir": BACKEND_MANIFEST_DIR,
                "trace_file": TRACE_FILE,
            },
        )
        assert structured["status"] == "ok"
        assert structured["target"]["route"] == "POST /reservations"

    asyncio.run(run())


def main() -> int:
    test_trace_route_links_transaction_trace_to_manifests()
    test_trace_route_maps_path_to_route_manifest()
    test_unknown_trace_or_route_is_conservative()
    test_missing_manifests_are_conservative()
    test_mcp_direct_registration_and_call()
    test_mcp_server_call_tool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
