from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import backend_reservation_safety, backend_scanner, backend_session_scanner, frontend_scanner, omni_bridge, omni_scribe


ALLOWED_OUTPUT_DIRS = {".frontend-ai", ".backend-ai", ".agent_bus"}


def uncertainty(reason: str) -> dict[str, Any]:
    return {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": reason,
        "confidence": 0.0,
    }


def resolve_project_root(project_root: str | None = None) -> Path:
    if not project_root:
        return PROJECT_ROOT
    path = Path(project_root)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def resolve_roots(project_root: Path, roots: list[str] | None = None) -> list[Path] | None:
    if not roots:
        return None
    resolved: list[Path] = []
    for root in roots:
        path = Path(root)
        if not path.is_absolute():
            path = project_root / path
        resolved.append(path.resolve())
    return resolved


def resolve_output_dir(project_root: Path, output: str) -> Path:
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = project_root / output_path
    output_path = output_path.resolve()

    try:
        relative = output_path.relative_to(project_root)
    except ValueError as exc:
        raise ValueError(f"Output directory is outside project root: {output_path}") from exc

    if not relative.parts or relative.parts[0] not in ALLOWED_OUTPUT_DIRS:
        allowed = ", ".join(sorted(ALLOWED_OUTPUT_DIRS))
        raise ValueError(f"Output directory must be under one of: {allowed}")

    return output_path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_call(callback: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return callback()
    except ValueError as exc:
        return uncertainty(str(exc))
    except FileNotFoundError as exc:
        return uncertainty(f"File not found: {exc.filename}")


def backend_index_project(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        output_dir = resolve_output_dir(root, output)
        return backend_scanner.generate_manifests(root, output_dir, resolve_roots(root, roots))

    return safe_call(run)


def backend_get_session_flow(
    entrypoint: str,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        output_dir = resolve_output_dir(root, output)
        manifests = backend_session_scanner.generate_manifests(root, output_dir, resolve_roots(root, roots))
        flow = backend_session_scanner.get_session_flow(manifests["session_flow"], entrypoint)
        return {"manifest_status": manifests["session_flow"].get("status"), **flow}

    return safe_call(run)


def backend_validate_transaction_usage(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        output_dir = resolve_output_dir(root, output)
        manifests = backend_session_scanner.generate_manifests(root, output_dir, resolve_roots(root, roots))
        validation = backend_session_scanner.validate_transaction_usage(manifests["transaction_boundaries"])
        return {"manifest_status": manifests["transaction_boundaries"].get("status"), **validation}

    return safe_call(run)


def authorization_map_from_manifests(routes_manifest: dict[str, Any], dependencies_manifest: dict[str, Any]) -> dict[str, Any]:
    dependencies_by_route: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for dependency in dependencies_manifest.get("dependencies", []):
        key = (dependency.get("route_method"), dependency.get("route_path"))
        dependencies_by_route.setdefault(key, []).append(dependency)

    routes: list[dict[str, Any]] = []
    for route in routes_manifest.get("routes", []):
        key = (route.get("method"), route.get("path"))
        dependencies = dependencies_by_route.get(key, [])
        security = [
            {
                "type": "scope" if dependency.get("scopes") else dependency.get("kind", "dependency"),
                "value": dependency.get("scopes") or dependency.get("callable"),
                "callable": dependency.get("callable"),
            }
            for dependency in dependencies
            if dependency.get("kind") == "Security" or dependency.get("scopes")
        ]
        protected = bool(security) or any(
            "current_user" in str(dependency.get("callable", "")) or "auth" in str(dependency.get("callable", "")).lower()
            for dependency in dependencies
        )
        routes.append(
            {
                "route": f"{route.get('method')} {route.get('path')}",
                "handler": route.get("handler"),
                "dependencies": [dependency.get("callable") for dependency in dependencies],
                "security": security,
                "authorization_status": "protected" if protected else "unprotected",
                "confidence": min(
                    [route.get("confidence", 0.0), dependencies_manifest.get("confidence", 0.0)] or [0.0]
                ),
            }
        )

    status = routes_manifest.get("status")
    risk = routes_manifest.get("risk")
    if status != "ok":
        status = "needs_manual_review"
        risk = "unknown"

    return {
        "status": status,
        "risk": risk,
        "routes": routes,
        "confidence": routes_manifest.get("confidence", 0.0),
        "provenance": "backend-route-dependency-manifests",
    }


def backend_get_authorization_map(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        output_dir = resolve_output_dir(root, output)
        manifests = backend_scanner.generate_manifests(root, output_dir, resolve_roots(root, roots))
        return authorization_map_from_manifests(manifests["routes"], manifests["dependencies"])

    return safe_call(run)


def backend_validate_authorization(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        auth_map = backend_get_authorization_map(project_root, roots, output)
        if auth_map.get("status") != "ok":
            return auth_map
        errors = []
        for route in auth_map.get("routes", []):
            method = str(route.get("route", "")).split(" ", 1)[0]
            if method in {"POST", "PUT", "PATCH", "DELETE"} and route.get("authorization_status") != "protected":
                errors.append(
                    {
                        "code": "AUTH001",
                        "severity": "error",
                        "route": route.get("route"),
                        "message": "Mutating route is not protected by detected auth dependency or security scope.",
                        "confidence": route.get("confidence", 0.0),
                    }
                )
        return {
            "status": "failed" if errors else "ok",
            "risk": "high" if errors else "low",
            "errors": errors,
            "warnings": [],
            "rules_checked": ["AUTH001"],
            "confidence": auth_map.get("confidence", 0.0),
        }

    return safe_call(run)


def backend_reservation_manifests(project_root: str, roots: list[str] | None, output: str) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    output_dir = resolve_output_dir(root, output)
    return backend_reservation_safety.generate_manifests(root, output_dir, resolve_roots(root, roots))


def backend_get_state_machine(
    name: str = "reservation",
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = backend_reservation_manifests(project_root, roots, output)
        return backend_reservation_safety.get_state_machine(manifests["state_machines"], name)

    return safe_call(run)


def backend_validate_state_transition(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = backend_reservation_manifests(project_root, roots, output)
        return backend_reservation_safety.validate_state_transition(manifests["state_machines"])

    return safe_call(run)


def backend_validate_idempotency(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = backend_reservation_manifests(project_root, roots, output)
        return backend_reservation_safety.validate_idempotency(manifests["outbox_events"])

    return safe_call(run)


def backend_validate_outbox_usage(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = backend_reservation_manifests(project_root, roots, output)
        return backend_reservation_safety.validate_outbox_usage(manifests["outbox_events"])

    return safe_call(run)


def backend_validate_reservation_invariants(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = backend_reservation_manifests(project_root, roots, output)
        return backend_reservation_safety.validate_reservation_invariants(manifests["invariants"])

    return safe_call(run)


def frontend_index_project(
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        output_dir = resolve_output_dir(root, output)
        return frontend_scanner.index_project(root, output_dir, resolve_roots(root, roots))

    return safe_call(run)


def frontend_manifests(project_root: str, roots: list[str] | None, output: str) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    output_dir = resolve_output_dir(root, output)
    return frontend_scanner.index_project(root, output_dir, resolve_roots(root, roots))


def frontend_search_components(
    intent: str,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
    limit: int = 5,
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        if manifests["index_meta"].get("status") != "ok":
            return uncertainty("No frontend source manifest is available for component search.")
        return frontend_scanner.search_components(manifests["components"], intent, limit)

    return safe_call(run)


def frontend_get_prop_signature(
    component_id: str,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        if manifests["index_meta"].get("status") != "ok":
            return uncertainty("No frontend source manifest is available for prop lookup.")
        return frontend_scanner.get_prop_signature(manifests["props"], component_id)

    return safe_call(run)


def frontend_find_component_usages(
    component_id: str,
    context: str | None = None,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
    limit: int = 5,
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        if manifests["index_meta"].get("status") != "ok":
            return uncertainty("No frontend source manifest is available for usage lookup.")
        return frontend_scanner.find_component_usages(manifests["usages"], component_id, context, limit)

    return safe_call(run)


def frontend_get_design_tokens(
    groups: list[str] | None = None,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        tokens_manifest = manifests["tokens"]
        if tokens_manifest.get("status") != "ok":
            return uncertainty("No frontend source manifest is available for design token lookup.")
        return {
            "status": "ok",
            "tokens": tokens_manifest.get("tokens", {}),
            "requested_groups": groups or [],
            "confidence": tokens_manifest.get("confidence", 0.0),
            "provenance": tokens_manifest.get("scanner", "frontend_design_tokens"),
        }

    return safe_call(run)


def frontend_list_assets(
    query: str | None = None,
    kind: str | None = None,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
    limit: int = 10,
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        assets_manifest = manifests["assets"]
        if assets_manifest.get("status") != "ok":
            return uncertainty("No frontend source manifest is available for asset lookup.")
        query_terms = {term for term in (query or "").lower().replace("-", " ").split() if term}
        results = []
        for asset in assets_manifest.get("assets", []):
            if kind and asset.get("kind") != kind:
                continue
            haystack = " ".join([asset.get("name", ""), asset.get("kind", ""), *asset.get("aliases", [])]).lower()
            if query_terms and not any(term in haystack for term in query_terms):
                continue
            results.append(asset)
        return {
            "status": "ok",
            "assets": results[:limit],
            "confidence": assets_manifest.get("confidence", 0.0),
            "provenance": assets_manifest.get("scanner", "frontend_asset_icon_catalog"),
        }

    return safe_call(run)


def frontend_get_layout_patterns(
    intent: str | None = None,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
    limit: int = 5,
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        manifests = frontend_manifests(project_root, roots, output)
        if manifests["index_meta"].get("status") != "ok":
            return uncertainty("No frontend source manifest is available for layout lookup.")
        return frontend_scanner.get_layout_patterns(manifests["layouts"], intent, limit)

    return safe_call(run)


def frontend_validate_ui_code(
    file_path: str,
    project_root: str = ".",
    roots: list[str] | None = None,
    output: str = ".frontend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        root = resolve_project_root(project_root)
        target = Path(file_path)
        if not target.is_absolute():
            target = root / target
        target = target.resolve()
        manifests = frontend_manifests(project_root, roots, output)
        if manifests["index_meta"].get("status") != "ok":
            return uncertainty("No frontend source manifest is available for UI validation.")
        return frontend_scanner.validate_ui_code(
            target,
            root,
            manifests["components"],
            manifests["props"],
            manifests["tokens"],
            manifests["assets"],
        )

    return safe_call(run)


def omni_bridge_pack_context(
    target: str,
    target_type: str = "auto",
    project_root: str = ".",
    frontend_manifest_dir: str = ".frontend-ai",
    backend_manifest_dir: str = ".backend-ai",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        return omni_bridge.bridge_pack_context(
            target,
            target_type=target_type,
            project_root=resolve_project_root(project_root),
            frontend_manifest_dir=frontend_manifest_dir,
            backend_manifest_dir=backend_manifest_dir,
        )

    return safe_call(run)


def omni_scribe_plan_write(
    target_file_path: str,
    proposed_content: str,
    project_root: str = ".",
    frontend_roots: list[str] | None = None,
    backend_roots: list[str] | None = None,
    artifact_dir: str = ".agent_bus/scribes",
) -> dict[str, Any]:
    def run() -> dict[str, Any]:
        return omni_scribe.plan_write(
            target_file_path,
            proposed_content,
            project_root=resolve_project_root(project_root),
            frontend_roots=frontend_roots,
            backend_roots=backend_roots,
            artifact_dir=artifact_dir,
        )

    return safe_call(run)


TOOL_SPECS: list[tuple[str, Callable[..., dict[str, Any]], str]] = [
    ("backend.get_session_flow", backend_get_session_flow, "Return session flow details for a backend entrypoint."),
    ("backend.validate_transaction_usage", backend_validate_transaction_usage, "Validate backend transaction usage."),
    ("backend.get_authorization_map", backend_get_authorization_map, "Build backend authorization map."),
    ("backend.validate_authorization", backend_validate_authorization, "Validate mutating route authorization."),
    ("backend.validate_idempotency", backend_validate_idempotency, "Validate critical flow idempotency."),
    ("backend.get_state_machine", backend_get_state_machine, "Return reservation state machine data."),
    ("backend.validate_state_transition", backend_validate_state_transition, "Validate reservation state transitions."),
    (
        "backend.validate_reservation_invariants",
        backend_validate_reservation_invariants,
        "Validate reservation invariants.",
    ),
    ("backend.validate_outbox_usage", backend_validate_outbox_usage, "Validate critical side-effect outbox usage."),
    ("frontend.index_project", frontend_index_project, "Generate frontend component manifests."),
    ("frontend.search_components", frontend_search_components, "Search frontend components by intent."),
    ("frontend.get_prop_signature", frontend_get_prop_signature, "Return component prop signature."),
    ("frontend.find_component_usages", frontend_find_component_usages, "Find component usage examples."),
    ("frontend.get_design_tokens", frontend_get_design_tokens, "Return discovered design tokens."),
    ("frontend.list_assets", frontend_list_assets, "Return discovered frontend assets and icons."),
    ("frontend.get_layout_patterns", frontend_get_layout_patterns, "Return frontend layout patterns."),
    ("frontend.validate_ui_code", frontend_validate_ui_code, "Validate UI code against manifests."),
    ("omni.bridge_pack_context", omni_bridge_pack_context, "Pack read-only context from generated manifests."),
    ("omni.scribe_plan_write", omni_scribe_plan_write, "Plan a validation-locked write without touching target files."),
]

EXPECTED_TOOL_NAMES = [name for name, _handler, _description in TOOL_SPECS]


def create_server() -> FastMCP:
    server = FastMCP(
        "omni-mcp",
        instructions=(
            "Safety-first frontend/backend analysis tools. Tools are read-only against source and write generated "
            "manifests only under .frontend-ai, .backend-ai, or .agent_bus."
        ),
    )
    for name, handler, description in TOOL_SPECS:
        server.tool(name=name, description=description, structured_output=True)(handler)
    return server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Omni-MCP server.")
    parser.add_argument("--transport", choices=["stdio", "sse", "streamable-http"], default="stdio")
    parser.add_argument("--list-tools", action="store_true", help="Print registered tool names and exit.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    server = create_server()
    if args.list_tools:
        for name in EXPECTED_TOOL_NAMES:
            print(name)
        return 0
    server.run(args.transport)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
