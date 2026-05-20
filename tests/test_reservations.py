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
from backend.models import Base, Inventory, Reservation, StockLock


class ReservationEndpointTests(unittest.TestCase):
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
                session.add(
                    Inventory(
                        item_id=item_id,
                        available_quantity=available_quantity,
                    )
                )

    async def _count_rows(self) -> tuple[int, int]:
        async with self.session_factory() as session:
            reservations = await session.scalar(select(func.count(Reservation.id)))
            stock_locks = await session.scalar(select(func.count(StockLock.id)))
        return int(reservations or 0), int(stock_locks or 0)

    async def _available_quantity(self, item_id: int = 101) -> int:
        async with self.session_factory() as session:
            value = await session.scalar(
                select(Inventory.available_quantity).where(Inventory.item_id == item_id)
            )
        return int(value or 0)

    def _post_reservation(self, key: str, item_id: int = 101, quantity: int = 2):
        return self.client.post(
            "/reservations",
            json={"item_id": item_id, "quantity": quantity},
            headers={"X-Idempotency-Key": key, "X-User-Id": "7"},
        )

    def test_create_reservation_persists_reservation_and_stock_lock(self) -> None:
        asyncio.run(self._seed_inventory())

        response = self._post_reservation("create-once")

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["item_id"], 101)
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["quantity"], 2)
        self.assertEqual(payload["status"], "pending_payment")
        self.assertEqual(payload["idempotency_key"], "create-once")
        self.assertEqual(asyncio.run(self._count_rows()), (1, 1))
        self.assertEqual(asyncio.run(self._available_quantity()), 3)

    def test_duplicate_idempotency_key_returns_existing_without_duplicate_rows(self) -> None:
        asyncio.run(self._seed_inventory())

        first = self._post_reservation("same-key")
        second = self._post_reservation("same-key")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["reservation_id"], second.json()["reservation_id"])
        self.assertEqual(asyncio.run(self._count_rows()), (1, 1))
        self.assertEqual(asyncio.run(self._available_quantity()), 3)

    def test_duplicate_idempotency_key_ignores_changed_retry_payload(self) -> None:
        asyncio.run(self._seed_inventory(available_quantity=10))

        first = self._post_reservation("retry-key", quantity=2)
        second = self._post_reservation("retry-key", quantity=5)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["quantity"], 2)
        self.assertEqual(first.json()["reservation_id"], second.json()["reservation_id"])
        self.assertEqual(asyncio.run(self._count_rows()), (1, 1))
        self.assertEqual(asyncio.run(self._available_quantity()), 8)

    def test_missing_idempotency_key_fails(self) -> None:
        asyncio.run(self._seed_inventory())

        response = self.client.post(
            "/reservations",
            json={"item_id": 101, "quantity": 1},
            headers={"X-User-Id": "7"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(asyncio.run(self._count_rows()), (0, 0))

    def test_insufficient_stock_fails_without_partial_rows(self) -> None:
        asyncio.run(self._seed_inventory(available_quantity=1))

        response = self._post_reservation("too-much", quantity=2)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(asyncio.run(self._count_rows()), (0, 0))
        self.assertEqual(asyncio.run(self._available_quantity()), 1)

    def test_service_layer_does_not_commit(self) -> None:
        services_dir = Path(__file__).resolve().parents[1] / "backend" / "services"
        service_sources = list(services_dir.glob("*.py"))
        for source in service_sources:
            self.assertNotIn(".commit(", source.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
