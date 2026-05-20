import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class ReservationStatus(enum.Enum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    SETTLED = "settled"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentTransactionType(enum.Enum):
    CONFIRMATION = "confirmation"
    REFUND = "refund"


class OutboxEventStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Reservation(Base):
    __tablename__ = "reservations"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_reservations_idempotency_key"),)

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    status = Column(Enum(ReservationStatus), default=ReservationStatus.DRAFT)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    idempotency_key = Column(String, nullable=False)
    stock_locks = relationship("StockLock", back_populates="reservation")
    payments = relationship("Payment", back_populates="reservation")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, unique=True, nullable=False)
    available_quantity = Column(Integer, nullable=False, default=0)


class StockLock(Base):
    __tablename__ = "stock_locks"

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"))
    item_id = Column(Integer, nullable=False)
    quantity = Column(Integer, default=1)
    expires_at = Column(DateTime, nullable=False)
    reservation = relationship("Reservation", back_populates="stock_locks")


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),)

    id = Column(Integer, primary_key=True)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False, default=PaymentStatus.PENDING)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reservation = relationship("Reservation", back_populates="payments")
    transactions = relationship("PaymentTransaction", back_populates="payment")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payment_transactions_idempotency_key"),
        UniqueConstraint("provider_reference", name="uq_payment_transactions_provider_reference"),
    )

    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("payments.id"), nullable=False)
    reservation_id = Column(Integer, ForeignKey("reservations.id"), nullable=False)
    transaction_type = Column(Enum(PaymentTransactionType), nullable=False)
    provider_reference = Column(String, nullable=False)
    status = Column(Enum(PaymentStatus), nullable=False)
    idempotency_key = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    payment = relationship("Payment", back_populates="transactions")


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("event_type", "idempotency_key", name="uq_outbox_event_type_idempotency_key"),)

    id = Column(Integer, primary_key=True)
    event_type = Column(String, nullable=False)
    aggregate_type = Column(String, nullable=False)
    aggregate_id = Column(Integer, nullable=False)
    idempotency_key = Column(String, nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(Enum(OutboxEventStatus), nullable=False, default=OutboxEventStatus.PENDING)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True)
    processing_expires_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_error = Column(Text, nullable=True)
