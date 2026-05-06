from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.frontend_scanner import (
    find_component_usages,
    get_layout_patterns,
    get_prop_signature,
    index_project,
    search_components,
    validate_ui_code,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_roots() -> list[Path]:
    base = PROJECT_ROOT / "tests" / "fixtures" / "frontend"
    return [
        base / "components",
        base / "tailwind.config.js",
        base / "icons.ts",
        base / "layouts.tsx",
        base / "pages",
    ]


def test_frontend_week1_manifests_and_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        result = index_project(PROJECT_ROOT, output_dir, fixture_roots())
        index_meta = load_json(output_dir / "index-meta.json")
        components = load_json(output_dir / "components.json")
        props = load_json(output_dir / "props.json")
        tokens = load_json(output_dir / "tokens.json")
        assets = load_json(output_dir / "assets.json")

    assert result["index_meta"]["status"] == "ok"
    assert index_meta["components"] == 2
    assert index_meta["assets"] == 2
    assert index_meta["usages"] >= 2
    assert index_meta["layouts"] >= 1
    assert "bg-primary" in tokens["tokens"]["classes"]
    assert "IconArrowRight" in {asset["name"] for asset in assets["assets"]}

    by_id = {component["component_id"]: component for component in components["components"]}
    assert by_id["ui.button"]["name"] == "Button"
    assert by_id["ui.button"]["import_path"] == "@/components/ui/Button"

    signature = get_prop_signature(props, "ui.button")
    assert signature["status"] == "ok"
    assert signature["props"]["label"]["required"] is True
    assert signature["props"]["variant"]["allowed_values"] == ["primary", "secondary", "ghost", "danger"]

    search = search_components(components, "delete destructive action")
    assert search["status"] == "ok"
    assert search["results"][0]["component_id"] == "ui.button"
    assert search["results"][0]["recommended_props"]["variant"] == "danger"

    validation = validate_ui_code(
        PROJECT_ROOT / "tests" / "fixtures" / "frontend" / "unsafe_usage.tsx",
        PROJECT_ROOT,
        components,
        props,
        tokens,
        assets,
    )
    codes = {issue["code"] for issue in validation["issues"]}
    assert validation["status"] == "failed"
    assert {"FE001", "FE002", "FE003", "FE004", "FE005", "FE006", "FE007", "FE008"}.issubset(codes)


def test_frontend_usage_and_layout_tools() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        result = index_project(PROJECT_ROOT, output_dir, fixture_roots())
        usages = load_json(output_dir / "usages.json")
        layouts = load_json(output_dir / "layouts.json")

    assert result["index_meta"]["status"] == "ok"
    usage_lookup = find_component_usages(usages, "ui.button", "destructive action")
    assert usage_lookup["status"] == "ok"
    assert usage_lookup["usages"]
    assert usage_lookup["usages"][0]["props_used"]["variant"] == "danger"
    assert usage_lookup["usages"][0]["file"].endswith("InventoryPage.tsx")

    layout_lookup = get_layout_patterns(layouts, "management list page")
    assert layout_lookup["status"] == "ok"
    assert layout_lookup["patterns"]
    pattern = layout_lookup["patterns"][0]
    assert pattern["pattern_id"] == "page.list-management"
    assert pattern["tree"] == ["PageContainer", "PageHeader", "Toolbar", "Card", "DataTable"]
    assert pattern["examples"][0].endswith("InventoryPage.tsx")


def test_empty_project_scan_needs_manual_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        output_dir = project_root / ".frontend-ai"
        result = index_project(project_root, output_dir, None)

    assert result["index_meta"]["status"] == "needs_manual_review"
    assert result["index_meta"]["risk"] == "unknown"
    assert result["index_meta"]["confidence"] < 0.75


def main() -> int:
    test_frontend_week1_manifests_and_tools()
    test_frontend_usage_and_layout_tools()
    test_empty_project_scan_needs_manual_review()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
