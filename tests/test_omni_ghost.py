import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.omni_ghost import prepare_scenario
from scripts.omni_vault import sandbox_run


def test_scenario_generation():
    result = prepare_scenario("expired_reservation_with_locks")
    assert result["status"] == "ok"
    assert len(result["seed_data"]) == 2
    assert result["seed_data"][0]["table"] == "reservations"
    print("test_scenario_generation: PASSED")


def test_integration_with_vault():
    # 1. Prepare scenario via Ghost
    scenario = prepare_scenario("expired_reservation_with_locks")
    seed = scenario["seed_data"]
    
    # 2. Run Vault sandbox with this seed (should fail INV001 automatically)
    code = "print('Checking pre-existing issues...')"
    vault_result = sandbox_run(code, seed_data=seed)
    
    assert vault_result["status"] == "failed"
    assert any(issue["code"] == "INV001" for issue in vault_result["invariant_issues"])
    print("test_integration_with_vault: PASSED")


def test_unknown_scenario():
    result = prepare_scenario("invalid_scenario")
    assert result["status"] == "failed"
    assert "available_scenarios" in result
    print("test_unknown_scenario: PASSED")


if __name__ == "__main__":
    try:
        test_scenario_generation()
        test_integration_with_vault()
        test_unknown_scenario()
        print("\nAll Omni-Ghost tests passed.")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
