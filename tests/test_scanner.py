from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.backend_scanner import generate_manifests


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    project_root = PROJECT_ROOT
    fixture = project_root / "tests" / "fixtures" / "sample_routes.py"

    with tempfile.TemporaryDirectory() as tmp:
        output_dir = Path(tmp)
        generate_manifests(project_root, output_dir, [fixture])

        routes_manifest = load_json(output_dir / "routes.json")
        dependencies_manifest = load_json(output_dir / "dependencies.json")
        index_meta = load_json(output_dir / "index-meta.json")
        validation_rules = load_json(output_dir / "validation-rules.json")

    routes = routes_manifest["routes"]
    dependencies = dependencies_manifest["dependencies"]

    assert index_meta["routes_count"] == 3
    assert index_meta["dependencies_count"] == 3
    assert validation_rules["confidence_threshold"] == 0.75

    route_by_handler = {route["handler"]: route for route in routes}
    assert route_by_handler["health_check"]["method"] == "GET"
    assert route_by_handler["health_check"]["path"] == "/health"
    assert route_by_handler["health_check"]["is_async"] is False
    assert route_by_handler["create_reservation"]["method"] == "POST"
    assert route_by_handler["create_reservation"]["path"] == "/reservations"
    assert route_by_handler["create_reservation"]["is_async"] is True
    assert route_by_handler["create_reservation"]["session_type"] == "AsyncSession"
    assert route_by_handler["update_reservation"]["method"] == "PATCH"
    assert route_by_handler["update_reservation"]["path"] == "/reservations/{reservation_id}"

    depends = [
        dependency
        for dependency in dependencies
        if dependency["kind"] == "Depends" and dependency["callable"] == "get_session"
    ]
    assert len(depends) == 2
    assert all(dependency["is_async_session"] is True for dependency in depends)

    security = [
        dependency
        for dependency in dependencies
        if dependency["kind"] == "Security" and dependency["callable"] == "get_current_user"
    ]
    assert len(security) == 1
    assert security[0]["scopes"] == ["reservation:create"]
    assert security[0]["param"] == "user"

    required_route_fields = {"method", "path", "handler", "is_async", "source_file", "line", "confidence"}
    required_dependency_fields = {"kind", "callable", "param", "source_file", "line", "confidence"}
    assert required_route_fields <= set(routes[0])
    assert required_dependency_fields <= set(dependencies[0])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
