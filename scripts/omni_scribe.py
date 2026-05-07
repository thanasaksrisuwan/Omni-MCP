from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import backend_reservation_safety, backend_session_scanner, frontend_scanner, omni_medic


FRONTEND_SUFFIXES = {".js", ".jsx", ".ts", ".tsx"}
BACKEND_SUFFIXES = {".py"}
SUPPORTED_SUFFIXES = FRONTEND_SUFFIXES | BACKEND_SUFFIXES
MIN_CONFIDENCE = 0.75


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(stable_json(data) + "\n", encoding="utf-8")


def uncertainty(reason: str) -> dict[str, Any]:
    return {
        "status": "needs_manual_review",
        "risk": "unknown",
        "reason": reason,
        "confidence": 0.0,
    }


def resolve_project_root(project_root: str | Path) -> Path:
    path = Path(project_root)
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def resolve_target_path(project_root: Path, target_file_path: str) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    if not target_file_path or not target_file_path.strip():
        return None, None, uncertainty("target_file_path is required.")

    target = Path(target_file_path)
    if not target.is_absolute():
        target = project_root / target
    target = target.resolve()

    try:
        relative = target.relative_to(project_root)
    except ValueError:
        return None, None, uncertainty(f"Target file is outside project root: {target}")

    if any(part in {"..", ""} for part in relative.parts):
        return None, None, uncertainty("Target file path is not safe to plan.")

    return target, relative.as_posix(), None


def resolve_agent_bus_dir(project_root: Path, path_value: str, required_prefix: tuple[str, ...]) -> Path:
    path = Path(path_value)
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    relative = path.relative_to(project_root)
    if relative.parts[: len(required_prefix)] != required_prefix:
        prefix = "/".join(required_prefix)
        raise ValueError(f"Output directory must be under {prefix}.")
    return path


def resolve_roots(project_root: Path, roots: list[str] | None) -> list[Path]:
    resolved: list[Path] = []
    for root in roots or []:
        path = Path(root)
        if not path.is_absolute():
            path = project_root / path
        resolved.append(path.resolve())
    return resolved


def safe_artifact_stem(target_relative: str, content_hash: str) -> str:
    safe_target = re.sub(r"[^A-Za-z0-9._-]+", "_", target_relative).strip("._-")
    if not safe_target:
        safe_target = "planned_write"
    return f"{safe_target}_{content_hash[:12]}"


def issue_from_exception(exc: BaseException, target_relative: str) -> dict[str, Any]:
    return {
        "code": exc.__class__.__name__,
        "severity": "error",
        "file": target_relative,
        "line": getattr(exc, "lineno", 0) or 0,
        "message": str(exc),
        "confidence": 0.95,
        "provenance": "omni-scribe-validation",
    }


