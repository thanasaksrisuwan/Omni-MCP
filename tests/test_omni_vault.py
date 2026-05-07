import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.omni_vault import sandbox_run


def test_safe_snippet():
    code = """
res = Reservation(id=1, status='draft')
session.add(res)
session.flush()

lock = StockLock(id=1, reservation_id=1, status='active', quantity=2)
session.add(lock)
session.flush()
"""
    result = sandbox_run(code)
    assert result["status"] == "ok"
    assert result["risk"] == "low"
    assert len(result["final_state"]["reservations"]) == 1
    assert result["final_state"]["reservations"][0]["status"] == "draft"
    print("test_safe_snippet: PASSED")


def test_unsafe_expired_with_lock():
    code = """
res = Reservation(id=1, status='expired')
session.add(res)
lock = StockLock(id=1, reservation_id=1, status='active', quantity=2)
session.add(lock)
session.flush()
"""
    result = sandbox_run(code)
    assert result["status"] == "failed"
    assert result["risk"] == "high"
    assert any(issue["code"] == "INV001" for issue in result["invariant_issues"])
    print("test_unsafe_expired_with_lock: PASSED")


def test_unsafe_paid_without_settled():
    code = """
res = Reservation(id=1, status='paid')
session.add(res)
session.flush()
"""
    result = sandbox_run(code)
    assert result["status"] == "failed"
    assert result["risk"] == "high"
    assert any(issue["code"] == "INV002" for issue in result["invariant_issues"])
    print("test_unsafe_paid_without_settled: PASSED")


def test_syntax_error():
    code = "invalid python code"
    result = sandbox_run(code)
    assert result["status"] == "failed"
    assert result["risk"] == "high"
    assert result["error"] is not None
    print("test_syntax_error: PASSED")


def test_seed_data():
    seed = [
        {"table": "reservations", "data": {"id": 10, "status": "pending_payment"}},
    ]
    code = "print(session.query(Reservation).get(10).status)"
    result = sandbox_run(code, seed_data=seed)
    assert result["status"] == "ok"
    assert "pending_payment" in result["execution_output"]
    print("test_seed_data: PASSED")


if __name__ == "__main__":
    try:
        test_safe_snippet()
        test_unsafe_expired_with_lock()
        test_unsafe_paid_without_settled()
        test_syntax_error()
        test_seed_data()
        print("\nAll Omni-Vault tests passed.")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
