from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.models import Base, OutboxEvent, OutboxEventStatus
from backend.worker import HandlerRegistry, claim_events, retry_delay, run_once


class OutboxWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "outbox-test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        self.session_factory = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        asyncio.run(self._create_schema())
        self.now = datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc)

    def tearDown(self) -> None:
        asyncio.run(self.engine.dispose())
        self.tmpdir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _seed_event(
        self,
        *,
        status: OutboxEventStatus = OutboxEventStatus.PENDING,
        attempt_count: int = 0,
        next_retry_at: datetime | None = None,
        processing_expires_at: datetime | None = None,
        key: str = "outbox-key",
    ) -> int:
        async with self.session_factory() as session:
            async with session.begin():
                event = OutboxEvent(
                    event_type="reservation.payment_confirmed",
                    aggregate_type="reservation",
                    aggregate_id=1,
                    idempotency_key=key,
                    payload_json="{}",
                    status=status,
                    attempt_count=attempt_count,
                    next_retry_at=next_retry_at,
                    processing_expires_at=processing_expires_at,
                )
                session.add(event)
                await session.flush()
                return int(event.id)

    async def _get_event(self, event_id: int) -> OutboxEvent:
        async with self.session_factory() as session:
            event = await session.get(OutboxEvent, event_id)
        assert event is not None
        return event

    async def _all_events(self) -> list[OutboxEvent]:
        async with self.session_factory() as session:
            result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.id))
            return list(result.scalars().all())

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    def test_claim_events_marks_pending_as_processing(self) -> None:
        event_id = asyncio.run(self._seed_event())

        async def claim() -> list[OutboxEvent]:
            async with self.session_factory() as session:
                return await claim_events(session, limit=10, now=self.now)

        claimed = asyncio.run(claim())
        event = asyncio.run(self._get_event(event_id))

        self.assertEqual([item.id for item in claimed], [event_id])
        self.assertEqual(event.status, OutboxEventStatus.PROCESSING)
        self.assertEqual(self._as_utc(event.processing_expires_at), self.now + timedelta(minutes=5))

    def test_run_once_processes_payment_confirmed_event(self) -> None:
        event_id = asyncio.run(self._seed_event())

        result = asyncio.run(run_once(self.session_factory, limit=10, now=self.now))
        event = asyncio.run(self._get_event(event_id))

        self.assertEqual(result.claimed, 1)
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(event.status, OutboxEventStatus.PROCESSED)
        self.assertEqual(self._as_utc(event.processed_at), self.now)
        self.assertIsNone(event.processing_expires_at)
        self.assertIsNone(event.next_retry_at)

    def test_handler_failure_sets_exponential_backoff(self) -> None:
        event_id = asyncio.run(self._seed_event())
        registry = HandlerRegistry()

        async def fail_handler(_event: OutboxEvent) -> None:
            raise RuntimeError("handler failed")

        registry.register("reservation.payment_confirmed", fail_handler)

        result = asyncio.run(run_once(self.session_factory, registry=registry, limit=10, now=self.now))
        event = asyncio.run(self._get_event(event_id))

        self.assertEqual(result.claimed, 1)
        self.assertEqual(result.processed, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(event.status, OutboxEventStatus.FAILED)
        self.assertEqual(event.attempt_count, 1)
        self.assertEqual(self._as_utc(event.next_retry_at), self.now + retry_delay(1))
        self.assertEqual(event.last_error, "handler failed")

    def test_terminal_failed_event_is_not_reclaimed(self) -> None:
        event_id = asyncio.run(
            self._seed_event(
                status=OutboxEventStatus.FAILED,
                attempt_count=5,
                next_retry_at=self.now - timedelta(minutes=1),
            )
        )

        result = asyncio.run(run_once(self.session_factory, limit=10, now=self.now))
        event = asyncio.run(self._get_event(event_id))

        self.assertEqual(result.claimed, 0)
        self.assertEqual(event.status, OutboxEventStatus.FAILED)
        self.assertEqual(event.attempt_count, 5)

    def test_expired_processing_event_is_reclaimed(self) -> None:
        event_id = asyncio.run(
            self._seed_event(
                status=OutboxEventStatus.PROCESSING,
                processing_expires_at=self.now - timedelta(minutes=1),
            )
        )

        async def claim() -> list[OutboxEvent]:
            async with self.session_factory() as session:
                return await claim_events(session, limit=10, now=self.now)

        claimed = asyncio.run(claim())
        event = asyncio.run(self._get_event(event_id))

        self.assertEqual([item.id for item in claimed], [event_id])
        self.assertEqual(event.status, OutboxEventStatus.PROCESSING)
        self.assertEqual(self._as_utc(event.processing_expires_at), self.now + timedelta(minutes=5))

    def test_second_worker_call_does_not_reprocess_claimed_event(self) -> None:
        asyncio.run(self._seed_event())

        async def claim_twice() -> tuple[list[OutboxEvent], list[OutboxEvent]]:
            async with self.session_factory() as first_session:
                first = await claim_events(first_session, limit=10, now=self.now)
            async with self.session_factory() as second_session:
                second = await claim_events(second_session, limit=10, now=self.now)
            return first, second

        first, second = asyncio.run(claim_twice())

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(asyncio.run(self._all_events())), 1)


if __name__ == "__main__":
    unittest.main()
