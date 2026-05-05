from __future__ import annotations

import argparse
import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.backend_scanner import (
        DEFAULT_SCAN_DIRS,
        EXCLUDED_DIRS,
        annotation_name,
        call_arg_name,
        dotted_name,
        relative_path,
        route_from_decorator,
        stable_json,
        string_value,
        write_json,
    )
except ModuleNotFoundError:
    from backend_scanner import (
        DEFAULT_SCAN_DIRS,
        EXCLUDED_DIRS,
        annotation_name,
        call_arg_name,
        dotted_name,
        relative_path,
        route_from_decorator,
        stable_json,
        string_value,
        write_json,
    )


SESSION_OPERATIONS = {"add", "delete", "execute", "flush", "commit", "rollback", "begin"}
CRITICAL_MODELS = {"Reservation", "StockLock", "Payment", "PaymentTransaction", "OutboxEvent"}
SIDE_EFFECT_HINTS = {
    "add_task",
    "email",
    "webhook",
    "queue",
    "dispatch",
    "external",
    "notification",
    "notify",
    "inventory_sync",
    "payment_sync",
    "send",
    "charge",
}


@dataclass
class SessionOperation:
    operation: str
    session: str
    source_file: str
    line: int
    inside_transaction: bool
    transaction_line: int | None
    function: str
    confidence: float
    target_model: str | None = None
    provenance: str = "static-analysis"


@dataclass
class TransactionBoundary:
    function: str
    source_file: str
    line: int
    session: str
    session_type: str | None
    context_kind: str
    pattern: str
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class SideEffectRecord:
    call: str
    source_file: str
    line: int
    function: str
    inside_transaction: bool
    transaction_line: int | None
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class FunctionAnalysis:
    name: str
    source_file: str
    line: int
    is_async: bool
    session_params: dict[str, str]
    session_dependencies: dict[str, str | None]
    route_method: str | None
    route_path: str | None
    operations: list[SessionOperation]
    boundaries: list[TransactionBoundary]
    side_effects: list[SideEffectRecord]
    calls: list[tuple[str, int]]
    concurrent_session_uses: list[tuple[str, int, str]]
    confidence: float
    provenance: str = "static-analysis"


@dataclass
class ValidationIssue:
    code: str
    severity: str
    message: str
    source_file: str
    line: int
    function: str
    confidence: float
    provenance: str = "static-analysis"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


def session_type_from_annotation(annotation: str | None) -> str | None:
    if annotation is None:
        return None
    if "AsyncSession" in annotation:
        return "AsyncSession"
    if "Session" in annotation:
        return "Session"
    return None


def iter_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[ast.arg, ast.AST | None]]:
    positional_defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + list(node.args.defaults)
    parameters = list(zip(node.args.args, positional_defaults, strict=False))
    parameters.extend(zip(node.args.kwonlyargs, node.args.kw_defaults, strict=False))
    return parameters


def dependency_callable(default: ast.AST | None) -> str | None:
    if not isinstance(default, ast.Call):
        return None
    name = dotted_name(default.func)
    if name not in {"Depends", "fastapi.Depends", "Security", "fastapi.Security"}:
        return None
    return call_arg_name(default.args[0]) if default.args else None


def is_session_operation_call(call: ast.Call, session_names: set[str]) -> tuple[str, str] | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr not in SESSION_OPERATIONS:
        return None
    session_name = dotted_name(call.func.value)
    if session_name not in session_names:
        return None
    return session_name, call.func.attr


def target_model_from_call(call: ast.Call) -> str | None:
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Call):
        return dotted_name(arg.func)
    return dotted_name(arg)


def is_begin_context(expr: ast.AST, session_names: set[str]) -> tuple[str, str] | None:
    if not isinstance(expr, ast.Call):
        return None
    found = is_session_operation_call(expr, session_names)
    if found and found[1] == "begin":
        return found
    return None


def call_contains_session(node: ast.AST, session_names: set[str]) -> str | None:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in session_names:
            return child.id
    return None


def is_concurrent_call(call: ast.Call) -> str | None:
    name = dotted_name(call.func)
    if name in {"asyncio.gather", "gather", "asyncio.create_task", "create_task"}:
        return name
    return None


def is_side_effect_call(call: ast.Call, session_names: set[str]) -> bool:
    if is_session_operation_call(call, session_names):
        return False
    name = dotted_name(call.func)
    if not name:
        return False
    lowered = name.lower()
    return any(hint in lowered for hint in SIDE_EFFECT_HINTS)


