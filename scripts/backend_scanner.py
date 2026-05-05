from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROUTE_METHODS = {"get", "post", "put", "patch", "delete"}
DEFAULT_SCAN_DIRS = ("app", "backend", "src")
EXCLUDED_DIRS = {
    ".agent_bus",
    ".backend-ai",
    ".frontend-ai",
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "tests",
}


@dataclass
class RouteRecord:
    method: str
    path: str
    handler: str
    is_async: bool
    source_file: str
    line: int
    confidence: float
    session_type: str | None = None


@dataclass
class DependencyRecord:
    kind: str
    callable: str | None
    param: str | None
    source_file: str
    line: int
    confidence: float
    scopes: list[str] | None = None
    annotation: str | None = None
    is_async_session: bool = False
    route_method: str | None = None
    route_path: str | None = None
    handler: str | None = None


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


def dotted_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    if isinstance(node, ast.Subscript):
        return dotted_name(node.value)
    if isinstance(node, ast.Constant):
        return str(node.value)
    return None


def annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Subscript):
        base = dotted_name(node.value)
        inner_parts: list[str] = []
        if isinstance(node.slice, ast.Tuple):
            inner_parts = [part for part in (annotation_name(elt) for elt in node.slice.elts) if part]
        else:
            inner = annotation_name(node.slice)
            if inner:
                inner_parts.append(inner)
        return f"{base}[{', '.join(inner_parts)}]" if inner_parts and base else base
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = annotation_name(node.left)
        right = annotation_name(node.right)
        if left and right:
            return f"{left} | {right}"
    return dotted_name(node)


def string_value(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def string_list_value(node: ast.AST | None) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        values = [string_value(elt) for elt in node.elts]
        return [value for value in values if value is not None]
    value = string_value(node)
    return [value] if value is not None else []


def call_arg_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Call):
        return dotted_name(node.func)
    return dotted_name(node)


def route_from_decorator(decorator: ast.AST) -> tuple[str, str, int] | None:
    if not isinstance(decorator, ast.Call):
        return None
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if decorator.func.attr not in ROUTE_METHODS:
        return None

    path = string_value(decorator.args[0]) if decorator.args else None
    if path is None:
        for keyword in decorator.keywords:
            if keyword.arg == "path":
                path = string_value(keyword.value)
                break

    if path is None:
        return None

    return decorator.func.attr.upper(), path, getattr(decorator, "lineno", 0)


def dependency_from_call(
    call: ast.Call,
    *,
    param: str | None,
    annotation: str | None,
    source_file: str,
    route_method: str | None,
    route_path: str | None,
    handler: str | None,
) -> DependencyRecord | None:
    kind = dotted_name(call.func)
    if kind not in {"Depends", "fastapi.Depends", "Security", "fastapi.Security"}:
        return None

    normalized_kind = "Security" if kind.endswith("Security") else "Depends"
    dependency_callable = call_arg_name(call.args[0]) if call.args else None
    scopes: list[str] | None = None
    if normalized_kind == "Security":
        for keyword in call.keywords:
            if keyword.arg == "scopes":
                scopes = string_list_value(keyword.value)
                break
        scopes = scopes or []

    is_async_session = annotation is not None and "AsyncSession" in annotation

    return DependencyRecord(
        kind=normalized_kind,
        callable=dependency_callable,
        param=param,
        source_file=source_file,
        line=getattr(call, "lineno", 0),
        confidence=0.95 if dependency_callable else 0.7,
        scopes=scopes,
        annotation=annotation,
        is_async_session=is_async_session,
        route_method=route_method,
        route_path=route_path,
        handler=handler,
    )


def dependency_from_parameter(
    arg: ast.arg,
    default: ast.AST | None,
    *,
    source_file: str,
    route_method: str,
    route_path: str,
    handler: str,
) -> DependencyRecord | None:
    annotation = annotation_name(arg.annotation)
    if not isinstance(default, ast.Call):
        return None

    return dependency_from_call(
        default,
        param=arg.arg,
        annotation=annotation,
        source_file=source_file,
        route_method=route_method,
        route_path=route_path,
        handler=handler,
    )


def decorator_dependencies(
    decorator: ast.AST,
    *,
    source_file: str,
    route_method: str,
    route_path: str,
    handler: str,
) -> list[DependencyRecord]:
    if not isinstance(decorator, ast.Call):
        return []

    records: list[DependencyRecord] = []
    for keyword in decorator.keywords:
        if keyword.arg != "dependencies":
            continue
        if not isinstance(keyword.value, (ast.List, ast.Tuple)):
            continue
        for item in keyword.value.elts:
            if isinstance(item, ast.Call):
                record = dependency_from_call(
                    item,
                    param=None,
                    annotation=None,
                    source_file=source_file,
                    route_method=route_method,
                    route_path=route_path,
                    handler=handler,
                )
                if record:
                    records.append(record)
    return records


