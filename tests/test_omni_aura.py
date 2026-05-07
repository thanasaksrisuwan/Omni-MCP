import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.omni_aura import analyze_surface


def test_a11y_missing_label():
    # Usage of a button with icon but no aria-label or children
    usages = {
        "ui.Button": [
            {
                "file": "src/components/MyButton.tsx",
                "line": 10,
                "props_used": {"icon": "CloseIcon"}
            }
        ]
    }
    result = analyze_surface("ui.Button", usages_manifest=usages)
    assert result["status"] == "ok"
    assert any(insight["code"] == "A11Y-001" for insight in result["ux_insights"])
    print("test_a11y_missing_label: PASSED")


def test_ux_layout_hierarchy():
    # A page component with no title or header signals in props
    props = {"ui.ProfilePage": {"userId": "string"}}
    result = analyze_surface("ui.ProfilePage", props_manifest=props)
    assert result["status"] == "ok"
    assert any(insight["code"] == "UX-001" for insight in result["ux_insights"])
    print("test_ux_layout_hierarchy: PASSED")


def test_vis_hardcoded_colors():
    # Usage with a hex code in the context summary
    usages = {
        "ui.Card": [
            {
                "file": "src/pages/Dashboard.tsx",
                "summary": "Container with background #f0f0f0"
            }
        ]
    }
    result = analyze_surface("ui.Card", usages_manifest=usages)
    assert result["status"] == "ok"
    assert any(insight["code"] == "VIS-001" for insight in result["ux_insights"])
    print("test_vis_hardcoded_colors: PASSED")


if __name__ == "__main__":
    try:
        test_a11y_missing_label()
        test_ux_layout_hierarchy()
        test_vis_hardcoded_colors()
        print("\nAll Omni-Aura tests passed.")
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)
