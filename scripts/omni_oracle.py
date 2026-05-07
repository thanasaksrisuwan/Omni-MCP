from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_KNOWLEDGE_DIR = ".agent_bus/knowledge"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def record_knowledge(
    type: str,
    content: str,
    *,
    context: str | list[str] | None = None,
    tags: list[str] | None = None,
    confidence: float = 1.0,
    knowledge_dir: str | Path = DEFAULT_KNOWLEDGE_DIR,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    dir_path = Path(knowledge_dir)
    if not dir_path.is_absolute():
        dir_path = root / dir_path
    ensure_dir(dir_path)
    
    entry_id = str(uuid.uuid4())
    entry = {
        "id": entry_id,
        "type": type,
        "content": content,
        "context": context if isinstance(context, list) else ([context] if context else []),
        "tags": [t.lower() for t in (tags or [])],
        "confidence": confidence,
        "created_at": utc_now(),
        "provenance": "manual-recording",
    }
    
    file_path = dir_path / f"{entry_id}.json"
    file_path.write_text(json.dumps(entry, indent=2, sort_keys=True), encoding="utf-8")
    
    # Return relative path if possible, else absolute
    try:
        final_path = str(file_path.relative_to(root))
    except ValueError:
        final_path = str(file_path)

    return {
        "status": "ok",
        "id": entry_id,
        "message": f"Knowledge recorded successfully: {type}",
        "path": final_path,
    }


def recall_knowledge(
    query: str | None = None,
    *,
    tags: list[str] | None = None,
    type: str | None = None,
    knowledge_dir: str | Path = DEFAULT_KNOWLEDGE_DIR,
) -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    dir_path = Path(knowledge_dir)
    if not dir_path.is_absolute():
        dir_path = root / dir_path
    
    if not dir_path.exists():
        return {"status": "ok", "results": [], "count": 0}
    
    results = []
    query_tags = {t.lower() for t in (tags or [])}
    query_text = (query or "").lower()
    
    for file_path in dir_path.glob("*.json"):
        try:
            entry = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
            
        # Filter by type
        if type and entry.get("type") != type:
            continue
            
        # Filter by tags
        entry_tags = {t.lower() for t in entry.get("tags", [])}
        if query_tags and not query_tags.intersection(entry_tags):
            continue
            
        # Filter by text search
        if query_text:
            text_haystack = f"{entry.get('content', '')} {' '.join(entry.get('context', []))}".lower()
            if query_text not in text_haystack:
                continue
                
        results.append(entry)
    
    # Sort by date (newest first)
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {
        "status": "ok",
        "results": results,
        "count": len(results),
        "knowledge_dir": str(knowledge_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Omni-Oracle: Contextual Memory System")
    subparsers = parser.add_subparsers(dest="command")
    
    # Record
    rec = subparsers.add_parser("record")
    rec.add_argument("--type", required=True, choices=["decision", "bug_pattern", "developer_preference", "business_rule"])
    rec.add_argument("--content", required=True)
    rec.add_argument("--context", action="append")
    rec.add_argument("--tags", action="append")
    rec.add_argument("--confidence", type=float, default=1.0)
    
    # Recall
    rel = subparsers.add_parser("recall")
    rel.add_argument("--query")
    rel.add_argument("--type")
    rel.add_argument("--tags", action="append")
    
    args = parser.parse_args()
    
    if args.command == "record":
        result = record_knowledge(args.type, args.content, context=args.context, tags=args.tags, confidence=args.confidence)
        print(json.dumps(result, indent=2))
    elif args.command == "recall":
        result = recall_knowledge(query=args.query, type=args.type, tags=args.tags)
        print(json.dumps(result, indent=2))
        
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
