from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CONFIDENCE_THRESHOLD = 0.75
REQUIRED_BACKEND_MANIFESTS = ["routes.json", "transaction-boundaries.json"]


def uncertainty(reason: str, *, target: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": reason,
        "confidence": 0.0,
    }
    if target is not None:
        result["target"] = target
    if details:
        result["details"] = details
    return result


def resolve_project_root(project_root: str | Path | None = None) -> Path:
    if project_root is None:
        return Path(__file__).resolve().parents[1]
    path = Path(project_root)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[1] / path
    return path.resolve()


def resolve_inside_project(project_root: Path, path_value: str | Path) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Path is outside project root: {path}") from exc
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_confidence(manifest: dict[str, Any] | None) -> float:
    if not manifest:
        return 0.0
    try:
        return float(manifest.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def load_backend_manifests(manifest_dir: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    manifests: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if not manifest_dir.exists():
        return manifests, [f"Backend manifest directory does not exist: {manifest_dir}"]
    for name in REQUIRED_BACKEND_MANIFESTS:
        path = manifest_dir / name
        if not path.exists():
            warnings.append(f"Missing backend manifest: {name}")
            continue
        try:
            manifests[name] = read_json(path)
        except json.JSONDecodeError as exc:
            warnings.append(f"Invalid JSON in backend manifest {name}: {exc}")
    return manifests, warnings


def manifest_health(
    manifests: dict[str, dict[str, Any]],
    threshold: float,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    health: list[dict[str, Any]] = []
    blockers: list[str] = []
    for name in REQUIRED_BACKEND_MANIFESTS:
        manifest = manifests.get(name)
        confidence = manifest_confidence(manifest)
        if not manifest:
            blockers.append(f"Missing required backend manifest: {name}")
            health.append({"manifest": name, "status": "missing", "confidence": 0.0})
            continue
        status = manifest.get("status", "unknown")
        health.append(
            {
                "manifest": name,
                "status": status,
                "risk": manifest.get("risk"),
                "confidence": confidence,
                "source_hash": manifest.get("source_hash"),
                "scanner": manifest.get("scanner") or manifest.get("parser"),
            }
        )
        if status == "needs_manual_review":
            blockers.append(f"Manifest {name} requires manual review")
        if confidence < threshold:
            blockers.append(f"Manifest {name} confidence {confidence:.2f} is below {threshold:.2f}")
    return not blockers, health, blockers


def load_trace_fixture(path: Path, threshold: float) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path.exists():
        return None, uncertainty(f"Trace fixture not found: {path}")
    try:
        trace_manifest = read_json(path)
    except json.JSONDecodeError as exc:
        return None, uncertainty(f"Invalid trace fixture JSON: {exc}")
    status = trace_manifest.get("status", "unknown")
    confidence = manifest_confidence(trace_manifest)
    if status == "needs_manual_review" or confidence < threshold:
        return None, uncertainty(
            "Trace fixture evidence is incomplete or low confidence.",
            details={"status": status, "confidence": confidence, "trace_file": str(path)},
        )
    return trace_manifest, None


def route_id(route: dict[str, Any]) -> str:
    return f"{route.get('method')} {route.get('path')}"


def trace_route_id(trace: dict[str, Any]) -> str:
    return f"{trace.get('method')} {trace.get('path')}"


def exact_route_match(routes_manifest: dict[str, Any], target: str) -> dict[str, Any] | None:
    normalized = target.strip()
    for route in routes_manifest.get("routes", []):
        candidates = {
            route_id(route),
            str(route.get("path", "")),
            str(route.get("handler", "")),
        }
        if normalized in candidates:
            return route
    return None


def exact_trace_match(trace_manifest: dict[str, Any], route: dict[str, Any], target: str) -> dict[str, Any] | None:
    normalized = target.strip()
    expected_route = route_id(route)
    for trace in trace_manifest.get("traces", []):
        candidates = {
            trace_route_id(trace),
            str(trace.get("path", "")),
            str(trace.get("handler", "")),
            str(trace.get("trace_id", "")),
        }
        if normalized in candidates or expected_route in candidates:
            return trace
    return None


def event_models(trace: dict[str, Any]) -> list[str]:
    models: set[str] = set()
    for event in trace.get("events", []):
        model = event.get("model") or event.get("target_model")
        if model:
            models.add(str(model))
    return sorted(models)


def event_transaction_patterns(trace: dict[str, Any]) -> list[str]:
    patterns: set[str] = set()
    for event in trace.get("events", []):
        pattern = event.get("transaction_pattern")
        if pattern:
            patterns.add(str(pattern))
    return sorted(patterns)


def event_names(trace: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for event in trace.get("events", []):
        name = event.get("event") or event.get("type")
        if name:
            names.append(str(name))
    return names


def static_operations(tx_manifest: dict[str, Any], handler: str) -> list[dict[str, Any]]:
    return [
        operation
        for operation in tx_manifest.get("session_operations", [])
        if operation.get("function") == handler
    ]


def static_boundaries(tx_manifest: dict[str, Any], handler: str) -> list[dict[str, Any]]:
    return [
        boundary
        for boundary in tx_manifest.get("transaction_boundaries", [])
        if boundary.get("function") == handler
    ]


def tx_issues_for_handler(tx_manifest: dict[str, Any], handler: str) -> list[dict[str, Any]]:
    validation = tx_manifest.get("validation", {})
    issues = validation.get("errors", []) + validation.get("warnings", [])
    return [issue for issue in issues if issue.get("function") == handler]


def compare_trace_to_static(
    trace: dict[str, Any],
    operations: list[dict[str, Any]],
    boundaries: list[dict[str, Any]],
    tx_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    runtime_models = set(event_models(trace))
    static_models = {
        str(operation.get("target_model"))
        for operation in operations
        if operation.get("target_model")
    }
    runtime_patterns = set(event_transaction_patterns(trace))
    static_patterns = {
        str(boundary.get("pattern"))
        for boundary in boundaries
        if boundary.get("pattern")
    }
    signals: list[str] = []
    warnings: list[dict[str, Any]] = []
    risk = "low"

    missing_runtime_models = sorted(static_models - runtime_models)
    extra_runtime_models = sorted(runtime_models - static_models)
    if missing_runtime_models:
        risk = "medium"
        warnings.append(
            {
                "code": "VISION_MODEL_NOT_OBSERVED",
                "message": f"Static model operations were not observed in trace: {', '.join(missing_runtime_models)}.",
                "severity": "warning",
            }
        )
    if extra_runtime_models:
        risk = "medium"
        warnings.append(
            {
                "code": "VISION_RUNTIME_MODEL_UNLINKED",
                "message": f"Runtime trace observed models not present in static manifest: {', '.join(extra_runtime_models)}.",
                "severity": "warning",
            }
        )
    if static_patterns and not runtime_patterns.intersection(static_patterns):
        risk = "high"
        warnings.append(
            {
                "code": "VISION_TRANSACTION_PATTERN_MISMATCH",
                "message": "Runtime transaction pattern did not match static transaction boundary manifest.",
                "severity": "error",
            }
        )
    if tx_issues:
        risk = "high"
        codes = sorted({str(issue.get("code")) for issue in tx_issues if issue.get("code")})
        warnings.append(
            {
                "code": "VISION_STATIC_TX_ISSUES",
                "message": f"Static transaction validator issues apply to this handler: {', '.join(codes)}.",
                "severity": "error",
            }
        )
    if not warnings:
        signals.append("Runtime trace events match manifest-backed route and transaction evidence.")

    return {
        "risk": risk,
        "signals": signals,
        "warnings": warnings,
        "runtime_models": sorted(runtime_models),
        "static_models": sorted(static_models),
        "runtime_transaction_patterns": sorted(runtime_patterns),
        "static_transaction_patterns": sorted(static_patterns),
    }


def trace_route(
    target: str,
    *,
    project_root: str | Path | None = None,
    backend_manifest_dir: str | Path = ".backend-ai",
    trace_file: str | Path = ".agent_bus/traces/omni-vision.json",
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    try:
        manifest_dir = resolve_inside_project(root, backend_manifest_dir)
        trace_path = resolve_inside_project(root, trace_file)
    except ValueError as exc:
        return uncertainty(str(exc), target=target)

    manifests, manifest_warnings = load_backend_manifests(manifest_dir)
    healthy, health, blockers = manifest_health(manifests, confidence_threshold)
    if not healthy:
        return uncertainty(
            "Backend manifest evidence is incomplete or low confidence.",
            target=target,
            details={"blockers": blockers, "warnings": manifest_warnings, "manifests": health},
        )

    trace_manifest, trace_error = load_trace_fixture(trace_path, confidence_threshold)
    if trace_error:
        trace_error["target"] = target
        return trace_error
    assert trace_manifest is not None

    route = exact_route_match(manifests["routes.json"], target)
    if not route:
        return uncertainty(
            "No exact backend route match for target.",
            target=target,
            details={"backend_manifest_dir": str(manifest_dir)},
        )

    trace = exact_trace_match(trace_manifest, route, target)
    if not trace:
        return uncertainty(
            "No trace fixture matches the manifest-backed route.",
            target=target,
            details={"route": route_id(route), "trace_file": str(trace_path)},
        )

    handler = str(route.get("handler", ""))
    tx_manifest = manifests["transaction-boundaries.json"]
    operations = static_operations(tx_manifest, handler)
    boundaries = static_boundaries(tx_manifest, handler)
    tx_issues = tx_issues_for_handler(tx_manifest, handler)
    comparison = compare_trace_to_static(trace, operations, boundaries, tx_issues)
    route_confidence = float(route.get("confidence", 0.0))
    trace_confidence = float(trace.get("confidence", trace_manifest.get("confidence", 0.0)))
    confidence = min(
        manifest_confidence(manifests["routes.json"]),
        manifest_confidence(tx_manifest),
        manifest_confidence(trace_manifest),
        route_confidence,
        trace_confidence,
    )

    return {
        "status": "ok",
        "risk": comparison["risk"],
        "target": {
            "requested": target,
            "route": route_id(route),
            "handler": handler,
            "trace_id": trace.get("trace_id"),
        },
        "trace": {
            "trace_id": trace.get("trace_id"),
            "method": trace.get("method"),
            "path": trace.get("path"),
            "status_code": trace.get("status_code"),
            "duration_ms": trace.get("duration_ms"),
            "events": trace.get("events", []),
            "event_names": event_names(trace),
        },
        "manifest_links": {
            "route": route,
            "transaction_boundaries": boundaries,
            "session_operations": operations,
            "transaction_issues": tx_issues,
            "manifests": health,
        },
        "runtime_summary": comparison,
        "confidence": round(confidence, 4),
        "provenance": "runtime-introspection",
        "trace_file": str(trace_path),
        "backend_manifest_dir": str(manifest_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Link an Omni-Vision trace fixture to backend manifests.")
    parser.add_argument("target")
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--backend-manifest-dir", default=".backend-ai")
    parser.add_argument("--trace-file", default=".agent_bus/traces/omni-vision.json")
    args = parser.parse_args()
    result = trace_route(
        args.target,
        project_root=args.project_root,
        backend_manifest_dir=args.backend_manifest_dir,
        trace_file=args.trace_file,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