class FunctionVisitor(ast.NodeVisitor):
    def __init__(self, analysis: FunctionAnalysis):
        self.analysis = analysis
        self.transaction_stack: list[tuple[int, str]] = []

    @property
    def session_names(self) -> set[str]:
        return set(self.analysis.session_params)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node, "with")

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node, "async with")

    def _visit_with(self, node: ast.With | ast.AsyncWith, context_kind: str) -> None:
        begin_contexts = [
            found
            for item in node.items
            if (found := is_begin_context(item.context_expr, self.session_names)) is not None
        ]
        for session_name, _operation in begin_contexts:
            session_type = self.analysis.session_params.get(session_name)
            self.analysis.operations.append(
                SessionOperation(
                    operation="begin",
                    session=session_name,
                    source_file=self.analysis.source_file,
                    line=getattr(node, "lineno", 0),
                    inside_transaction=True,
                    transaction_line=getattr(node, "lineno", 0),
                    function=self.analysis.name,
                    confidence=0.95,
                )
            )
            self.analysis.boundaries.append(
                TransactionBoundary(
                    function=self.analysis.name,
                    source_file=self.analysis.source_file,
                    line=getattr(node, "lineno", 0),
                    session=session_name,
                    session_type=session_type,
                    context_kind=context_kind,
                    pattern=f"{context_kind} {session_name}.begin()",
                    confidence=0.95,
                )
            )

        if begin_contexts:
            self.transaction_stack.append((getattr(node, "lineno", 0), context_kind))
            for statement in node.body:
                self.visit(statement)
            self.transaction_stack.pop()
            return

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        found = is_session_operation_call(node, self.session_names)
        if found:
            session_name, operation = found
            if operation != "begin":
                transaction_line = self.transaction_stack[-1][0] if self.transaction_stack else None
                self.analysis.operations.append(
                    SessionOperation(
                        operation=operation,
                        session=session_name,
                        source_file=self.analysis.source_file,
                        line=getattr(node, "lineno", 0),
                        inside_transaction=bool(self.transaction_stack),
                        transaction_line=transaction_line,
                        function=self.analysis.name,
                        target_model=target_model_from_call(node) if operation == "add" else None,
                        confidence=0.95,
                    )
                )

        concurrent_call = is_concurrent_call(node)
        if concurrent_call:
            session_name = call_contains_session(node, self.session_names)
            if session_name:
                self.analysis.concurrent_session_uses.append((concurrent_call, getattr(node, "lineno", 0), session_name))

        if self.transaction_stack and is_side_effect_call(node, self.session_names):
            self.analysis.side_effects.append(
                SideEffectRecord(
                    call=dotted_name(node.func) or "unknown",
                    source_file=self.analysis.source_file,
                    line=getattr(node, "lineno", 0),
                    function=self.analysis.name,
                    inside_transaction=True,
                    transaction_line=self.transaction_stack[-1][0],
                    confidence=0.85,
                )
            )

        called = dotted_name(node.func)
        if called:
            self.analysis.calls.append((called, getattr(node, "lineno", 0)))

        self.generic_visit(node)


def analyze_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    source_file: str,
    route_method: str | None,
    route_path: str | None,
) -> FunctionAnalysis:
    session_params: dict[str, str] = {}
    session_dependencies: dict[str, str | None] = {}
    for arg, default in iter_parameters(node):
        annotation = annotation_name(arg.annotation)
        session_type = session_type_from_annotation(annotation)
        if session_type:
            session_params[arg.arg] = session_type
            session_dependencies[arg.arg] = dependency_callable(default)

    analysis = FunctionAnalysis(
        name=node.name,
        source_file=source_file,
        line=getattr(node, "lineno", 0),
        is_async=isinstance(node, ast.AsyncFunctionDef),
        session_params=session_params,
        session_dependencies=session_dependencies,
        route_method=route_method,
        route_path=route_path,
        operations=[],
        boundaries=[],
        side_effects=[],
        calls=[],
        concurrent_session_uses=[],
        confidence=0.9 if session_params or route_method else 0.8,
    )
    FunctionVisitor(analysis).visit(node)
    return analysis


def analyze_file(file_path: Path, project_root: Path) -> list[FunctionAnalysis]:
    source_file = relative_path(file_path, project_root)
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=source_file)
    analyses: list[FunctionAnalysis] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_decorators = [
            route
            for decorator in node.decorator_list
            if (route := route_from_decorator(decorator)) is not None
        ]
        if route_decorators:
            for method, path, _line in route_decorators:
                analyses.append(analyze_function(node, source_file=source_file, route_method=method, route_path=path))
        else:
            analysis = analyze_function(node, source_file=source_file, route_method=None, route_path=None)
            if analysis.session_params or analysis.operations or analysis.boundaries:
                analyses.append(analysis)

    return analyses


