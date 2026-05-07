from __future__ import annotations

import json
from typing import Any


def prepare_scenario(scenario: str) -> dict[str, Any]:
    """Generates synthetic seed data for Omni-Vault based on a scenario."""
    
    if scenario == "expired_reservation_with_locks":
        return {
            "status": "ok",
            "scenario": scenario,
            "seed_data": [
                {"table": "reservations", "data": {"id": 100, "status": "expired"}},
                {"table": "stock_locks", "data": {"id": 1, "reservation_id": 100, "status": "active", "quantity": 5}}
            ],
            "description": "Simulation of a reservation that expired but failed to release stock locks."
        }
    
    elif scenario == "partially_paid_reservation":
        return {
            "status": "ok",
            "scenario": scenario,
            "seed_data": [
                {"table": "reservations", "data": {"id": 200, "status": "pending_payment"}},
                {"table": "payments", "data": {"id": 1, "reservation_id": 200, "status": "settled"}},
                {"table": "payments", "data": {"id": 2, "reservation_id": 200, "status": "failed"}}
            ],
            "description": "Simulation of a reservation with multiple payment attempts, one successful."
        }
        
    elif scenario == "confirmed_no_stock":
        return {
            "status": "ok",
            "scenario": scenario,
            "seed_data": [
                {"table": "reservations", "data": {"id": 300, "status": "confirmed"}},
                {"table": "stock_locks", "data": {"id": 3, "reservation_id": 300, "status": "released", "quantity": 0}}
            ],
            "description": "Simulation of a confirmed reservation where stock lock was incorrectly released or never held."
        }

    return {
        "status": "failed",
        "error": f"Unknown scenario: {scenario}",
        "available_scenarios": [
            "expired_reservation_with_locks",
            "partially_paid_reservation",
            "confirmed_no_stock"
        ]
    }


def main() -> int:
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Omni-Ghost: Synthetic Data Simulator")
    parser.add_argument("--scenario", required=True, help="Scenario name to prepare.")
    args = parser.parse_args()
    
    print(json.dumps(prepare_scenario(args.scenario), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
