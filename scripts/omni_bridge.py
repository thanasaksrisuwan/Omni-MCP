from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CONFIDENCE_THRESHOLD = 0.75

FRONTEND_REQUIRED = [
    "components.json",
    "props.json",
    "usages.json",
    "tokens.json",
    "assets.json",
    "layouts.json",
]

BACKEND_REQUIRED = [
    "routes.json",
    "dependencies.json",
    "session-flow.json",
    "transaction-boundaries.json",
    "validation-rules.json",
]


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


def resolve_manifest_dir(project_root: Path, manifest_dir: str | Path) -> Path:
    path = Path(manifest_dir)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Manifest directory is outside project root: {path}") from exc
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifests(manifest_dir: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    manifests: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    if not manifest_dir.exists():
        return manifests, [f"Manifest directory does not exist: {manifest_dir}"]
    for path in sorted(manifest_dir.glob("*.json")):
        try:
            data = read_json(path)
        except json.JSONDecodeError as exc:
            warnings.append(f"Invalid JSON in {path.name}: {exc}")
            continue
        manifests[path.name] = data
    return manifests, warnings


def manifest_confidence(manifest: dict[str, Any] | None) -> float:
    if not manifest:
        return 0.0
    try:
        return float(manifest.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def manifest_health(
    manifests: dict[str, dict[str, Any]],
    required_names: list[str],
    threshold: float,
) -> tuple[bool, list[dict[str, Any]], list[str]]:
    health: list[dict[str, Any]] = []
    blockers: list[str] = []
    for name in required_names:
        manifest = manifests.get(name)
        if manifest is None:
            blockers.append(f"Missing required manifest: {name}")
            health.append({"manifest": name, "status": "missing", "confidence": 0.0})
            continue
        status = manifest.get("status", "unknown")
        confidence = manifest_confidence(manifest)
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


def exact_component_match(components_manifest: dict[str, Any], target: str) -> dict[str, Any] | None:
    for component in components_manifest.get("components", []):
        candidates = {
            str(component.get("component_id", "")),
            str(component.get("name", "")),
            str(component.get("import_path", "")),
        }
        if target in candidates:
            return component
    return None


def exact_route_match(routes_manifest: dict[str, Any], target: str) -> dict[str, Any] | None:
    normalized = target.strip()
    for route in routes_manifest.get("routes", []):
        route_id = f"{route.get('method')} {route.get('path')}"
        candidates = {
            route_id,
            str(route.get("path", "")),
            str(route.get("handler", "")),
        }
        if normalized in candidates:
            return route
    return None


def add_related_file(files: list[dict[str, Any]], path: str | None, reason: str, evidence: dict[str, Any]) -> None:
    if not path:
        return
    entry = {
        "path": path,
        "reason": reason,
        "line": evidence.get("line"),
        "provenance": evidence.get("provenance"),
        "confidence": evidence.get("confidence"),
    }
    if entry not in files:
        files.append(entry)


def risk_rank(risk: str) -> int:
    return {"unknown": 0, "low": 1, "medium": 2, "high": 3}.get(risk, 0)


def higher_risk(current: str, candidate: str) -> str:
    return candidate if risk_rank(candidate) > risk_rank(current) else current


def summarize_frontend_impact(
    component: dict[str, Any],
    usages: list[dict[str, Any]],
    manifest_health_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    risk = "low"
    signals: list[str] = []
    if component.get("status") == "deprecated":
        risk = "high"
        signals.append("Component manifest marks this component as deprecated.")
    if not usages:
        risk = higher_risk(risk, "medium")
        signals.append("No usage examples were found in the usage manifest.")
    for entry in manifest_health_entries:
        if entry.get("risk") == "high":
            risk = "high"
            signals.append(f"Manifest {entry.get('manifest')} reports high risk.")
    if not signals:
        signals.append("Component, props, usages, tokens, assets, and layout manifests are present with sufficient confidence.")
    return {"risk": risk, "signals": signals}


def summarize_backend_impact(
    route: dict[str, Any],
    dependencies: list[dict[str, Any]],
    flow: dict[str, Any],
    tx_issues: list[dict[str, Any]],
    critical_models: list[str],
) -> dict[str, Any]:
    risk = "low"
    signals: list[str] = []
    method = str(route.get("method", ""))
    if method in {"POST", "PUT", "PATCH", "DELETE"}:
        risk = higher_risk(risk, "medium")
        signals.append(f"{method} route can mutate data.")

    protected = any(dep.get("kind") == "Security" or dep.get("scopes") for dep in dependencies)
    protected = protected or any(
        "current_user" in str(dep.get("callable", "")) or "auth" in str(dep.get("callable", "")).lower()
        for dep in dependencies
    )
    if method in {"POST", "PUT", "PATCH", "DELETE"} and not protected:
        risk = "high"
        signals.append("Mutating route has no detected auth dependency or security scope.")

    touched_models = sorted(
        {
            str(operation.get("target_model"))
            for operation in flow.get("session_operations", [])
            if operation.get("target_model")
        }
    )
    critical_touches = [model for model in touched_models if model in critical_models]
    if critical_touches:
        risk = higher_risk(risk, "medium")
        signals.append(f"Route touches critical models: {', '.join(critical_touches)}.")
    if tx_issues:
        risk = "high"
        codes = sorted({str(issue.get("code")) for issue in tx_issues if issue.get("code")})
        signals.append(f"Transaction validator issues apply to this handler: {', '.join(codes)}.")
    if not flow.get("transaction_pattern") and len(critical_touches) > 1:
        risk = "high"
        signals.append("Multiple critical model writes have no proven transaction pattern.")
    if not signals:
        signals.append("Route, dependencies, session flow, transaction boundaries, and validation rules are present.")
    return {
        "risk": risk,
        "signals": signals,
        "touched_models": touched_models,
        "critical_models_touched": critical_touches,
    }


def pack_frontend_component(
    target: str,
    manifests: dict[str, dict[str, Any]],
    manifest_dir: Path,
    threshold: float,
    require_match: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    components_manifest = manifests.get("components.json")
    if not components_manifest:
        return (uncertainty("Missing required manifest: components.json", target=target), []) if require_match else (None, ["frontend components manifest missing"])

    if require_match:
        healthy, health, blockers = manifest_health(manifests, FRONTEND_REQUIRED, threshold)
        if not healthy:
            return uncertainty("Frontend manifest evidence is incomplete or low confidence.", target=target, details={"blockers": blockers, "manifests": health}), []

    component = exact_component_match(components_manifest, target)
    if not component:
        reason = f"No exact frontend component match for target: {target}"
        return (uncertainty(reason, target=target), []) if require_match else (None, [reason])

    healthy, health, blockers = manifest_health(manifests, FRONTEND_REQUIRED, threshold)
    if not healthy:
        return uncertainty("Frontend manifest evidence is incomplete or low confidence.", target=target, details={"blockers": blockers, "manifests": health}), []

    component_id = component.get("component_id")
    props_manifest = manifests["props.json"]
    usages_manifest = manifests["usages.json"]
    props = props_manifest.get("props", {}).get(component_id)
    if not props:
        return uncertainty(
            "Component prop relationship cannot be proven from props.json.",
            target=target,
            details={"component_id": component_id},
        ), []

    usages = [
        usage for usage in usages_manifest.get("usages", []) if usage.get("component_id") == component_id
    ]
    related_files: list[dict[str, Any]] = []
    add_related_file(related_files, component.get("source_file"), "component definition", component)
    for usage in usages:
        add_related_file(related_files, usage.get("file"), "component usage", usage)

    layout_patterns = []
    usage_files = {usage.get("file") for usage in usages}
    for pattern in manifests["layouts.json"].get("patterns", []):
        examples = set(pattern.get("examples", []))
        if examples & usage_files:
            layout_patterns.append(pattern)

    impact = summarize_frontend_impact(component, usages, health)
    confidence = min(
        [manifest_confidence(manifests[name]) for name in FRONTEND_REQUIRED] + [manifest_confidence({"confidence": component.get("confidence", 0.0)})]
    )
    return {
        "status": "ok",
        "risk": impact["risk"],
        "target": {
            "type": "frontend_component",
            "requested": target,
            "component_id": component_id,
        },
        "context": {
            "component": component,
            "props": props,
            "usages": usages,
            "layout_patterns": layout_patterns,
            "tokens": {
                "summary": "Design token manifest is available; use project tokens rather than arbitrary styles.",
                "classes": manifests["tokens.json"].get("tokens", {}).get("classes", []),
            },
            "assets": {
                "summary": "Asset/icon manifest is available; use listed assets only.",
                "count": len(manifests["assets.json"].get("assets", [])),
            },
            "related_files": related_files,
            "manifests": health,
            "manifest_dir": str(manifest_dir),
        },
        "impact": impact,
        "confidence": round(confidence, 4),
        "provenance": "manifest",
    }, []


def tx_validation_issues_for_handler(tx_manifest: dict[str, Any], handler: str) -> list[dict[str, Any]]:
    validation = tx_manifest.get("validation", {})
    issues = validation.get("errors", []) + validation.get("warnings", [])
    return [issue for issue in issues if issue.get("function") == handler]


def pack_backend_route(
    target: str,
    manifests: dict[str, dict[str, Any]],
    manifest_dir: Path,
    threshold: float,
    require_match: bool,
) -> tuple[dict[str, Any] | None, list[str]]:
    routes_manifest = manifests.get("routes.json")
    if not routes_manifest:
        return (uncertainty("Missing required manifest: routes.json", target=target), []) if require_match else (None, ["backend routes manifest missing"])

    if require_match:
        healthy, health, blockers = manifest_health(manifests, BACKEND_REQUIRED, threshold)
        if not healthy:
            return uncertainty("Backend manifest evidence is incomplete or low confidence.", target=target, details={"blockers": blockers, "manifests": health}), []

    route = exact_route_match(routes_manifest, target)
    if not route:
        reason = f"No exact backend route match for target: {target}"
        return (uncertainty(reason, target=target), []) if require_match else (None, [reason])

    healthy, health, blockers = manifest_health(manifests, BACKEND_REQUIRED, threshold)
    if not healthy:
        return uncertainty("Backend manifest evidence is incomplete or low confidence.", target=target, details={"blockers": blockers, "manifests": health}), []

    route_id = f"{route.get('method')} {route.get('path')}"
    handler = str(route.get("handler", ""))
    dependencies = [
        dependency
        for dependency in manifests["dependencies.json"].get("dependencies", [])
        if dependency.get("route_method") == route.get("method") and dependency.get("route_path") == route.get("path")
    ]
    flows = manifests["session-flow.json"].get("flows", [])
    flow = next((item for item in flows if item.get("entrypoint") == route_id or item.get("handler") == handler), None)
    if flow is None:
        return uncertainty(
            "Route session flow relationship cannot be proven from session-flow.json.",
            target=target,
            details={"route": route_id, "handler": handler},
        ), []

    tx_manifest = manifests["transaction-boundaries.json"]
    tx_boundaries = [
        boundary for boundary in tx_manifest.get("transaction_boundaries", []) if boundary.get("function") == handler
    ]
    tx_operations = [
        operation for operation in tx_manifest.get("session_operations", []) if operation.get("function") == handler
    ]
    tx_issues = tx_validation_issues_for_handler(tx_manifest, handler)
    validation_rules = manifests["validation-rules.json"]
    critical_models = [str(model) for model in validation_rules.get("critical_models", [])]

    related_files: list[dict[str, Any]] = []
    add_related_file(related_files, route.get("source_file"), "route handler", route)
    for dependency in dependencies:
        add_related_file(related_files, dependency.get("source_file"), "route dependency", dependency)
    add_related_file(related_files, flow.get("source_file"), "session flow", flow)
    for issue in tx_issues:
        add_related_file(related_files, issue.get("source_file"), "transaction validation issue", issue)

    impact = summarize_backend_impact(route, dependencies, flow, tx_issues, critical_models)
    confidence = min([manifest_confidence(manifests[name]) for name in BACKEND_REQUIRED] + [float(route.get("confidence", 0.0)), float(flow.get("confidence", 0.0))])
    return {
        "status": "ok",
        "risk": impact["risk"],
        "target": {
            "type": "backend_route",
            "requested": target,
            "route": route_id,
            "handler": handler,
        },
        "context": {
            "route": route,
            "dependencies": dependencies,
            "session_flow": flow,
            "transaction_boundaries": tx_boundaries,
            "session_operations": tx_operations,
            "transaction_issues": tx_issues,
            "validation_rules": {
                "critical_models": critical_models,
                "critical_tables": validation_rules.get("critical_tables", []),
                "confidence_threshold": validation_rules.get("confidence_threshold", threshold),
            },
            "related_files": related_files,
            "manifests": health,
            "manifest_dir": str(manifest_dir),
        },
        "impact": impact,
        "confidence": round(confidence, 4),
        "provenance": "manifest",
    }, []


def bridge_pack_context(
    target: str,
    target_type: str = "auto",
    project_root: str | Path | None = None,
    frontend_manifest_dir: str | Path = ".frontend-ai",
    backend_manifest_dir: str | Path = ".backend-ai",
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    frontend_dir = resolve_manifest_dir(root, frontend_manifest_dir)
    backend_dir = resolve_manifest_dir(root, backend_manifest_dir)
    frontend_manifests, frontend_warnings = load_manifests(frontend_dir)
    backend_manifests, backend_warnings = load_manifests(backend_dir)

    target_type = target_type.lower().strip()
    if target_type not in {"auto", "frontend_component", "backend_route"}:
        return uncertainty(
            "Unsupported target_type. Use auto, frontend_component, or backend_route.",
            target=target,
            details={"target_type": target_type},
        )

    misses: list[str] = []
    if target_type in {"auto", "frontend_component"}:
        result, reasons = pack_frontend_component(
            target,
            frontend_manifests,
            frontend_dir,
            confidence_threshold,
            require_match=target_type == "frontend_component",
        )
        if result is not None:
            if result.get("status") == "ok" or target_type == "frontend_component":
                if frontend_warnings:
                    result.setdefault("warnings", []).extend(frontend_warnings)
                return result
        misses.extend(reasons)

    if target_type in {"auto", "backend_route"}:
        result, reasons = pack_backend_route(
            target,
            backend_manifests,
            backend_dir,
            confidence_threshold,
            require_match=target_type == "backend_route",
        )
        if result is not None:
            if result.get("status") == "ok" or target_type == "backend_route":
                if backend_warnings:
                    result.setdefault("warnings", []).extend(backend_warnings)
                return result
        misses.extend(reasons)

    warnings = frontend_warnings + backend_warnings
    return uncertainty(
        "No exact manifest-backed target match was found.",
        target=target,
        details={
            "misses": misses,
            "warnings": warnings,
            "frontend_manifest_dir": str(frontend_dir),
            "backend_manifest_dir": str(backend_dir),
        },
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pack read-only Omni-Bridge context from manifests.")
    parser.add_argument("target")
    parser.add_argument("--target-type", default="auto", choices=["auto", "frontend_component", "backend_route"])
    parser.add_argument("--project-root", default=None)
    parser.add_argument("--frontend-manifest-dir", default=".frontend-ai")
    parser.add_argument("--backend-manifest-dir", default=".backend-ai")
    args = parser.parse_args()
    result = bridge_pack_context(
        args.target,
        target_type=args.target_type,
        project_root=args.project_root,
        frontend_manifest_dir=args.frontend_manifest_dir,
        backend_manifest_dir=args.backend_manifest_dir,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