def scan_file(file_path: Path, project_root: Path) -> tuple[list[RouteRecord], list[DependencyRecord]]:
    source_file = relative_path(file_path, project_root)
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=source_file)
    routes: list[RouteRecord] = []
    dependencies: list[DependencyRecord] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        route_decorators = [
            (decorator, route)
            for decorator in node.decorator_list
            if (route := route_from_decorator(decorator)) is not None
        ]

        if not route_decorators:
            continue

        positional_defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
        parameter_defaults = list(zip(node.args.args, positional_defaults, strict=False))
        parameter_defaults.extend(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False))

        for decorator, (method, path, line) in route_decorators:
            session_type: str | None = None
            for arg, default in parameter_defaults:
                record = dependency_from_parameter(
                    arg,
                    default,
                    source_file=source_file,
                    route_method=method,
                    route_path=path,
                    handler=node.name,
                )
                if record:
                    dependencies.append(record)
                    if record.is_async_session:
                        session_type = "AsyncSession"

            decorator_records = decorator_dependencies(
                decorator,
                source_file=source_file,
                route_method=method,
                route_path=path,
                handler=node.name,
            )
            dependencies.extend(decorator_records)

            routes.append(
                RouteRecord(
                    method=method,
                    path=path,
                    handler=node.name,
                    is_async=isinstance(node, ast.AsyncFunctionDef),
                    source_file=source_file,
                    line=line,
                    confidence=0.95,
                    session_type=session_type,
                )
            )

    return routes, dependencies


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
        warnings.append("No default backend source directories found: app, backend, src")
        return [], warnings

    files: list[Path] = []
    for root in scan_roots:
        if root.is_file() and root.suffix == ".py":
            files.append(root)
            continue
        if not root.exists():
            warnings.append(f"Scan root does not exist: {relative_path(root, project_root)}")
            continue
        for file_path in root.rglob("*.py"):
            if any(part in EXCLUDED_DIRS for part in file_path.relative_to(project_root).parts):
                continue
            files.append(file_path)

    return sorted(set(files)), warnings


def validation_rules(generated_at: str, project_root: Path) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "source_hash": "configuration",
        "confidence": 1.0,
        "confidence_threshold": 0.75,
        "route_methods": sorted(method.upper() for method in ROUTE_METHODS),
        "critical_models": [
            "Reservation",
            "StockLock",
            "Payment",
            "PaymentTransaction",
            "OutboxEvent",
        ],
        "critical_tables": [
            "reservations",
            "stock_locks",
            "payments",
            "payment_transactions",
            "outbox_events",
        ],
        "statuses": [
            "ok",
            "needs_manual_review",
            "failed",
        ],
        "fallback_parser": "ast",
        "preferred_parser": "libcst",
        "rules": {
            "low_confidence": {
                "threshold": 0.75,
                "status": "needs_manual_review",
                "risk": "unknown",
            },
            "required_route_fields": [
                "method",
                "path",
                "handler",
                "is_async",
                "source_file",
                "line",
                "confidence",
            ],
            "required_dependency_fields": [
                "kind",
                "callable",
                "param",
                "source_file",
                "line",
                "confidence",
            ],
        },
    }


def generate_manifests(project_root: Path, output_dir: Path, roots: list[Path] | None = None) -> dict[str, Any]:
    generated_at = utc_now()
    files, warnings = discover_files(project_root, roots)
    routes: list[RouteRecord] = []
    dependencies: list[DependencyRecord] = []

    for file_path in files:
        file_routes, file_dependencies = scan_file(file_path, project_root)
        routes.extend(file_routes)
        dependencies.extend(file_dependencies)

    digest = source_hash(files) if files else hashlib.sha256(b"").hexdigest()
    confidence = 0.95 if files else 0.5
    status = "ok" if files else "needs_manual_review"
    risk = "low" if files else "unknown"
    if not files:
        warnings.append("No Python backend files were scanned; route/dependency absence is not proven")
    if any(record.confidence < 0.75 for record in dependencies):
        status = "needs_manual_review"
        risk = "unknown"
        warnings.append("One or more dependency records have confidence below 0.75")

    common = {
        "schema_version": "1.0.0",
        "generated_at": generated_at,
        "project_root": str(project_root),
        "source_hash": digest,
        "confidence": confidence,
        "status": status,
        "risk": risk,
        "parser": "ast",
        "preferred_parser": "libcst",
    }
    index_meta = {
        **common,
        "scanner": "backend_day1_route_dependency_scanner",
        "scan_roots": [relative_path(path, project_root) for path in (roots or [project_root / name for name in DEFAULT_SCAN_DIRS])],
        "files_scanned": [relative_path(path, project_root) for path in files],
        "routes_count": len(routes),
        "dependencies_count": len(dependencies),
        "warnings": warnings,
    }
    routes_manifest = {
        **common,
        "routes": [asdict(record) for record in routes],
    }
    dependencies_manifest = {
        **common,
        "dependencies": [asdict(record) for record in dependencies],
    }

    write_json(output_dir / "index-meta.json", index_meta)
    write_json(output_dir / "routes.json", routes_manifest)
    write_json(output_dir / "dependencies.json", dependencies_manifest)
    write_json(output_dir / "validation-rules.json", validation_rules(generated_at, project_root))

    return {
        "index_meta": index_meta,
        "routes": routes_manifest,
        "dependencies": dependencies_manifest,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Backend Day 1 route and dependency manifests.")
    parser.add_argument("--project-root", default=".", help="Project root used for relative paths.")
    parser.add_argument("--root", action="append", dest="roots", help="Python file or directory to scan. May be repeated.")
    parser.add_argument("--output", default=".backend-ai", help="Output directory for generated manifests.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    roots = [Path(root) for root in args.roots] if args.roots else None
    result = generate_manifests(project_root, output_dir, roots)
    summary = {
        "status": result["index_meta"]["status"],
        "routes": result["index_meta"]["routes_count"],
        "dependencies": result["index_meta"]["dependencies_count"],
        "output": str(output_dir),
        "warnings": result["index_meta"]["warnings"],
    }
    print(stable_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
