from __future__ import annotations

import asyncio
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mcp_server


FRONTEND_ROOTS = [
    "tests/fixtures/frontend/components",
    "tests/fixtures/frontend/tailwind.config.js",
    "tests/fixtures/frontend/icons.ts",
    "tests/fixtures/frontend/layouts.tsx",
    "tests/fixtures/frontend/pages",
]
BACKEND_DAY1_ROOTS = ["tests/fixtures/sample_routes.py"]
BACKEND_DAY2_ROOTS = [
    "tests/fixtures/day2_routes.py",
    "tests/fixtures/services/reservation_service.py",
]
RESERVATION_ROOTS = [
    "tests/fixtures/reservation_safe.py",
    "tests/fixtures/reservation_unsafe.py",
]


def test_expected_tool_registration() -> None:
    async def run() -> None:
        server = mcp_server.create_server()
        tools = await server.list_tools()
        names = {tool.name for tool in tools}
        assert set(mcp_server.EXPECTED_TOOL_NAMES).issubset(names)
        _content, structured = await server.call_tool(
            "frontend.search_components",
            {
                "intent": "delete destructive action",
                "roots": FRONTEND_ROOTS,
                "output": ".agent_bus/logs/mcp_server_call_tool_test",
            },
        )
        assert structured["status"] == "ok"
        assert structured["results"][0]["component_id"] == "ui.button"

    asyncio.run(run())


def test_frontend_tools_delegate_to_scanner() -> None:
    output = ".agent_bus/logs/mcp_server_frontend_test"
    index = mcp_server.frontend_index_project(roots=FRONTEND_ROOTS, output=output)
    assert index["index_meta"]["status"] == "ok"

    search = mcp_server.frontend_search_components("delete destructive action", roots=FRONTEND_ROOTS, output=output)
    assert search["status"] == "ok"
    assert search["results"][0]["component_id"] == "ui.button"

    props = mcp_server.frontend_get_prop_signature("ui.button", roots=FRONTEND_ROOTS, output=output)
    assert props["status"] == "ok"
    assert props["props"]["variant"]["allowed_values"] == ["primary", "secondary", "ghost", "danger"]

    usages = mcp_server.frontend_find_component_usages("ui.button", "destructive", roots=FRONTEND_ROOTS, output=output)
    assert usages["status"] == "ok"
    assert usages["usages"]

    tokens = mcp_server.frontend_get_design_tokens(["color"], roots=FRONTEND_ROOTS, output=output)
    assert tokens["status"] == "ok"
    assert "bg-primary" in tokens["tokens"]["classes"]

    assets = mcp_server.frontend_list_assets("trash", "icon", roots=FRONTEND_ROOTS, output=output)
    assert assets["status"] == "ok"
    assert assets["assets"][0]["name"] == "IconTrash"

    layouts = mcp_server.frontend_get_layout_patterns("management list page", roots=FRONTEND_ROOTS, output=output)
    assert layouts["status"] == "ok"
    assert layouts["patterns"][0]["pattern_id"] == "page.list-management"

    validation = mcp_server.frontend_validate_ui_code(
        "tests/fixtures/frontend/unsafe_usage.tsx",
        roots=FRONTEND_ROOTS,
        output=output,
    )
    assert validation["status"] == "failed"
    assert {issue["code"] for issue in validation["issues"]} >= {"FE001", "FE003", "FE006"}


def test_backend_tools_delegate_to_scanners() -> None:
    day1_output = ".agent_bus/logs/mcp_server_backend_day1_test"
    auth_map = mcp_server.backend_get_authorization_map(roots=BACKEND_DAY1_ROOTS, output=day1_output)
    assert auth_map["status"] == "ok"
    assert any(route["authorization_status"] == "protected" for route in auth_map["routes"])

    auth_validation = mcp_server.backend_validate_authorization(roots=BACKEND_DAY1_ROOTS, output=day1_output)
    assert auth_validation["status"] == "failed"
    assert "AUTH001" in {issue["code"] for issue in auth_validation["errors"]}

    day2_output = ".agent_bus/logs/mcp_server_backend_day2_test"
    flow = mcp_server.backend_get_session_flow(
        "POST /safe-reservations",
        roots=BACKEND_DAY2_ROOTS,
        output=day2_output,
    )
    assert flow["status"] == "ok"
    assert flow["flow"]["transaction_pattern"] == "async with session.begin()"

    tx_validation = mcp_server.backend_validate_transaction_usage(roots=BACKEND_DAY2_ROOTS, output=day2_output)
    assert tx_validation["status"] == "failed"
    assert "TX001" in {issue["code"] for issue in tx_validation["errors"] + tx_validation["warnings"]}

    reservation_output = ".agent_bus/logs/mcp_server_reservation_test"
    machine = mcp_server.backend_get_state_machine(roots=RESERVATION_ROOTS, output=reservation_output)
    assert machine["status"] == "ok"
    assert "pending_payment" in machine["state_machine"]["states"]

    state = mcp_server.backend_validate_state_transition(roots=RESERVATION_ROOTS, output=reservation_output)
    assert state["status"] == "failed"
    assert "STATE001" in {issue["code"] for issue in state["errors"] + state["warnings"]}

    idempotency = mcp_server.backend_validate_idempotency(roots=RESERVATION_ROOTS, output=reservation_output)
    assert idempotency["status"] == "failed"

    outbox = mcp_server.backend_validate_outbox_usage(roots=RESERVATION_ROOTS, output=reservation_output)
    assert outbox["status"] == "failed"

    invariants = mcp_server.backend_validate_reservation_invariants(roots=RESERVATION_ROOTS, output=reservation_output)
    assert invariants["status"] == "failed"


def test_missing_source_and_output_guard_are_conservative() -> None:
    empty = mcp_server.frontend_search_components("button", output=".agent_bus/logs/mcp_server_empty_frontend_test")
    assert empty["status"] == "needs_manual_review"
    assert empty["risk"] == "unknown"

    unsafe_output = mcp_server.frontend_index_project(roots=FRONTEND_ROOTS, output="tmp/not-allowed")
    assert unsafe_output["status"] == "needs_manual_review"
    assert unsafe_output["risk"] == "unknown"


def main() -> int:
    test_expected_tool_registration()
    test_frontend_tools_delegate_to_scanner()
    test_backend_tools_delegate_to_scanners()
    test_missing_source_and_output_guard_are_conservative()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
