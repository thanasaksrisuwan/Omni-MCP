from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backend_reservation_safety import (
    generate_manifests,
    get_state_machine,
    validate_idempotency,
    validate_outbox_usage,
    validate_reservation_invariants,
    validate_state_transition,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def issue_codes(validation: dict) -> set[str]:
    return {issue["code"] for issue in validation.get("errors", []) + validation.get("warnings", [])}


def main() -> int:
    safe_root = PROJECT_ROOT / "tests" / "fixtures" / "reservation_safe.py"
    unsafe_root = PROJECT_ROOT / "tests" / "fixtures" / "reservation_unsafe.py"

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp) / "combined"
        result = generate_manifests(PROJECT_ROOT, output_dir, [safe_root, unsafe_root])
        state_machines = load_json(output_dir / "state-machines.json")
        outbox_events = load_json(output_dir / "outbox-events.json")
        invariants = load_json(output_dir / "invariants.json")

    assert result["state_machines"]["status"] == "failed"
    assert state_machines["status"] == "failed"
    assert outbox_events["status"] == "failed"
    assert invariants["status"] == "failed"

    machine_lookup = get_state_machine(state_machines, "reservation")
    assert machine_lookup["status"] == "ok"
    assert "pending_payment" in machine_lookup["state_machine"]["states"]

    state_validation = validate_state_transition(state_machines)
    idempotency_validation = validate_idempotency(outbox_events)
    outbox_validation = validate_outbox_usage(outbox_events)
    invariant_validation = validate_reservation_invariants(invariants)

    assert {"STATE001", "STATE002"}.issubset(issue_codes(state_validation))
    assert {"IDEMP001", "IDEMP002", "IDEMP003", "IDEMP004"}.issubset(issue_codes(idempotency_validation))
    assert {"OUTBOX001", "OUTBOX002", "OUTBOX003", "OUTBOX004"}.issubset(issue_codes(outbox_validation))
    assert {"INV001", "INV002", "INV003", "INV004", "INV005", "INV006", "INV007"}.issubset(
        issue_codes(invariant_validation)
    )

    with tempfile.TemporaryDirectory() as tmp:
        safe_output_dir = Path(tmp) / "safe"
        generate_manifests(PROJECT_ROOT, safe_output_dir, [safe_root])
        safe_state = load_json(safe_output_dir / "state-machines.json")
        safe_outbox = load_json(safe_output_dir / "outbox-events.json")
        safe_invariants = load_json(safe_output_dir / "invariants.json")

    assert validate_state_transition(safe_state)["status"] == "ok"
    assert validate_idempotency(safe_outbox)["status"] == "ok"
    assert validate_outbox_usage(safe_outbox)["status"] == "ok"
    assert validate_reservation_invariants(safe_invariants)["status"] == "ok"

    with tempfile.TemporaryDirectory() as tmp:
        empty_project_root = Path(tmp) / "empty_project"
        empty_project_root.mkdir()
        empty_output_dir = Path(tmp) / "empty"
        empty = generate_manifests(empty_project_root, empty_output_dir, None)

    assert empty["state_machines"]["status"] == "needs_manual_review"
    assert empty["state_machines"]["risk"] == "unknown"
    assert empty["outbox_events"]["status"] == "needs_manual_review"
    assert empty["invariants"]["status"] == "needs_manual_review"

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
