from __future__ import annotations

import argparse
import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any


class MockModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Reservation(MockModel):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not hasattr(self, "status"):
            self.status = "draft"


class StockLock(MockModel):
    pass


class Payment(MockModel):
    pass


class Query:
    def __init__(self, data, model_class):
        self.data = data
        self.model_class = model_class

    def filter(self, *args, **kwargs):
        # Very limited filter support for MVP
        # In a real sandbox, this would be more complex
        return self

    def join(self, *args):
        return self

    def outerjoin(self, *args):
        return self

    def all(self):
        return self.data

    def get(self, ident):
        for item in self.data:
            if getattr(item, "id", None) == ident:
                return item
        return None


class MockSession:
    def __init__(self):
        self._items = []

    def add(self, item):
        self._items.append(item)

    def flush(self):
        pass

    def commit(self):
        pass

    def close(self):
        pass

    def query(self, model_class):
        subset = [item for item in self._items if isinstance(item, model_class)]
        return Query(subset, model_class)


def check_invariants(session: MockSession) -> list[dict[str, Any]]:
    issues = []
    reservations = session.query(Reservation).all()
    locks = session.query(StockLock).all()
    payments = session.query(Payment).all()

    # INV001: Expired reservation must not have active stock locks
    for res in reservations:
        if res.status == "expired":
            res_locks = [l for l in locks if getattr(l, "reservation_id", None) == res.id]
            if any(getattr(l, "status", "") == "active" for l in res_locks):
                issues.append(
                    {
                        "code": "INV001",
                        "severity": "error",
                        "message": f"Reservation {res.id} is expired but still has active stock locks.",
                    }
                )

    # INV002: Paid reservation must have settled payment
    for res in reservations:
        if res.status == "paid":
            res_payments = [p for p in payments if getattr(p, "reservation_id", None) == res.id]
            if not any(getattr(p, "status", "") == "settled" for p in res_payments):
                issues.append(
                    {
                        "code": "INV002",
                        "severity": "error",
                        "message": f"Reservation {res.id} is paid but has no settled payment.",
                    }
                )

    # INV004: Cancelled reservation must release stock
    for res in reservations:
        if res.status == "cancelled":
            res_locks = [l for l in locks if getattr(l, "reservation_id", None) == res.id]
            if any(getattr(l, "status", "") == "active" for l in res_locks):
                issues.append(
                    {
                        "code": "INV004",
                        "severity": "error",
                        "message": f"Reservation {res.id} is cancelled but still has active stock locks.",
                    }
                )

    return issues


def sandbox_run(
    code_snippet: str,
    seed_data: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    session = MockSession()

    # Seed data
    if seed_data:
        for item in seed_data:
            table = item.get("table")
            data = item.get("data", {})
            if table == "reservations":
                session.add(Reservation(**data))
            elif table == "stock_locks":
                session.add(StockLock(**data))
            elif table == "payments":
                session.add(Payment(**data))

    output = io.StringIO()
    error = None
    exec_globals = {
        "session": session,
        "Reservation": Reservation,
        "StockLock": StockLock,
        "Payment": Payment,
    }

    try:
        with redirect_stdout(output):
            exec(code_snippet, exec_globals)
    except Exception:
        error = traceback.format_exc()

    issues = check_invariants(session)
    
    final_state = {
        "reservations": [
            {"id": getattr(r, "id", None), "status": r.status} for r in session.query(Reservation).all()
        ],
        "stock_locks": [
            {"id": getattr(s, "id", None), "reservation_id": getattr(s, "reservation_id", None), "status": getattr(s, "status", None)}
            for s in session.query(StockLock).all()
        ],
        "payments": [
            {"id": getattr(p, "id", None), "reservation_id": getattr(p, "reservation_id", None), "status": getattr(p, "status", None)}
            for p in session.query(Payment).all()
        ],
    }

    return {
        "status": "ok" if not error and not issues else "failed",
        "risk": "high" if error or issues else "low",
        "execution_output": output.getvalue(),
        "error": error,
        "invariant_issues": issues,
        "final_state": final_state,
        "confidence": 0.8,
        "provenance": "transactional-sandbox-mock",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a transactional sandbox for Omni-MCP (Mocked).")
    parser.add_argument("--code", required=True, help="Python code snippet to execute.")
    parser.add_argument("--seed", help="JSON string of seed data.")
    args = parser.parse_args()

    seed_data = json.loads(args.seed) if args.seed else None
    result = sandbox_run(args.code, seed_data)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
