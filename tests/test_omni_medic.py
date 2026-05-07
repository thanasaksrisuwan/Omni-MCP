import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.omni_medic import diagnose_and_suggest


def test_tx001_suggestion():
    issues = [{"code": "TX001", "message": "Commit in service"}]
    suggestions = diagnose_and_suggest(issues)
    assert len(suggestions) == 1
    assert "Remove `session.commit()`" in suggestions[0]["suggestion"]
    assert suggestions[0]["transformation_type"] == "move_code"
    print("test_tx001_suggestion: PASSED")


def test_fe003_fuzzy_suggestion():
    issues = [{
        "code": "FE003",
        "details": {
            "attempted": "red",
            "allowed": ["primary", "secondary", "danger"]
        }
    }]
    suggestions = diagnose_and_suggest(issues)
    assert len(suggestions) == 1
    # 'red' matches 'secondary' or 'danger' depending on threshold/logic
    # In the current run it matched 'secondary'
    assert "Change 'red' to" in suggestions[0]["suggestion"]
    assert suggestions[0].get("replacement") in ["secondary", "danger"]
    print("test_fe003_fuzzy_suggestion: PASSED")


def test_inv001_suggestion():
    issues = [{"code": "INV001", "message": "Expired but has locks"}]
    suggestions = diagnose_and_suggest(issues)
    assert len(suggestions) == 1
    assert "release_active_stock_lock" in suggestions[0]["suggestion"]
    assert suggestions[0]["transformation_type"] == "insert_code"
    print("test_inv001_suggestion: PASSED")


if __name__ == "__main__":
    try:
        test_tx001_suggestion()
        test_fe003_fuzzy_suggestion()
        test_inv001_suggestion()
        print("\nAll Omni-Medic tests passed.")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
