from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SCAN_DIRS = ("src",)
EXCLUDED_DIRS = {
    ".agent_bus",
    ".backend-ai",
    ".frontend-ai",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
STORY_RE = re.compile(r"\.stories\.(?:ts|tsx|js|jsx)$")
PLAYWRIGHT_CONFIG_RE = re.compile(r"playwright\.config\.(?:ts|js|mts|mjs|cts|cjs)$")
PLAYWRIGHT_SPEC_RE = re.compile(r"\.(?:spec|e2e)\.(?:ts|tsx|js|jsx)$")


@dataclass
class StoryRecord:
    story_id: str
    title: str | None
    component: str | None
    story_name: str
    file: str
    line: int
    visual_check_ready: bool
    confidence: float
    provenance: str = "static-storybook-discovery"


@dataclass
class PlaywrightRecord:
    kind: str
    file: str
    line: int
    tests_detected: int
    expects_detected: int
    confidence: float
    provenance: str = "static-playwright-discovery"


@dataclass
class A11yRecord:
    file: str
    line: int
    component: str | None
    rule: str
    evidence: str
    confidence: float
    provenance: str = "static-a11y-discovery"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(data) + "\n", encoding="utf-8")


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def source_hash(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(file_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def discover_files(project_root: Path, roots: list[Path] | None) -> tuple[list[Path], list[str], bool]:
    warnings: list[str] = []
    scan_roots: list[Path] = []
    has_default_src = (project_root / "src").exists()

    if roots:
        scan_roots = [root if root.is_absolute() else project_root / root for root in roots]
    else:
        for name in DEFAULT_SCAN_DIRS:
            candidate = project_root / name
            if candidate.exists():
                scan_roots.append(candidate)

    if not scan_roots:
        warnings.append("No default frontend source directories found: src")
        return [], warnings, has_default_src

    files: list[Path] = []
    for root in scan_roots:
        if root.is_file():
            if root.suffix in SOURCE_SUFFIXES:
                files.append(root)
            else:
                warnings.append(f"Scan root is not a frontend source file: {relative_path(root, project_root)}")
            continue

        if not root.exists():
            warnings.append(f"Scan root does not exist: {relative_path(root, project_root)}")
            continue

        for file_path in root.rglob("*"):
            if file_path.suffix not in SOURCE_SUFFIXES:
                continue
            try:
                parts = file_path.relative_to(project_root).parts
            except ValueError:
                parts = file_path.parts
            if any(part in EXCLUDED_DIRS for part in parts):
                continue
            files.append(file_path)

    return sorted(set(files)), warnings, has_default_src


def quoted_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.S)
    if not match:
        return None
    return match.group(1) or match.group(2)


def parse_story_file(file_path: Path, project_root: Path, text: str) -> list[StoryRecord]:
    if not STORY_RE.search(file_path.name):
        return []

    title = quoted_value(r"title\s*:\s*(?:\"([^\"]+)\"|'([^']+)')", text)
    component_match = re.search(r"component\s*:\s*(\w+)", text)
    component = component_match.group(1) if component_match else None
    records: list[StoryRecord] = []

    for match in re.finditer(r"export\s+const\s+(\w+)(?:\s*:[^=]+)?\s*=", text):
        story_name = match.group(1)
        records.append(
            StoryRecord(
                story_id=f"{relative_path(file_path, project_root)}::{story_name}",
                title=title,
                component=component,
                story_name=story_name,
                file=relative_path(file_path, project_root),
                line=line_number(text, match.start(1)),
                visual_check_ready=bool(title and component),
                confidence=0.86 if title and component else 0.76,
            )
        )

    if not records:
        records.append(
            StoryRecord(
                story_id=f"{relative_path(file_path, project_root)}::default",
                title=title,
                component=component,
                story_name="default",
                file=relative_path(file_path, project_root),
                line=1,
                visual_check_ready=bool(title or component),
                confidence=0.75,
            )
        )

    return records


def parse_playwright_file(file_path: Path, project_root: Path, text: str) -> list[PlaywrightRecord]:
    records: list[PlaywrightRecord] = []
    is_config = bool(PLAYWRIGHT_CONFIG_RE.fullmatch(file_path.name))
    is_spec = bool(PLAYWRIGHT_SPEC_RE.search(file_path.name))
    if not is_config and not is_spec:
        return records

    test_count = len(re.findall(r"\btest\s*\(", text))
    expect_count = len(re.findall(r"\bexpect\s*\(", text))
    records.append(
        PlaywrightRecord(
            kind="config" if is_config else "spec",
            file=relative_path(file_path, project_root),
            line=1,
            tests_detected=test_count,
            expects_detected=expect_count,
            confidence=0.84 if is_config or test_count else 0.76,
        )
    )
    return records


def component_name_near_export(text: str, offset: int) -> str | None:
    snippet = text[offset : offset + 500]
    match = re.search(r"export\s+function\s+(\w+)", snippet)
    if match:
        return match.group(1)
    return None


def parse_a11y_records(file_path: Path, project_root: Path, text: str) -> list[A11yRecord]:
    records: list[A11yRecord] = []

    for match in re.finditer(r"@ai\.a11y\s+([^\r\n*]+)", text):
        records.append(
            A11yRecord(
                file=relative_path(file_path, project_root),
                line=line_number(text, match.start()),
                component=component_name_near_export(text, match.end()),
                rule=match.group(1).strip(),
                evidence="@ai.a11y",
                confidence=0.88,
            )
        )

    for attr_match in re.finditer(r"\b(aria-[\w-]+|role)\s*=", text):
        records.append(
            A11yRecord(
                file=relative_path(file_path, project_root),
                line=line_number(text, attr_match.start()),
                component=None,
                rule=f"uses {attr_match.group(1)}",
                evidence=attr_match.group(1),
                confidence=0.78,
            )
        )

    return records


def build_common(
    project_root: Path,
    files: list[Path],
    warnings: list[str],
    status: str,
    risk: str,
    confidence: float,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "project_root": str(project_root),
        "source_hash": source_hash(files) if files else hashlib.sha256(b"").hexdigest(),
        "confidence": confidence,
        "status": status,
        "risk": risk,
        "parser": "python-regex-static",
        "runtime_execution": "not_run",
        "warnings": warnings,
        "files_scanned": [relative_path(path, project_root) for path in files],
    }


def index_runtime_visual(project_root: Path, output_dir: Path, roots: list[Path] | None = None) -> dict[str, Any]:
    files, warnings, has_default_src = discover_files(project_root, roots)
    stories: list[StoryRecord] = []
    playwright: list[PlaywrightRecord] = []
    a11y_records: list[A11yRecord] = []

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        stories.extend(parse_story_file(file_path, project_root, text))
        playwright.extend(parse_playwright_file(file_path, project_root, text))
        a11y_records.extend(parse_a11y_records(file_path, project_root, text))

    if not files:
        warnings.append("No frontend source files were scanned; runtime and visual safety are not proven")

    if not has_default_src and not roots:
        warnings.append("No runnable frontend source directory was detected; browser runtime checks were not executed")

    status = "ok" if files and (roots or has_default_src) else "needs_manual_review"
    risk = "low" if status == "ok" else "unknown"
    confidence = 0.84 if status == "ok" else 0.5
    common = build_common(project_root, files, warnings, status, risk, confidence)
    visual_check_ready = bool(stories)
    storybook_ready = bool(stories)
    playwright_ready = any(item.kind == "config" for item in playwright)

    stories_manifest = {
        **common,
        "scanner": "frontend_storybook_static_discovery",
        "stories": [asdict(story) for story in stories],
        "story_count": len(stories),
        "storybook_ready": storybook_ready,
    }
    readiness_manifest = {
        **common,
        "scanner": "frontend_runtime_visual_readiness",
        "storybook": {
            "ready": storybook_ready,
            "story_count": len(stories),
            "runtime_render": "not_run",
        },
        "playwright": {
            "ready": playwright_ready,
            "config_count": sum(1 for item in playwright if item.kind == "config"),
            "spec_count": sum(1 for item in playwright if item.kind == "spec"),
            "runtime_execution": "not_run",
            "records": [asdict(item) for item in playwright],
        },
        "a11y_snapshot": {
            "ready": bool(a11y_records),
            "record_count": len(a11y_records),
            "records": [asdict(item) for item in a11y_records],
        },
        "visual_check": {
            "ready": visual_check_ready,
            "mode": "static-readiness",
            "screenshots": "not_generated",
            "visual_regression": "not_run",
        },
    }

    write_json(output_dir / "stories.json", stories_manifest)
    write_json(output_dir / "runtime-visual-readiness.json", readiness_manifest)
    return {"stories": stories_manifest, "readiness": readiness_manifest}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate optional frontend runtime and visual readiness manifests.")
    parser.add_argument("--project-root", default=".", help="Project root used for relative paths.")
    parser.add_argument("--root", action="append", dest="roots", help="Frontend file or directory to scan. May be repeated.")
    parser.add_argument("--target", action="append", dest="targets", help="Alias for --root.")
    parser.add_argument("--output", default=".frontend-ai", help="Output directory for generated manifests.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary after generation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    root_values = []
    if args.roots:
        root_values.extend(args.roots)
    if args.targets:
        root_values.extend(args.targets)
    roots = [Path(root) for root in root_values] if root_values else None
    result = index_runtime_visual(project_root, output_dir, roots)
    summary = {
        "status": result["readiness"]["status"],
        "risk": result["readiness"]["risk"],
        "stories": result["stories"]["story_count"],
        "storybook_ready": result["readiness"]["storybook"]["ready"],
        "playwright_ready": result["readiness"]["playwright"]["ready"],
        "a11y_records": result["readiness"]["a11y_snapshot"]["record_count"],
        "visual_check_ready": result["readiness"]["visual_check"]["ready"],
        "runtime_execution": result["readiness"]["runtime_execution"],
        "output": str(output_dir),
    }
    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
