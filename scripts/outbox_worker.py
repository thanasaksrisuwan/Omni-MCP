from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import async_session, engine
from backend.models import Base
from backend.worker import run_once


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process Omni-Booking outbox events.")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum events to claim per batch.")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> int:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    result = await run_once(async_session, limit=args.limit)
    print(json.dumps(asdict(result), ensure_ascii=True, sort_keys=True))
    return 0


def main() -> int:
    args = parse_args()
    if not args.once:
        print("Only --once is supported in the MVP worker.")
        return 2
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
