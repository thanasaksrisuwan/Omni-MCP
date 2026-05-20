from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ReservationCreate(BaseModel):
    item_id: int = Field(..., ge=1)
    quantity: int = Field(default=1, ge=1)


class ReservationResponse(BaseModel):
    reservation_id: int
    item_id: int
    user_id: int
    quantity: int
    status: str
    idempotency_key: str
    stock_lock_expires_at: datetime


class PaymentConfirmRequest(BaseModel):
    amount: int = Field(..., ge=1)
    currency: str = Field(..., min_length=3, max_length=3)
    provider_reference: str = Field(..., min_length=1)


class PaymentConfirmResponse(BaseModel):
    reservation_id: int
    payment_id: int
    transaction_id: int
    status: str
    idempotency_key: str
