from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_session
from backend.main import app
from backend.models import (
    Base,
    Inventory,
    OutboxEvent,
    OutboxEventStatus,
    Payment,
    PaymentStatus,
    PaymentTransaction,
    Reservation,
    ReservationStatus,
)


class PaymentOutboxEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "booking-test.db"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}")
        self.session_factory = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        asyncio.run(self._create_schema())

        async def override_get_session():
            async with self.session_factory() as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        asyncio.run(self.engine.dispose())
        self.tmpdir.cleanup()

    async def _create_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def _seed_inventory(self, item_id: int = 101, available_quantity: int = 5) -> None:
        async with self.session_factory() as session:
            async with session.begin():
                session.add(Inventory(item_id=item_id, available_quantity=available_quantity))

    def _create_reservation(self, key: str = "reservation-key") -> int:
        asyncio.run(self._seed_inventory())
        response = self.client.post(
            "/reservations",
            json={"item_id": 101, "quantity": 2},
            headers={"X-Idempotency-Key": key, "X-User-Id": "7"},
        )
        self.assertEqual(response.status_code, 201)
        return int(response.json()["reservation_id"])

    def _confirm_payment(
        self,
        reservation_id: int,
        key: str = "payment-key",
        provider_reference: str = "provider-reference",
        user_id: str = "7",
    ):
        return self.client.post(
            f"/reservations/{reservation_id}/payments/confirm",
            json={
                "amount": 1000,
                "currency": "THB",
                "provider_reference": provider_reference,
            },
            headers={"X-Idempotency-Key": key, "X-User-Id": user_id},
        )

    async def _row_counts(self) -> tuple[int, int, int]:
        async with self.session_factory() as session:
            payments = await session.scalar(select(func.count(Payment.id)))
            transactions = await session.scalar(select(func.count(PaymentTransaction.id)))
            outbox_events = await session.scalar(select(func.count(OutboxEvent.id)))
        return int(payments or 0), int(transactions or 0), int(outbox_events or 0)

    async def _reservation_status(self, reservation_id: int) -> ReservationStatus:
        async with self.session_factory() as session:
            status_value = await session.scalar(
                select(Reservation.status).where(Reservation.id == reservation_id)
            )
        assert status_value is not None
        return status_value

    async def _payment_records(self) -> tuple[Payment, PaymentTransaction, OutboxEvent]:
        async with self.session_factory() as session:
            payment = await session.scalar(select(Payment))
            transaction = await session.scalar(select(PaymentTransaction))
            outbox_event = await session.scalar(select(OutboxEvent))
        assert payment is not None
        assert transaction is not None
        assert outbox_event is not None
        return payment, transaction, outbox_event

    def test_confirm_payment_persists_payment_transaction_outbox_and_marks_paid(self) -> None:
        reservation_id = self._create_reservation()

        response = self._confirm_payment(reservation_id)

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["reservation_id"], reservation_id)
        self.assertEqual(payload["status"], "paid")
        self.assertEqual(payload["idempotency_key"], "payment-key")
        self.assertEqual(asyncio.run(self._reservation_status(reservation_id)), ReservationStatus.PAID)
        self.assertEqual(asyncio.run(self._row_counts()), (1, 1, 1))

        payment, transaction, outbox_event = asyncio.run(self._payment_records())
        self.assertEqual(payment.status, PaymentStatus.SETTLED)
        self.assertEqual(transaction.status, PaymentStatus.SETTLED)
        self.assertEqual(outbox_event.status, OutboxEventStatus.PENDING)
        self.assertEqual(outbox_event.event_type, "reservation.payment_confirmed")
        self.assertEqual(outbox_event.idempotency_key, "payment-key")

    def test_duplicate_idempotency_key_returns_existing_without_duplicate_rows(self) -> None:
        reservation_id = self._create_reservation()

        first = self._confirm_payment(reservation_id, key="same-payment-key")
        second = self._confirm_payment(reservation_id, key="same-payment-key")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(asyncio.run(self._row_counts()), (1, 1, 1))

    def test_missing_idempotency_key_fails(self) -> None:
        reservation_id = self._create_reservation()

        response = self.client.post(
            f"/reservations/{reservation_id}/payments/confirm",
            json={
                "amount": 1000,
                "currency": "THB",
                "provider_reference": "missing-key-provider",
            },
            headers={"X-User-Id": "7"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(asyncio.run(self._row_counts()), (0, 0, 0))

    def test_non_existing_reservation_fails_without_partial_rows(self) -> None:
        response = self._confirm_payment(999)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(asyncio.run(self._row_counts()), (0, 0, 0))

    def test_non_pending_reservation_fails_for_new_payment_key(self) -> None:
        reservation_id = self._create_reservation()
        first = self._confirm_payment(reservation_id, key="first-key", provider_reference="first-provider")

        second = self._confirm_payment(reservation_id, key="second-key", provider_reference="second-provider")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(asyncio.run(self._row_counts()), (1, 1, 1))

    def test_payment_route_does_not_use_background_tasks_or_external_calls(self) -> None:
        source = (PROJECT_ROOT / "backend" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("BackgroundTasks", source)
        self.assertNotIn(".add_task(", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("httpx.", source)


if __name__ == "__main__":
    unittest.main()
