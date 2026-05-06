from enum import Enum

from fastapi import APIRouter, Depends, Header
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


class ReservationStatus(Enum):
    draft = "draft"
    pending_payment = "pending_payment"
    paid = "paid"
    confirmed = "confirmed"
    fulfilled = "fulfilled"
    cancelled = "cancelled"
    expired = "expired"
    refunded = "refunded"


class Reservation:
    status = ReservationStatus.draft


class StockLock:
    def __init__(self, quantity: int):
        self.quantity = quantity


class Payment:
    def __init__(self, status: str):
        self.status = status


class PaymentTransaction:
    def __init__(self, kind: str):
        self.kind = kind


class OutboxEvent:
    __table_args__ = (UniqueConstraint("event_type", "idempotency_key"),)

    def __init__(self, event_type: str, idempotency_key: str):
        self.event_type = event_type
        self.idempotency_key = idempotency_key


class IdempotencyRecord:
    __table_args__ = (UniqueConstraint("key"),)

    def __init__(self, key: str):
        self.key = key


def get_async_session() -> AsyncSession:
    raise NotImplementedError


async def get_existing_idempotency_result(session: AsyncSession, idempotency_key: str):
    raise NotImplementedError


async def ensure_stock_lock_active(session: AsyncSession, reservation: Reservation) -> None:
    raise NotImplementedError


async def release_active_stock_locks(session: AsyncSession, reservation: Reservation) -> None:
    raise NotImplementedError


async def release_stock_locks(session: AsyncSession, reservation: Reservation) -> None:
    raise NotImplementedError


@router.post("/reservations")
async def create_reservation(
    session: AsyncSession = Depends(get_async_session),
    idempotency_key: str = Header(alias="X-Idempotency-Key"),
):
    existing = await get_existing_idempotency_result(session, idempotency_key)
    if existing:
        return existing

    async with session.begin():
        reservation = Reservation()
        reservation.status = ReservationStatus.pending_payment
        session.add(reservation)
        session.add(IdempotencyRecord(key=idempotency_key))
        session.add(OutboxEvent(event_type="reservation.created", idempotency_key=idempotency_key))

    return reservation


async def mark_paid(session: AsyncSession, reservation: Reservation) -> None:
    if reservation.status == ReservationStatus.pending_payment:
        session.add(Payment(status="settled"))
        reservation.status = ReservationStatus.paid


async def confirm_reservation(session: AsyncSession, reservation: Reservation) -> None:
    if reservation.status == ReservationStatus.paid:
        await ensure_stock_lock_active(session, reservation)
        reservation.status = ReservationStatus.confirmed


async def expire_reservation(session: AsyncSession, reservation: Reservation) -> Reservation:
    if reservation.status == ReservationStatus.expired:
        return reservation
    if reservation.status == ReservationStatus.pending_payment:
        await release_active_stock_locks(session, reservation)
        reservation.status = ReservationStatus.expired
    return reservation


async def cancel_reservation(session: AsyncSession, reservation: Reservation) -> None:
    if reservation.status == ReservationStatus.pending_payment:
        await release_stock_locks(session, reservation)
        reservation.status = ReservationStatus.cancelled


async def refund_reservation(session: AsyncSession, reservation: Reservation) -> None:
    if reservation.status == ReservationStatus.paid:
        session.add(PaymentTransaction(kind="refund"))
        reservation.status = ReservationStatus.refunded


async def create_stock_lock(session: AsyncSession, requested_quantity: int, available_quantity: int) -> None:
    if requested_quantity <= available_quantity:
        session.add(StockLock(quantity=requested_quantity))