def collect_validation_issues(validation: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in ("issues", "errors"):
        values = validation.get(key, [])
        if isinstance(values, list):
            issues.extend(item for item in values if isinstance(item, dict))
    return issues


def validation_failed(validation: dict[str, Any]) -> bool:
    if validation.get("status") in {"failed", "needs_manual_review"}:
        return True
    return any(item.get("severity") == "error" for item in collect_validation_issues(validation))


def validate_frontend(
    *,
    project_root: Path,
    temp_file: Path,
    target_relative: str,
    frontend_roots: list[str] | None,
    validation_output_dir: Path,
) -> dict[str, Any]:
    try:
        roots = [temp_file, *resolve_roots(project_root, frontend_roots)]
        manifests = frontend_scanner.index_project(project_root, validation_output_dir, roots)
        index_meta = manifests["index_meta"]
        if index_meta.get("status") != "ok" or index_meta.get("confidence", 0.0) < MIN_CONFIDENCE:
            return {
                "status": "needs_manual_review",
                "risk": "unknown",
                "reason": "Frontend manifests were not confident enough to validate the proposed content.",
                "manifest_status": index_meta.get("status"),
                "confidence": index_meta.get("confidence", 0.0),
                "warnings": index_meta.get("warnings", []),
            }
        result = frontend_scanner.validate_ui_code(
            temp_file,
            project_root,
            manifests["components"],
            manifests["props"],
            manifests["tokens"],
            manifests["assets"],
        )
        return {"validator": "frontend.validate_ui_code", **result}
    except Exception as exc:  # noqa: BLE001 - validator failures must become blocking evidence.
        return {
            "status": "failed",
            "risk": "high",
            "validator": "frontend.validate_ui_code",
            "issues": [issue_from_exception(exc, target_relative)],
            "confidence": 0.95,
        }


def validate_backend(
    *,
    project_root: Path,
    temp_file: Path,
    target_relative: str,
    backend_roots: list[str] | None,
    validation_output_dir: Path,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    roots = [temp_file, *resolve_roots(project_root, backend_roots)]

    try:
        session_manifests = backend_session_scanner.generate_manifests(
            project_root,
            validation_output_dir / "session",
            roots,
        )
        tx_validation = backend_session_scanner.validate_transaction_usage(
            session_manifests["transaction_boundaries"]
        )
        results.append({"validator": "backend.validate_transaction_usage", **tx_validation})
    except Exception as exc:  # noqa: BLE001
        results.append(
            {
                "status": "failed",
                "risk": "high",
                "validator": "backend.validate_transaction_usage",
                "errors": [issue_from_exception(exc, target_relative)],
                "confidence": 0.95,
            }
        )

    try:
        reservation_manifests = backend_reservation_safety.generate_manifests(
            project_root,
            validation_output_dir / "reservation",
            roots,
        )
        results.extend(
            [
                {
                    "validator": "backend.validate_state_transition",
                    **backend_reservation_safety.validate_state_transition(reservation_manifests["state_machines"]),
                },
                {
                    "validator": "backend.validate_idempotency",
                    **backend_reservation_safety.validate_idempotency(reservation_manifests["outbox_events"]),
                },
                {
                    "validator": "backend.validate_outbox_usage",
                    **backend_reservation_safety.validate_outbox_usage(reservation_manifests["outbox_events"]),
                },
                {
                    "validator": "backend.validate_reservation_invariants",
                    **backend_reservation_safety.validate_reservation_invariants(reservation_manifests["invariants"]),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        results.append(
            {
                "status": "failed",
                "risk": "high",
                "validator": "backend.reservation_safety",
                "errors": [issue_from_exception(exc, target_relative)],
                "confidence": 0.95,
            }
        )

    has_blocker = any(validation_failed(result) for result in results)
    return {
        "status": "failed" if has_blocker else "ok",
        "risk": "high" if has_blocker else "low",
        "validator": "backend.composite_safety",
        "results": results,
        "confidence": min((result.get("confidence", 0.9) for result in results), default=0.9),
    }


def flatten_backend_issues(validation: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for result in validation.get("results", []):
        issues.extend(collect_validation_issues(result))
    return issues


def plan_write(
    target_file_path: str,
    proposed_content: str,
    *,
    project_root: str | Path = ".",
    frontend_roots: list[str] | None = None,
    backend_roots: list[str] | None = None,
    artifact_dir: str = ".agent_bus/scribes",
) -> dict[str, Any]:
    root = resolve_project_root(project_root)
    target_path, target_relative, target_error = resolve_target_path(root, target_file_path)
    if target_error:
        return target_error
    assert target_path is not None
    assert target_relative is not None

    suffix = target_path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        return uncertainty(f"Unsupported target file type for Omni-Scribe validation: {suffix or '<none>'}")

    if not isinstance(proposed_content, str) or not proposed_content.strip():
        return uncertainty("proposed_content must be a non-empty string.")

    try:
        scribes_dir = resolve_agent_bus_dir(root, artifact_dir, (".agent_bus", "scribes"))
        temp_root = resolve_agent_bus_dir(root, ".agent_bus/scribe_temp", (".agent_bus", "scribe_temp"))
    except ValueError as exc:
        return uncertainty(str(exc))

    content_hash = hashlib.sha256(proposed_content.encode("utf-8")).hexdigest()
    artifact_stem = safe_artifact_stem(target_relative, content_hash)
    temp_file = temp_root / artifact_stem / target_relative
    validation_output_dir = root / ".agent_bus" / "logs" / "omni_scribe" / artifact_stem
    temp_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file.write_text(proposed_content, encoding="utf-8")

    if suffix in FRONTEND_SUFFIXES:
        validation = validate_frontend(
            project_root=root,
            temp_file=temp_file,
            target_relative=target_relative,
            frontend_roots=frontend_roots,
            validation_output_dir=validation_output_dir / "frontend",
        )
        issues = collect_validation_issues(validation)
    else:
        validation = validate_backend(
            project_root=root,
            temp_file=temp_file,
            target_relative=target_relative,
            backend_roots=backend_roots,
            validation_output_dir=validation_output_dir / "backend",
        )
        issues = flatten_backend_issues(validation)

    if validation_failed(validation):
        suggestions = omni_medic.diagnose_and_suggest(issues)
        return {
            "status": "blocked",
            "risk": "high" if validation.get("status") == "failed" else "unknown",
            "target_file_path": target_relative,
            "artifact_path": None,
            "temp_file": temp_file.relative_to(root).as_posix(),
            "validation": validation,
            "issues": issues,
            "suggestions": suggestions,
            "confidence": validation.get("confidence", 0.0),
            "provenance": "omni-scribe-write-plan",
        }

    artifact = {
        "schema_version": "1.0.0",
        "status": "planned",
        "created_at": utc_now(),
        "target_file_path": target_relative,
        "target_exists": target_path.exists(),
        "content_hash": content_hash,
        "proposed_content": proposed_content,
        "validation": validation,
        "temp_file": temp_file.relative_to(root).as_posix(),
        "provenance": "omni-scribe-write-plan",
        "note": "This artifact is a plan only. Omni-Scribe did not write to the target file.",
    }
    artifact_path = scribes_dir / f"{artifact_stem}.json"
    write_json(artifact_path, artifact)

    return {
        "status": "ok",
        "risk": "low",
        "target_file_path": target_relative,
        "artifact_path": artifact_path.relative_to(root).as_posix(),
        "content_hash": content_hash,
        "validation": validation,
        "confidence": validation.get("confidence", 0.9),
        "provenance": "omni-scribe-write-plan",
    }
