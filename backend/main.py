import json
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import engine, get_session
from .models import (
    Base,
    Inventory,
    OutboxEvent,
    OutboxEventStatus,
    Payment,
    PaymentStatus,
    PaymentTransaction,
    PaymentTransactionType,
    Reservation,
    ReservationStatus,
    StockLock,
)
from .schemas import PaymentConfirmRequest, PaymentConfirmResponse, ReservationCreate, ReservationResponse

app = FastAPI(title="Omni-Booking API")


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/health")
async def health():
    return {"status": "ok"}


async def get_current_user_id(x_user_id: int = Header(..., alias="X-User-Id")) -> int:
    if x_user_id <= 0:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return x_user_id


async def get_existing_idempotency(session: AsyncSession, idempotency_key: str) -> Reservation | None:
    result = await session.execute(
        select(Reservation).where(Reservation.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def get_existing_idempotency_payment(session: AsyncSession, idempotency_key: str) -> PaymentTransaction | None:
    result = await session.execute(
        select(PaymentTransaction).where(PaymentTransaction.idempotency_key == idempotency_key)
    )
    return result.scalar_one_or_none()


async def get_payment(session: AsyncSession, payment_id: int) -> Payment:
    result = await session.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment record is missing",
        )
    return payment


async def get_reservation(session: AsyncSession, reservation_id: int) -> Reservation:
    result = await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reservation not found")
    return reservation


async def get_stock_lock(session: AsyncSession, reservation_id: int) -> StockLock:
    result = await session.execute(
        select(StockLock).where(StockLock.reservation_id == reservation_id)
    )
    stock_lock = result.scalar_one_or_none()
    if stock_lock is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reservation stock lock is missing",
        )
    return stock_lock


def persist_idempotency(reservation: Reservation) -> Reservation:
    return reservation


def persist_idempotency_payment(payment: Payment) -> Payment:
    return payment


def mark_payment_settled(payment: Payment) -> Payment:
    payment.status = PaymentStatus.SETTLED
    return payment


def reservation_response(reservation: Reservation, stock_lock: StockLock) -> ReservationResponse:
    return ReservationResponse(
        reservation_id=reservation.id,
        item_id=reservation.item_id,
        user_id=reservation.user_id,
        quantity=reservation.quantity,
        status=reservation.status.value,
        idempotency_key=reservation.idempotency_key,
        stock_lock_expires_at=stock_lock.expires_at,
    )


def return_existing_response(reservation: Reservation, stock_lock: StockLock) -> ReservationResponse:
    return reservation_response(reservation, stock_lock)


def payment_response(
    payment: Payment,
    payment_transaction: PaymentTransaction,
) -> PaymentConfirmResponse:
    return PaymentConfirmResponse(
        reservation_id=payment.reservation_id,
        payment_id=payment.id,
        transaction_id=payment_transaction.id,
        status=ReservationStatus.PAID.value,
        idempotency_key=payment_transaction.idempotency_key,
    )


@app.post(
    "/reservations",
    response_model=ReservationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_reservation(
    payload: ReservationCreate,
    response: Response,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> ReservationResponse:
    idempotency_key = x_idempotency_key.strip()
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Idempotency-Key is required",
        )

    async with session.begin():
        existing = await get_existing_idempotency(session, idempotency_key)
        if existing is not None:
            stock_lock = await get_stock_lock(session, existing.id)
            response.status_code = status.HTTP_200_OK
            return return_existing_response(existing, stock_lock)

        inventory_result = await session.execute(
            select(Inventory).where(Inventory.item_id == payload.item_id)
        )
        inventory = inventory_result.scalar_one_or_none()
        if inventory is None or inventory.available_quantity < payload.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Insufficient stock",
            )
        inventory.available_quantity -= payload.quantity

        reservation = persist_idempotency(
            Reservation(
                item_id=payload.item_id,
                user_id=current_user_id,
                quantity=payload.quantity,
                status=ReservationStatus.PENDING_PAYMENT,
                idempotency_key=idempotency_key,
            )
        )
        session.add(reservation)
        await session.flush()

        stock_lock = StockLock(
            reservation_id=reservation.id,
            item_id=payload.item_id,
            quantity=payload.quantity,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        session.add(stock_lock)

    return reservation_response(reservation, stock_lock)


@app.post(
    "/reservations/{reservation_id}/payments/confirm",
    response_model=PaymentConfirmResponse,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_reservation_payment(
    reservation_id: int,
    payload: PaymentConfirmRequest,
    response: Response,
    x_idempotency_key: str = Header(..., alias="X-Idempotency-Key"),
    current_user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> PaymentConfirmResponse:
    idempotency_key = x_idempotency_key.strip()
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Idempotency-Key is required",
        )

    async with session.begin():
        existing_transaction = await get_existing_idempotency_payment(session, idempotency_key)
        if existing_transaction is not None:
            existing_reservation = await get_reservation(session, existing_transaction.reservation_id)
            if existing_reservation.user_id != current_user_id:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reservation access denied")
            if existing_transaction.reservation_id != reservation_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key belongs to a different reservation",
                )
            payment = await get_payment(session, existing_transaction.payment_id)
            response.status_code = status.HTTP_200_OK
            return payment_response(payment, existing_transaction)

        reservation = await get_reservation(session, reservation_id)
        if reservation.user_id != current_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reservation access denied")
        if reservation.status != ReservationStatus.PENDING_PAYMENT:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Reservation is not pending payment",
            )

        provider_reference_result = await session.execute(
            select(PaymentTransaction).where(PaymentTransaction.provider_reference == payload.provider_reference)
        )
        if provider_reference_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Provider reference already confirmed",
            )

        payment = mark_payment_settled(
            persist_idempotency_payment(
                Payment(
                    reservation_id=reservation.id,
                    amount=payload.amount,
                    currency=payload.currency.upper(),
                    status=PaymentStatus.SETTLED,
                    idempotency_key=idempotency_key,
                )
            )
        )
        session.add(payment)
        await session.flush()

        payment_transaction = PaymentTransaction(
            payment_id=payment.id,
            reservation_id=reservation.id,
            transaction_type=PaymentTransactionType.CONFIRMATION,
            provider_reference=payload.provider_reference,
            status=PaymentStatus.SETTLED,
            idempotency_key=idempotency_key,
        )
        session.add(payment_transaction)
        reservation.status = ReservationStatus.PAID
        await session.flush()

        outbox_payload = {
            "reservation_id": reservation.id,
            "payment_id": payment.id,
            "transaction_id": payment_transaction.id,
            "event": "reservation.payment_confirmed",
        }
        session.add(
            OutboxEvent(
                event_type="reservation.payment_confirmed",
                aggregate_type="reservation",
                aggregate_id=reservation.id,
                idempotency_key=idempotency_key,
                payload_json=json.dumps(outbox_payload, sort_keys=True, separators=(",", ":")),
                status=OutboxEventStatus.PENDING,
                attempt_count=0,
            )
        )

    return payment_response(payment, payment_transaction)
