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
VALIDATION_RULES = ["FE001", "FE002", "FE003", "FE004", "FE005", "FE006", "FE007", "FE008"]
TOKEN_PREFIXES = ("bg-", "text-", "border-", "rounded-", "p-", "px-", "py-", "m-", "mx-", "my-", "gap-")


@dataclass
class ComponentRecord:
    component_id: str
    name: str
    import_path: str
    source_file: str
    line: int
    intent: str
    avoid: str | None
    status: str
    a11y: str | None
    props_type: str | None
    confidence: float
    provenance: str = "manual-jsdoc"


@dataclass
class PropRecord:
    name: str
    type: str
    required: bool
    allowed_values: list[str] | None
    default: str | None
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class AssetRecord:
    name: str
    kind: str
    import_path: str
    source_file: str
    line: int
    aliases: list[str]
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class ComponentUsageRecord:
    component_id: str
    component_name: str
    file: str
    line: int
    import_path: str | None
    props_used: dict[str, str | bool]
    summary: str
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class LayoutPatternRecord:
    pattern_id: str
    file: str
    line: int
    tree: list[str]
    examples: list[str]
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class ValidationIssue:
    code: str
    severity: str
    file: str
    line: int
    message: str
    component_id: str | None
    suggested_fix: str | None
    confidence: float
    provenance: str = "manifest-validation"


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


