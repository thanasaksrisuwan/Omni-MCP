from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.frontend_runtime_visual_scanner import index_runtime_visual


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def fixture_roots() -> list[Path]:
    base = PROJECT_ROOT / "tests" / "fixtures" / "frontend"
    return [base]


def test_runtime_visual_fixture_manifests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        result = index_runtime_visual(PROJECT_ROOT, output_dir, fixture_roots())
        stories = load_json(output_dir / "stories.json")
        readiness = load_json(output_dir / "runtime-visual-readiness.json")

    assert result["readiness"]["status"] == "ok"
    assert stories["storybook_ready"] is True
    assert stories["story_count"] == 2
    assert {story["story_name"] for story in stories["stories"]} == {"Primary", "Danger"}
    assert all(story["visual_check_ready"] for story in stories["stories"])

    assert readiness["playwright"]["ready"] is True
    assert readiness["playwright"]["config_count"] == 1
    assert readiness["playwright"]["spec_count"] == 1
    assert readiness["a11y_snapshot"]["ready"] is True
    assert readiness["a11y_snapshot"]["record_count"] >= 1
    assert readiness["visual_check"]["ready"] is True
    assert readiness["runtime_execution"] == "not_run"


def test_empty_project_scan_needs_manual_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project_root = Path(tmp)
        output_dir = project_root / ".frontend-ai"
        result = index_runtime_visual(project_root, output_dir, None)
        readiness = load_json(output_dir / "runtime-visual-readiness.json")

    assert result["readiness"]["status"] == "needs_manual_review"
    assert result["readiness"]["risk"] == "unknown"
    assert readiness["confidence"] < 0.75
    assert readiness["storybook"]["ready"] is False
    assert readiness["visual_check"]["ready"] is False


def main() -> int:
    test_runtime_visual_fixture_manifests()
    test_empty_project_scan_needs_manual_review()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
