from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any


def fuzzy_match(target: str, candidates: list[str], threshold: float = 0.3) -> str | None:
    matches = difflib.get_close_matches(target, candidates, n=1, cutoff=threshold)
    return matches[0] if matches else None


def diagnose_and_suggest(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions = []
    
    for issue in issues:
        code = issue.get("code")
        message = issue.get("message", "")
        
        # TX001: Commit in Service
        if code == "TX001":
            suggestions.append({
                "issue_code": code,
                "diagnosis": "Transaction commit detected in service/repository layer.",
                "suggestion": "Remove `session.commit()` from this file. Move the transaction boundary to the controller or route handler using `async with session.begin():`.",
                "transformation_type": "move_code"
            })
            
        # FE003: Invalid Prop Value
        elif code == "FE003":
            # Extract attempted value and allowed values if present in message/details
            # For MVP, assume we can parse it from the message or it's provided in details
            details = issue.get("details", {})
            attempted = details.get("attempted")
            allowed = details.get("allowed", [])
            
            if attempted and allowed:
                best_match = fuzzy_match(attempted, allowed)
                if best_match:
                    suggestions.append({
                        "issue_code": code,
                        "diagnosis": f"Invalid prop value '{attempted}'. Possible typo.",
                        "suggestion": f"Change '{attempted}' to '{best_match}'.",
                        "replacement": best_match,
                        "transformation_type": "replace_literal"
                    })
            else:
                suggestions.append({
                    "issue_code": code,
                    "diagnosis": "Invalid prop value.",
                    "suggestion": "Check the component manifest for allowed union values.",
                    "transformation_type": "manual_fix"
                })
                
        # INV001: Missing Release Stock
        elif code == "INV001":
            suggestions.append({
                "issue_code": code,
                "diagnosis": "Expired reservation must release stock locks.",
                "suggestion": "Add `await release_active_stock_lock(session, reservation_id)` before finishing the flow.",
                "transformation_type": "insert_code"
            })

    return suggestions


def main() -> int:
    # CLI test wrapper
    import sys
    if len(sys.argv) > 1:
        issues = json.loads(sys.argv[1])
        print(json.dumps(diagnose_and_suggest(issues), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