def function_has_transaction_ownership(analysis: FunctionAnalysis) -> bool:
    return bool(analysis.boundaries) or any(operation.operation == "commit" for operation in analysis.operations)


def issue(
    code: str,
    severity: str,
    message: str,
    analysis: FunctionAnalysis,
    line: int | None = None,
    confidence: float = 0.9,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        message=message,
        source_file=analysis.source_file,
        line=line or analysis.line,
        function=analysis.name,
        confidence=confidence,
    )


def validate_analyses(analyses: list[FunctionAnalysis]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    by_name = {analysis.name: analysis for analysis in analyses}

    for analysis in analyses:
        path_parts = set(Path(analysis.source_file).parts)

        for operation in analysis.operations:
            if operation.operation == "commit" and {"services", "repositories"} & path_parts:
                issues.append(
                    issue(
                        "TX001",
                        "error",
                        "session.commit() found inside services/repositories; transaction ownership should remain at route/use-case boundary.",
                        analysis,
                        operation.line,
                    )
                )

        critical_writes = {
            operation.target_model
            for operation in analysis.operations
            if operation.operation == "add" and operation.target_model in CRITICAL_MODELS
        }
        if len(critical_writes) > 1 and not analysis.boundaries:
            issues.append(
                issue(
                    "TX002",
                    "error",
                    f"Multi-table critical writes without explicit transaction boundary: {sorted(critical_writes)}.",
                    analysis,
                )
            )

        for side_effect in analysis.side_effects:
            issues.append(
                issue(
                    "TX003",
                    "error",
                    f"Side-effect call inside transaction block: {side_effect.call}.",
                    analysis,
                    side_effect.line,
                    confidence=side_effect.confidence,
                )
            )

        sorted_operations = sorted(analysis.operations, key=lambda operation: operation.line)
        commit_lines = [operation.line for operation in sorted_operations if operation.operation == "commit"]
        if commit_lines:
            first_commit = min(commit_lines)
            later_writes = [
                operation
                for operation in sorted_operations
                if operation.line > first_commit and operation.operation in {"add", "delete", "execute", "flush"}
            ]
            if later_writes:
                issues.append(
                    issue(
                        "TX004",
                        "warning",
                        "Commit occurs before later database operations in the same function; manual review required.",
                        analysis,
                        first_commit,
                        confidence=0.8,
                    )
                )

        for called_name, line in analysis.calls:
            callee = by_name.get(called_name.split(".")[-1])
            if callee and function_has_transaction_ownership(analysis) and function_has_transaction_ownership(callee):
                issues.append(
                    issue(
                        "TX005",
                        "error",
                        f"Multiple transaction owners detected: {analysis.name} calls {callee.name}, and both own transaction boundaries.",
                        analysis,
                        line,
                    )
                )

        for session_name, session_type in analysis.session_params.items():
            if analysis.route_method and analysis.is_async and session_type == "Session":
                issues.append(
                    issue(
                        "TX006",
                        "error",
                        "Async route handler uses sync Session annotation.",
                        analysis,
                        confidence=0.95,
                    )
                )
            if analysis.route_method and not analysis.is_async and session_type == "AsyncSession":
                issues.append(
                    issue(
                        "TX006",
                        "error",
                        "Sync route handler uses AsyncSession annotation.",
                        analysis,
                        confidence=0.95,
                    )
                )

            for boundary in analysis.boundaries:
                if boundary.session != session_name:
                    continue
                if session_type == "AsyncSession" and boundary.context_kind != "async with":
                    issues.append(
                        issue(
                            "TX006",
                            "error",
                            "AsyncSession transaction uses sync with instead of async with.",
                            analysis,
                            boundary.line,
                        )
                    )
                if session_type == "Session" and boundary.context_kind != "with":
                    issues.append(
                        issue(
                            "TX006",
                            "error",
                            "Sync Session transaction uses async with instead of with.",
                            analysis,
                            boundary.line,
                        )
                    )

        for concurrent_call, line, session_name in analysis.concurrent_session_uses:
            session_type = analysis.session_params.get(session_name)
            if session_type == "AsyncSession":
                issues.append(
                    issue(
                        "TX007",
                        "error",
                        f"AsyncSession `{session_name}` is shared through concurrent call `{concurrent_call}`.",
                        analysis,
                        line,
                    )
                )

    return issues


def session_flow_record(analysis: FunctionAnalysis) -> dict[str, Any]:
    session_dependency = None
    session_type = None
    if analysis.session_params:
        first_session = next(iter(analysis.session_params))
        session_type = analysis.session_params[first_session]
        session_dependency = analysis.session_dependencies.get(first_session)

    transaction_pattern = None
    transaction_owner = None
    if analysis.boundaries:
        transaction_pattern = analysis.boundaries[0].pattern
        transaction_owner = f"{analysis.source_file}:{analysis.name}"
    elif any(operation.operation == "commit" for operation in analysis.operations):
        transaction_pattern = "commit"
        transaction_owner = f"{analysis.source_file}:{analysis.name}"

    risk = "low"
    if not analysis.session_params and analysis.route_method:
        risk = "unknown"
    if analysis.side_effects:
        risk = "high"

    return {
        "entrypoint": f"{analysis.route_method} {analysis.route_path}" if analysis.route_method else None,
        "handler": analysis.name,
        "source_file": analysis.source_file,
        "line": analysis.line,
        "is_async": analysis.is_async,
        "session_dependency": session_dependency,
        "session_type": session_type,
        "transaction_owner": transaction_owner,
        "transaction_pattern": transaction_pattern,
        "session_operations": [asdict(operation) for operation in analysis.operations],
        "commits_found": [asdict(operation) for operation in analysis.operations if operation.operation == "commit"],
        "flushes_found": [asdict(operation) for operation in analysis.operations if operation.operation == "flush"],
        "side_effects_inside_transaction": [asdict(effect) for effect in analysis.side_effects if effect.inside_transaction],
        "risk": risk,
        "confidence": analysis.confidence,
        "provenance": analysis.provenance,
    }


def generate_manifests(project_root: Path, output_dir: Path, roots: list[Path] | None = None) -> dict[str, Any]:
    generated_at = utc_now()
    files, warnings = discover_files(project_root, roots)
    analyses: list[FunctionAnalysis] = []
    for file_path in files:
        analyses.extend(analyze_file(file_path, project_root))

    issues = validate_analyses(analyses)
    digest = source_hash(files) if files else hashlib.sha256(b"").hexdigest()
    if not files:
        warnings.append("No Python backend files were scanned; transaction safety is not proven")

    has_errors = any(validation_issue.severity == "error" for validation_issue in issues)
    status = "failed" if has_errors else ("ok" if files else "needs_manual_review")
    risk = "high" if has_errors else ("low" if files else "unknown")
    confidence = 0.9 if files else 0.5

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
        "warnings": warnings,
    }
    session_flow = {
        **common,
        "scanner": "backend_day2_session_flow_transaction_boundary",
        "files_scanned": [relative_path(path, project_root) for path in files],
        "flows": [session_flow_record(analysis) for analysis in analyses if analysis.route_method or analysis.session_params],
    }
    transaction_boundaries = {
        **common,
        "transaction_boundaries": [asdict(boundary) for analysis in analyses for boundary in analysis.boundaries],
        "session_operations": [asdict(operation) for analysis in analyses for operation in analysis.operations],
        "validation": {
            "status": status,
            "errors": [asdict(validation_issue) for validation_issue in issues if validation_issue.severity == "error"],
            "warnings": [asdict(validation_issue) for validation_issue in issues if validation_issue.severity == "warning"],
            "rules_checked": ["TX001", "TX002", "TX003", "TX004", "TX005", "TX006", "TX007"],
        },
    }

    write_json(output_dir / "session-flow.json", session_flow)
    write_json(output_dir / "transaction-boundaries.json", transaction_boundaries)
    return {
        "session_flow": session_flow,
        "transaction_boundaries": transaction_boundaries,
    }


