from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends
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
    status = "draft"


class StockLock:
    def __init__(self, quantity: int):
        self.quantity = quantity


class Payment:
    pass


class PaymentTransaction:
    pass


class OutboxEvent:
    def __init__(self, event_type: str):
        self.event_type = event_type


def get_async_session() -> AsyncSession:
    raise NotImplementedError


def send_reservation_confirmation(reservation_id: str) -> None:
    raise NotImplementedError


@router.post("/reservations/unsafe")
async def create_unsafe_reservation(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_async_session),
):
    async with session.begin():
        reservation = Reservation()
        session.add(reservation)
        session.add(OutboxEvent(event_type="reservation.created"))
        background_tasks.add_task(send_reservation_confirmation, "reservation_1")
    return reservation


async def draft_to_confirmed(reservation: Reservation) -> None:
    if reservation.status == "draft":
        reservation.status = "confirmed"


async def expire_without_release(reservation: Reservation) -> None:
    if reservation.status == "pending_payment":
        reservation.status = "expired"


async def paid_without_payment(reservation: Reservation) -> None:
    if reservation.status == "pending_payment":
        reservation.status = "paid"


async def confirm_without_stock(reservation: Reservation) -> None:
    if reservation.status == "paid":
        reservation.status = "confirmed"


async def cancel_without_release(reservation: Reservation) -> None:
    if reservation.status == "pending_payment":
        reservation.status = "cancelled"


async def refund_without_transaction(reservation: Reservation) -> None:
    if reservation.status == "paid":
        reservation.status = "refunded"


async def expired_to_confirmed(reservation: Reservation) -> None:
    if reservation.status == "expired":
        reservation.status = "confirmed"


async def create_unsafe_stock_lock(session: AsyncSession, requested_quantity: int) -> None:
    session.add(StockLock(quantity=requested_quantity))