def source_hash(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for file_path in sorted(files, key=lambda item: item.as_posix()):
        digest.update(file_path.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def discover_files(project_root: Path, roots: list[Path] | None) -> tuple[list[Path], list[str]]:
    warnings: list[str] = []
    scan_roots: list[Path] = []

    if roots:
        scan_roots = [root if root.is_absolute() else project_root / root for root in roots]
    else:
        for name in DEFAULT_SCAN_DIRS:
            candidate = project_root / name
            if candidate.exists():
                scan_roots.append(candidate)

    if not scan_roots:
        warnings.append("No default frontend source directories found: src")
        return [], warnings

    files: list[Path] = []
    for root in scan_roots:
        if root.is_file() and root.suffix in SOURCE_SUFFIXES:
            files.append(root)
            continue
        if not root.exists():
            warnings.append(f"Scan root does not exist: {relative_path(root, project_root)}")
            continue
        for file_path in root.rglob("*"):
            if file_path.suffix not in SOURCE_SUFFIXES:
                continue
            if any(part in EXCLUDED_DIRS for part in file_path.relative_to(project_root).parts):
                continue
            files.append(file_path)

    return sorted(set(files)), warnings


def import_path_for(file_path: Path, project_root: Path) -> str:
    rel = relative_path(file_path, project_root)
    no_suffix = str(Path(rel).with_suffix("")).replace("\\", "/")
    if no_suffix.startswith("tests/fixtures/frontend/"):
        no_suffix = no_suffix.replace("tests/fixtures/frontend/", "", 1)
        return "@/" + no_suffix
    if no_suffix.startswith("src/"):
        return "@/" + no_suffix[4:]
    return no_suffix


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def jsdoc_metadata(comment: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for raw_line in comment.splitlines():
        line = raw_line.strip().lstrip("*").strip()
        if not line.startswith("@ai."):
            continue
        key_value = line[4:].split(None, 1)
        if len(key_value) == 2:
            metadata[key_value[0]] = key_value[1].strip()
    return metadata


def parse_allowed_values(type_text: str) -> list[str] | None:
    values = re.findall(r'"([^"]+)"|\'([^\']+)\'', type_text)
    flattened = [first or second for first, second in values]
    return flattened or None


def parse_props(text: str) -> dict[str, dict[str, PropRecord]]:
    props_by_type: dict[str, dict[str, PropRecord]] = {}
    pattern = re.compile(r"export\s+(?:interface|type)\s+(\w+)\s*(?:=\s*)?\{(?P<body>.*?)\}", re.S)
    for match in pattern.finditer(text):
        type_name = match.group(1)
        body = match.group("body")
        props: dict[str, PropRecord] = {}
        for raw_line in body.splitlines():
            line = raw_line.strip().rstrip(";")
            if not line or line.startswith("//"):
                continue
            prop_match = re.match(r"(\w+)(\?)?\s*:\s*(.+)$", line)
            if not prop_match:
                continue
            prop_name = prop_match.group(1)
            optional = bool(prop_match.group(2))
            type_text = prop_match.group(3).strip()
            props[prop_name] = PropRecord(
                name=prop_name,
                type=type_text,
                required=not optional,
                allowed_values=parse_allowed_values(type_text),
                default=None,
                confidence=0.88,
            )
        props_by_type[type_name] = props
    return props_by_type


def parse_components(file_path: Path, project_root: Path, text: str) -> tuple[list[ComponentRecord], dict[str, dict[str, PropRecord]]]:
    props_by_type = parse_props(text)
    components: list[ComponentRecord] = []
    pattern = re.compile(
        r"(?P<comment>/\*\*.*?\*/)\s*export\s+function\s+(?P<name>\w+)\s*\((?P<params>.*?)\)",
        re.S,
    )
    for match in pattern.finditer(text):
        metadata = jsdoc_metadata(match.group("comment"))
        component_id = metadata.get("component")
        intent = metadata.get("intent")
        if not component_id or not intent:
            continue
        params = match.group("params")
        props_type_match = re.search(r":\s*(\w+)", params)
        props_type = props_type_match.group(1) if props_type_match else None
        components.append(
            ComponentRecord(
                component_id=component_id,
                name=match.group("name"),
                import_path=import_path_for(file_path, project_root),
                source_file=relative_path(file_path, project_root),
                line=line_number(text, match.start("name")),
                intent=intent,
                avoid=metadata.get("avoid"),
                status=metadata.get("status", "stable"),
                a11y=metadata.get("a11y"),
                props_type=props_type,
                confidence=0.93 if props_type in props_by_type else 0.8,
            )
        )
    return components, props_by_type


def token_classes_from_text(text: str) -> set[str]:
    tokens: set[str] = set()
    for quoted in re.findall(r'["\']([A-Za-z0-9_:#./ -]+)["\']', text):
        for token in quoted.split():
            if token.startswith(TOKEN_PREFIXES):
                tokens.add(token)

    for section, prefix in (("colors", ("bg-", "text-", "border-")), ("spacing", ("p-", "px-", "py-", "m-", "mx-", "my-", "gap-")), ("borderRadius", ("rounded-",))):
        section_match = re.search(section + r"\s*:\s*\{(?P<body>.*?)\}", text, re.S)
        if not section_match:
            continue
        for key in re.findall(r"(\w+)\s*:", section_match.group("body")):
            if key in {"DEFAULT", "extend"}:
                continue
            for item_prefix in prefix:
                tokens.add(item_prefix + key)
    return tokens


def parse_assets(file_path: Path, project_root: Path, text: str) -> list[AssetRecord]:
    assets: list[AssetRecord] = []
    for match in re.finditer(r"export\s+(?:function|const)\s+(Icon\w+)", text):
        name = match.group(1)
        aliases = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", name.replace("Icon", ""))
        assets.append(
            AssetRecord(
                name=name,
                kind="icon",
                import_path=import_path_for(file_path, project_root),
                source_file=relative_path(file_path, project_root),
                line=line_number(text, match.start(1)),
                aliases=[alias.lower() for alias in aliases],
                confidence=0.9,
            )
        )
    return assets


def summarize_usage(component_name: str, props_used: dict[str, str | bool]) -> str:
    if props_used.get("variant") == "danger":
        return f"{component_name} used for destructive action"
    if "loading" in props_used:
        return f"{component_name} used with loading state"
    if props_used:
        return f"{component_name} used with props: {', '.join(sorted(props_used))}"
    return f"{component_name} used without explicit props"


def parse_component_usages(
    file_path: Path,
    project_root: Path,
    text: str,
    components_by_name: dict[str, ComponentRecord],
) -> list[ComponentUsageRecord]:
    imports = import_records(text)
    usages: list[ComponentUsageRecord] = []
    for tag, attrs, line in jsx_tags(text):
        component = components_by_name.get(tag)
        if not component:
            continue
        props_used = attr_values(attrs)
        usages.append(
            ComponentUsageRecord(
                component_id=component.component_id,
                component_name=component.name,
                file=relative_path(file_path, project_root),
                line=line,
                import_path=imports.get(tag),
                props_used=props_used,
                summary=summarize_usage(component.name, props_used),
                confidence=0.88 if imports.get(tag) == component.import_path else 0.78,
            )
        )
    return usages


def parse_layout_patterns(file_path: Path, project_root: Path, text: str) -> list[LayoutPatternRecord]:
    layout_names = {
        "PageContainer",
        "PageHeader",
        "Toolbar",
        "Card",
        "DataTable",
        "FormSection",
        "EmptyState",
    }
    found: list[tuple[str, int]] = []
    for tag, _attrs, line in jsx_tags(text):
        if tag in layout_names:
            found.append((tag, line))
    if not found:
        return []

    seen: set[str] = set()
    tree: list[str] = []
    for tag, _line in found:
        if tag in seen:
            continue
        seen.add(tag)
        tree.append(tag)

    pattern_id = "page.list-management" if {"PageContainer", "PageHeader", "Toolbar", "DataTable"} <= set(tree) else "page.custom"
    return [
        LayoutPatternRecord(
            pattern_id=pattern_id,
            file=relative_path(file_path, project_root),
            line=found[0][1],
            tree=tree,
            examples=[relative_path(file_path, project_root)],
            confidence=0.86 if pattern_id != "page.custom" else 0.76,
        )
    ]


def build_common(project_root: Path, files: list[Path], warnings: list[str], status: str, risk: str, confidence: float) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "generated_at": utc_now(),
        "project_root": str(project_root),
        "source_hash": source_hash(files) if files else hashlib.sha256(b"").hexdigest(),
        "confidence": confidence,
        "status": status,
        "risk": risk,
        "parser": "python-regex",
        "preferred_parser": "ts-morph",
        "warnings": warnings,
        "files_scanned": [relative_path(path, project_root) for path in files],
    }


def index_project(project_root: Path, output_dir: Path, roots: list[Path] | None = None) -> dict[str, Any]:
    files, warnings = discover_files(project_root, roots)
    components: list[ComponentRecord] = []
    props_by_component: dict[str, dict[str, PropRecord]] = {}
    all_tokens: set[str] = set()
    assets: list[AssetRecord] = []
    file_texts: dict[Path, str] = {}

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        file_texts[file_path] = text
        file_components, props_by_type = parse_components(file_path, project_root, text)
        components.extend(file_components)
        for component in file_components:
            props_by_component[component.component_id] = props_by_type.get(component.props_type or "", {})
        all_tokens.update(token_classes_from_text(text))
        assets.extend(parse_assets(file_path, project_root, text))

    components_by_name = {component.name: component for component in components}
    usages: list[ComponentUsageRecord] = []
    layouts: list[LayoutPatternRecord] = []
    for file_path, text in file_texts.items():
        usages.extend(parse_component_usages(file_path, project_root, text, components_by_name))
        layouts.extend(parse_layout_patterns(file_path, project_root, text))

    if not files:
        warnings.append("No frontend source files were scanned; UI safety is not proven")

    status = "ok" if files else "needs_manual_review"
    risk = "low" if files else "unknown"
    confidence = 0.88 if files else 0.5
    common = build_common(project_root, files, warnings, status, risk, confidence)

    components_manifest = {
        **common,
        "scanner": "frontend_component_semantic_graph",
        "components": [asdict(component) for component in components],
    }
    props_manifest = {
        **common,
        "scanner": "frontend_prop_signature",
        "props": {
            component_id: {
                "component_id": component_id,
                "props": {name: asdict(prop) for name, prop in props.items()},
                "confidence": 0.9 if props else 0.5,
                "provenance": "static-analysis",
            }
            for component_id, props in props_by_component.items()
        },
    }
    tokens_manifest = {
        **common,
        "scanner": "frontend_design_tokens",
        "tokens": {
            "classes": sorted(all_tokens),
            "by_prefix": {
                prefix.rstrip("-"): sorted(token for token in all_tokens if token.startswith(prefix))
                for prefix in TOKEN_PREFIXES
            },
        },
    }
    assets_manifest = {
        **common,
        "scanner": "frontend_asset_icon_catalog",
        "assets": [asdict(asset) for asset in assets],
    }
    usages_manifest = {
        **common,
        "scanner": "frontend_component_usage_graph",
        "usages": [asdict(usage) for usage in usages],
    }
    layouts_manifest = {
        **common,
        "scanner": "frontend_layout_patterns",
        "patterns": [asdict(layout) for layout in layouts],
    }
    index_meta = {
        **common,
        "scanner": "frontend_week1_index_project",
        "components": len(components),
        "props": sum(len(props) for props in props_by_component.values()),
        "tokens": len(all_tokens),
        "assets": len(assets),
        "usages": len(usages),
        "layouts": len(layouts),
    }

    write_json(output_dir / "index-meta.json", index_meta)
    write_json(output_dir / "components.json", components_manifest)
    write_json(output_dir / "props.json", props_manifest)
    write_json(output_dir / "tokens.json", tokens_manifest)
    write_json(output_dir / "assets.json", assets_manifest)
    write_json(output_dir / "usages.json", usages_manifest)
    write_json(output_dir / "layouts.json", layouts_manifest)
    return {
        "index_meta": index_meta,
        "components": components_manifest,
        "props": props_manifest,
        "tokens": tokens_manifest,
        "assets": assets_manifest,
        "usages": usages_manifest,
        "layouts": layouts_manifest,
    }


def component_lookup(components_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {component["name"]: component for component in components_manifest.get("components", [])}


def component_id_lookup(components_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {component["component_id"]: component for component in components_manifest.get("components", [])}


def search_components(components_manifest: dict[str, Any], intent: str, limit: int = 5) -> dict[str, Any]:
    query_terms = {term for term in re.split(r"\W+", intent.lower()) if term}
    results: list[dict[str, Any]] = []
    for component in components_manifest.get("components", []):
        haystack = " ".join(
            [
                component.get("component_id", ""),
                component.get("name", ""),
                component.get("intent", ""),
                component.get("avoid") or "",
                component.get("status", ""),
            ]
        ).lower()
        score = sum(1 for term in query_terms if term in haystack) / max(len(query_terms), 1)
        if score <= 0:
            continue
        recommended_props: dict[str, str] = {}
        if "danger" in haystack or "delete" in intent.lower() or "destructive" in intent.lower():
            recommended_props["variant"] = "danger"
        results.append(
            {
                "component_id": component["component_id"],
                "name": component["name"],
                "import_path": component["import_path"],
                "score": round(min(score + 0.35, 1.0), 2),
                "why": f"Matches intent metadata: {component.get('intent', '')}",
                "recommended_props": recommended_props,
                "confidence": component.get("confidence", 0.0),
            }
        )
    return {"status": "ok", "results": sorted(results, key=lambda item: item["score"], reverse=True)[:limit]}


def get_prop_signature(props_manifest: dict[str, Any], component_id: str) -> dict[str, Any]:
    signature = props_manifest.get("props", {}).get(component_id)
    if not signature:
        return {
            "status": "needs_manual_review",
            "risk": "unknown",
            "reason": f"No prop signature found for {component_id}",
        }
    return {"status": "ok", **signature}


def find_component_usages(usages_manifest: dict[str, Any], component_id: str, context: str | None = None, limit: int = 5) -> dict[str, Any]:
    context_terms = {term for term in re.split(r"\W+", (context or "").lower()) if term}
    matches: list[dict[str, Any]] = []
    for usage in usages_manifest.get("usages", []):
        if usage.get("component_id") != component_id:
            continue
        score = 1.0
        if context_terms:
            haystack = f"{usage.get('summary', '')} {' '.join(map(str, usage.get('props_used', {}).values()))}".lower()
            score = sum(1 for term in context_terms if term in haystack) / max(len(context_terms), 1)
            if score == 0:
                continue
        matches.append({**usage, "score": round(score, 2)})
    return {"status": "ok", "usages": sorted(matches, key=lambda item: item["score"], reverse=True)[:limit]}


def get_layout_patterns(layouts_manifest: dict[str, Any], intent: str | None = None, limit: int = 5) -> dict[str, Any]:
    intent_terms = {term for term in re.split(r"\W+", (intent or "").lower()) if term}
    patterns: list[dict[str, Any]] = []
    for pattern in layouts_manifest.get("patterns", []):
        score = 1.0
        if intent_terms:
            haystack = f"{pattern.get('pattern_id', '')} {' '.join(pattern.get('tree', []))}".lower()
            score = sum(1 for term in intent_terms if term in haystack) / max(len(intent_terms), 1)
            if score == 0:
                continue
        patterns.append({**pattern, "score": round(score, 2)})
    return {"status": "ok", "patterns": sorted(patterns, key=lambda item: item["score"], reverse=True)[:limit]}


def import_records(text: str) -> dict[str, str]:
    imports: dict[str, str] = {}
    for match in re.finditer(r"import\s+\{(?P<names>[^}]+)\}\s+from\s+[\"'](?P<path>[^\"']+)[\"']", text):
        path = match.group("path")
        for name in match.group("names").split(","):
            clean = name.strip().split(" as ")[-1].strip()
            if clean:
                imports[clean] = path
    return imports


def jsx_tags(text: str) -> list[tuple[str, str, int]]:
    tags: list[tuple[str, str, int]] = []
    for match in re.finditer(r"<(?P<tag>[A-Z]\w*)(?P<attrs>[^<>]*?)(?:/?>)", text, re.S):
        tag = match.group("tag")
        if tag in {"React", "Fragment"}:
            continue
        tags.append((tag, match.group("attrs"), line_number(text, match.start())))
    return tags


def attr_values(attrs: str) -> dict[str, str | bool]:
    values: dict[str, str | bool] = {}
    for match in re.finditer(r"(\w+)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|\{([^}]*)\}))?", attrs):
        name = match.group(1)
        if name in {"true", "false"}:
            continue
        value = match.group(2) or match.group(3) or match.group(4)
        values[name] = value if value is not None else True
    return values


def issue(
    code: str,
    message: str,
    file_path: Path,
    project_root: Path,
    line: int,
    component_id: str | None = None,
    suggested_fix: str | None = None,
    confidence: float = 0.9,
    severity: str = "error",
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        file=relative_path(file_path, project_root),
        line=line,
        message=message,
        component_id=component_id,
        suggested_fix=suggested_fix,
        confidence=confidence,
    )


def validate_ui_code(
    file_path: Path,
    project_root: Path,
    components_manifest: dict[str, Any],
    props_manifest: dict[str, Any],
    tokens_manifest: dict[str, Any],
    assets_manifest: dict[str, Any],
) -> dict[str, Any]:
    text = file_path.read_text(encoding="utf-8")
    imports = import_records(text)
    components_by_name = component_lookup(components_manifest)
    assets_by_name = {asset["name"]: asset for asset in assets_manifest.get("assets", [])}
    token_classes = set(tokens_manifest.get("tokens", {}).get("classes", []))
    issues: list[ValidationIssue] = []

    for tag, attrs, line in jsx_tags(text):
        if tag.startswith("Icon"):
            if tag not in assets_by_name:
                issues.append(issue("FE005", f"Unknown icon `{tag}`.", file_path, project_root, line, suggested_fix="Use an exported icon from assets manifest."))
            continue

        component = components_by_name.get(tag)
        if not component:
            issues.append(issue("FE001", f"Unknown component `{tag}`.", file_path, project_root, line))
            continue

        component_id = component["component_id"]
        imported_from = imports.get(tag)
        if imported_from and imported_from != component["import_path"]:
            issues.append(
                issue(
                    "FE002",
                    f"Import path for `{tag}` is `{imported_from}`, expected `{component['import_path']}`.",
                    file_path,
                    project_root,
                    line,
                    component_id,
                    f"Import from `{component['import_path']}`.",
                )
            )

        if component.get("status") == "deprecated":
            issues.append(issue("FE007", f"Component `{tag}` is deprecated.", file_path, project_root, line, component_id))

        props = props_manifest.get("props", {}).get(component_id, {}).get("props", {})
        attrs_lookup = attr_values(attrs)
        for prop_name, prop in props.items():
            if prop.get("required") and prop_name not in attrs_lookup:
                issues.append(issue("FE004", f"Required prop `{prop_name}` is missing on `{tag}`.", file_path, project_root, line, component_id))
            if prop_name in attrs_lookup and prop.get("allowed_values"):
                value = attrs_lookup[prop_name]
                if isinstance(value, str) and value.strip("\"'") not in prop["allowed_values"]:
                    suggestion = f"Use one of: {', '.join(prop['allowed_values'])}."
                    issues.append(issue("FE003", f"Invalid prop value `{value}` for `{tag}.{prop_name}`.", file_path, project_root, line, component_id, suggestion))

    for match in re.finditer(r"className\s*=\s*(?:\"([^\"]*)\"|'([^']*)')", text):
        classes = (match.group(1) or match.group(2) or "").split()
        for class_name in classes:
            if class_name.startswith(TOKEN_PREFIXES) and class_name not in token_classes:
                issues.append(issue("FE006", f"Unknown design token class `{class_name}`.", file_path, project_root, line_number(text, match.start())))

    for match in re.finditer(r"className\s*=\s*\{`[^`]*\$\{[^`]*`}", text):
        issues.append(
            issue(
                "FE008",
                "Dynamic Tailwind class construction detected.",
                file_path,
                project_root,
                line_number(text, match.start()),
                suggested_fix="Use a static token map from the manifest.",
                confidence=0.95,
                severity="warning",
            )
        )

    status = "failed" if any(item.severity == "error" for item in issues) else "ok"
    return {
        "status": status,
        "issues": [asdict(item) for item in issues],
        "rules_checked": VALIDATION_RULES,
        "confidence": 0.9,
        "provenance": "manifest-validation",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Frontend Week 1 component manifests.")
    parser.add_argument("--project-root", default=".", help="Project root used for relative paths.")
    parser.add_argument("--root", action="append", dest="roots", help="Frontend file or directory to scan. May be repeated.")
    parser.add_argument("--output", default=".frontend-ai", help="Output directory for generated manifests.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary after generation.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    roots = [Path(root) for root in args.roots] if args.roots else None
    result = index_project(project_root, output_dir, roots)
    summary = {
        "status": result["index_meta"]["status"],
        "risk": result["index_meta"]["risk"],
        "components": result["index_meta"]["components"],
        "props": result["index_meta"]["props"],
        "tokens": result["index_meta"]["tokens"],
        "assets": result["index_meta"]["assets"],
        "usages": result["index_meta"]["usages"],
        "layouts": result["index_meta"]["layouts"],
        "output": str(output_dir),
    }
    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