def get_session_flow(session_flow_manifest: dict[str, Any], entrypoint: str) -> dict[str, Any]:
    for flow in session_flow_manifest.get("flows", []):
        if flow.get("entrypoint") == entrypoint or flow.get("handler") == entrypoint:
            return {
                "status": "ok",
                "risk": flow.get("risk", "unknown"),
                "confidence": flow.get("confidence", 0.0),
                "flow": flow,
            }

    return {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": f"No session flow found for {entrypoint}",
    }


def validate_transaction_usage(transaction_boundaries_manifest: dict[str, Any]) -> dict[str, Any]:
    validation = transaction_boundaries_manifest.get("validation")
    if not validation:
        return {
            "status": "needs_manual_review",
            "risk": "unknown",
            "reason": "Manifest does not contain validation output",
        }
    return validation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Backend Day 2 session and transaction manifests.")
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
    validation = result["transaction_boundaries"]["validation"]
    print(
        stable_json(
            {
                "status": result["session_flow"]["status"],
                "risk": result["session_flow"]["risk"],
                "flows": len(result["session_flow"]["flows"]),
                "transaction_boundaries": len(result["transaction_boundaries"]["transaction_boundaries"]),
                "errors": len(validation["errors"]),
                "warnings": len(validation["warnings"]),
                "output": str(output_dir),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
