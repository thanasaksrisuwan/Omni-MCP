from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backend_session_scanner import generate_manifests, get_session_flow, validate_transaction_usage


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    roots = [
        PROJECT_ROOT / "tests" / "fixtures" / "day2_routes.py",
        PROJECT_ROOT / "tests" / "fixtures" / "services" / "reservation_service.py",
    ]

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        generate_manifests(PROJECT_ROOT, output_dir, roots)
        session_flow = load_json(output_dir / "session-flow.json")
        transaction_boundaries = load_json(output_dir / "transaction-boundaries.json")

    flows = session_flow["flows"]
    validation = validate_transaction_usage(transaction_boundaries)
    errors = validation["errors"]
    warnings = validation["warnings"]
    codes = {issue["code"] for issue in errors + warnings}

    assert len(flows) >= 8
    assert len(transaction_boundaries["transaction_boundaries"]) >= 4
    assert session_flow["status"] == "failed"
    assert transaction_boundaries["status"] == "failed"

    for code in {"TX001", "TX002", "TX003", "TX004", "TX005", "TX006", "TX007"}:
        assert code in codes, f"missing {code}"

    flow_by_handler = {flow["handler"]: flow for flow in flows}
    safe_flow = flow_by_handler["create_safe_reservation"]
    safe_lookup = get_session_flow(session_flow, "POST /safe-reservations")
    assert safe_lookup["status"] == "ok"
    assert safe_lookup["flow"]["handler"] == "create_safe_reservation"
    assert safe_flow["session_type"] == "AsyncSession"
    assert safe_flow["session_dependency"] == "get_async_session"
    assert safe_flow["transaction_pattern"] == "async with session.begin()"
    assert any(operation["operation"] == "flush" for operation in safe_flow["session_operations"])

    tx006_messages = [issue["message"] for issue in errors if issue["code"] == "TX006"]
    assert any("sync Session" in message for message in tx006_messages)
    assert any("AsyncSession" in message for message in tx006_messages)

    tx007 = [issue for issue in errors if issue["code"] == "TX007"]
    assert tx007 and "asyncio.gather" in tx007[0]["message"]

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
