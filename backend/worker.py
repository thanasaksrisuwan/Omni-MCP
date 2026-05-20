from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import OutboxEvent, OutboxEventStatus

LOGGER = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
PROCESSING_TIMEOUT = timedelta(minutes=5)
PAYMENT_CONFIRMED_EVENT = "reservation.payment_confirmed"

EventHandler = Callable[[OutboxEvent], Awaitable[None]]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, EventHandler] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        self._handlers[event_type] = handler

    async def handle(self, event: OutboxEvent) -> None:
        handler = self._handlers.get(event.event_type)
        if handler is None:
            raise ValueError(f"No outbox handler registered for event type: {event.event_type}")
        await handler(event)


@dataclass(frozen=True)
class WorkerRunResult:
    claimed: int
    processed: int
    failed: int


async def handle_payment_confirmed(event: OutboxEvent) -> None:
    LOGGER.info(
        "Processed outbox event %s with idempotency key %s",
        event.event_type,
        event.idempotency_key,
    )


DEFAULT_REGISTRY = HandlerRegistry()
DEFAULT_REGISTRY.register(PAYMENT_CONFIRMED_EVENT, handle_payment_confirmed)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def retry_delay(attempt_count: int) -> timedelta:
    return timedelta(minutes=2**attempt_count)


def _dialect_supports_skip_locked(session: AsyncSession) -> bool:
    bind = session.get_bind()
    return bind.dialect.name in {"postgresql", "oracle"}


def _eligible_event_filter(now: datetime):
    retry_due = and_(
        OutboxEvent.status == OutboxEventStatus.FAILED,
        OutboxEvent.attempt_count < MAX_ATTEMPTS,
        or_(OutboxEvent.next_retry_at.is_(None), OutboxEvent.next_retry_at <= now),
    )
    processing_expired = and_(
        OutboxEvent.status == OutboxEventStatus.PROCESSING,
        OutboxEvent.processing_expires_at.is_not(None),
        OutboxEvent.processing_expires_at <= now,
        OutboxEvent.attempt_count < MAX_ATTEMPTS,
    )
    return or_(OutboxEvent.status == OutboxEventStatus.PENDING, retry_due, processing_expired)


async def claim_events(
    session: AsyncSession,
    limit: int = 10,
    now: datetime | None = None,
    processing_timeout: timedelta = PROCESSING_TIMEOUT,
) -> list[OutboxEvent]:
    if limit <= 0:
        return []

    now = now or utc_now()
    expires_at = now + processing_timeout
    statement = (
        select(OutboxEvent)
        .where(_eligible_event_filter(now))
        .order_by(OutboxEvent.created_at, OutboxEvent.id)
        .limit(limit)
    )
    if _dialect_supports_skip_locked(session):
        statement = statement.with_for_update(skip_locked=True)

    async with session.begin():
        result = await session.execute(statement)
        events = list(result.scalars().all())
        for event in events:
            event.status = OutboxEventStatus.PROCESSING
            event.processing_expires_at = expires_at
            event.updated_at = now
    return events


async def _load_processing_event(session: AsyncSession, event_id: int) -> OutboxEvent | None:
    async with session.begin():
        event = await session.get(OutboxEvent, event_id)
        if event is None or event.status != OutboxEventStatus.PROCESSING:
            return None
        return event


async def _mark_processed(session: AsyncSession, event_id: int, now: datetime) -> None:
    async with session.begin():
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            return
        event.status = OutboxEventStatus.PROCESSED
        event.processed_at = now
        event.processing_expires_at = None
        event.next_retry_at = None
        event.last_error = None
        event.updated_at = now


async def _mark_failed(
    session: AsyncSession,
    event_id: int,
    error: Exception,
    now: datetime,
    max_attempts: int = MAX_ATTEMPTS,
) -> None:
    async with session.begin():
        event = await session.get(OutboxEvent, event_id)
        if event is None:
            return
        event.attempt_count += 1
        event.status = OutboxEventStatus.FAILED
        event.processing_expires_at = None
        event.processed_at = None
        event.last_error = str(error)
        event.updated_at = now
        if event.attempt_count >= max_attempts:
            event.next_retry_at = None
        else:
            event.next_retry_at = now + retry_delay(event.attempt_count)


async def process_event(
    session_factory: Callable[[], Any],
    event_id: int,
    registry: HandlerRegistry = DEFAULT_REGISTRY,
    now: datetime | None = None,
) -> bool:
    now = now or utc_now()
    async with session_factory() as session:
        event = await _load_processing_event(session, event_id)
    if event is None:
        return False

    try:
        await registry.handle(event)
    except Exception as exc:
        async with session_factory() as session:
            await _mark_failed(session, event_id, exc, now)
        return False

    async with session_factory() as session:
        await _mark_processed(session, event_id, now)
    return True


async def run_once(
    session_factory: Callable[[], Any],
    registry: HandlerRegistry = DEFAULT_REGISTRY,
    limit: int = 10,
    now: datetime | None = None,
) -> WorkerRunResult:
    now = now or utc_now()
    async with session_factory() as session:
        events = await claim_events(session, limit=limit, now=now)

    processed = 0
    failed = 0
    for event in events:
        if await process_event(session_factory, event.id, registry=registry, now=now):
            processed += 1
        else:
            failed += 1
    return WorkerRunResult(claimed=len(events), processed=processed, failed=failed)
