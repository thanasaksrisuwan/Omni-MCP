from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def analyze_surface(
    component_id: str,
    *,
    props_manifest: dict[str, Any] | None = None,
    usages_manifest: dict[str, Any] | None = None,
    tokens_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyzes a UI component for accessibility and UX semantic quality."""
    
    insights = []
    base_score = 1.0
    
    # Mock data for demonstration if manifests are missing
    props = (props_manifest or {}).get(component_id, {})
    usages = (usages_manifest or {}).get(component_id, [])
    
    # 1. A11Y-001: Missing Label Check
    # If it's a Button or Link and has an icon prop but no children/label
    if "Button" in component_id or "Link" in component_id:
        # Check if typically used without labels in usages (simplified heuristic)
        for usage in usages:
            props_used = usage.get("props_used", {})
            if "icon" in props_used and "children" not in props_used and "label" not in props_used:
                if "aria-label" not in props_used:
                    insights.append({
                        "code": "A11Y-001",
                        "severity": "warning",
                        "message": f"Icon-only usage of '{component_id}' at {usage.get('file')}:{usage.get('line')} is missing an 'aria-label'.",
                        "impact": "Screen readers will not be able to describe this action."
                    })
                    base_score -= 0.1

    # 2. UX-001: Layout Hierarchy
    if "Page" in component_id and "Container" not in component_id:
        # Pages should have headers (heuristic: check props for title or children for Header)
        has_header_signal = any("header" in p.lower() or "title" in p.lower() for p in props.keys())
        if not has_header_signal:
            insights.append({
                "code": "UX-001",
                "severity": "info",
                "message": f"Page component '{component_id}' might be missing a clear 'PageHeader' or title prop.",
                "impact": "Users might lose context of where they are in the application."
            })
            base_score -= 0.05

    # 3. VIS-001: Token Compliance
    # Check if any hardcoded colors are detected (simplified for MVP)
    for usage in usages:
        context = usage.get("summary", "").lower()
        if "#" in context or "rgb" in context:
            insights.append({
                "code": "VIS-001",
                "severity": "error",
                "message": f"Hardcoded color detected in usage of '{component_id}' at {usage.get('file')}.",
                "impact": "Breaks visual consistency and theme support. Use Design Tokens instead."
            })
            base_score -= 0.2

    return {
        "status": "ok",
        "component_id": component_id,
        "semantic_score": max(0.0, round(base_score, 2)),
        "ux_insights": insights,
        "verdict": "GOOD" if base_score > 0.8 else "NEEDS_IMPROVEMENT" if base_score > 0.5 else "CRITICAL",
        "confidence": 0.8,
        "provenance": "omni-aura-static-heuristics"
    }


def main() -> int:
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Omni-Aura: Visual/UX Semantics")
    parser.add_argument("--component", required=True)
    args = parser.parse_args()
    
    print(json.dumps(analyze_surface(args.component), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
