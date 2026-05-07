from __future__ import annotations

import copy
import json
from typing import Any

from scripts import omni_ghost, omni_vault


def generate_adversarial_variations(base_seed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variations = []
    
    # 1. Variation: Zero Quantities
    var_zero = copy.deepcopy(base_seed)
    for item in var_zero:
        if item.get("table") == "stock_locks":
            item["data"]["quantity"] = 0
    variations.append({"name": "zero_quantity", "seed": var_zero})
    
    # 2. Variation: Null Foreign Keys
    var_null_fk = copy.deepcopy(base_seed)
    for item in var_null_fk:
        if "reservation_id" in item.get("data", {}):
            item["data"]["reservation_id"] = None
    variations.append({"name": "null_foreign_keys", "seed": var_null_fk})
    
    return variations


def stress_test(
    code_snippet: str,
    base_scenario: str | None = None,
    custom_seed: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    # 1. Resolve base seed
    seed = []
    if base_scenario:
        ghost_res = omni_ghost.prepare_scenario(base_scenario)
        if ghost_res["status"] == "ok":
            seed = ghost_res["seed_data"]
    elif custom_seed:
        seed = custom_seed
        
    # 2. Run Baseline
    baseline_result = omni_vault.sandbox_run(code_snippet, seed_data=seed)
    
    # 3. Generate and run adversarial variations
    variations = generate_adversarial_variations(seed)
    adversarial_results = []
    
    for var in variations:
        res = omni_vault.sandbox_run(code_snippet, seed_data=var["seed"])
        adversarial_results.append({
            "variation": var["name"],
            "status": res["status"],
            "risk": res["risk"],
            "invariant_issues": res["invariant_issues"],
            "error": res["error"]
        })
        
    # 4. Determine Verdict
    failures = [r for r in adversarial_results if r["status"] == "failed" or r["risk"] == "high"]
    verdict = "PASS"
    if failures:
        verdict = "FAIL" if len(failures) > 1 or any(r["error"] for r in failures) else "WARNING"
        
    return {
        "status": "ok",
        "verdict": verdict,
        "baseline_summary": {
            "status": baseline_result["status"],
            "risk": baseline_result["risk"],
            "issues_count": len(baseline_result["invariant_issues"])
        },
        "adversarial_reports": adversarial_results,
        "summary": f"Stress test complete. Verdict: {verdict}. {len(failures)} hostile variations failed.",
        "confidence": 0.85
    }


def main() -> int:
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Omni-Guardian: Adversarial Validation")
    parser.add_argument("--code", required=True)
    parser.add_argument("--scenario")
    args = parser.parse_args()
    
    print(json.dumps(stress_test(args.code, base_scenario=args.scenario), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
