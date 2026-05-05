import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session


router = APIRouter()


class Reservation:
    pass


class StockLock:
    pass


class Payment:
    pass


def get_async_session() -> AsyncSession:
    raise NotImplementedError


def get_sync_session() -> Session:
    raise NotImplementedError


def send_confirmation(reservation_id: str) -> None:
    raise NotImplementedError


async def reserve_stock(session: AsyncSession, item_id: str) -> None:
    await session.execute("select 1")


async def create_payment(session: AsyncSession) -> None:
    session.add(Payment())


async def nested_transaction_owner(session: AsyncSession) -> None:
    await session.commit()


@router.post("/safe-reservations")
async def create_safe_reservation(session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        session.add(Reservation())
        session.add(StockLock())
        await session.flush()


@router.post("/unsafe-multi-write")
async def create_without_transaction(session: AsyncSession = Depends(get_async_session)):
    session.add(Reservation())
    session.add(StockLock())


@router.post("/side-effect")
async def side_effect_inside_transaction(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_async_session),
):
    async with session.begin():
        session.add(Reservation())
        background_tasks.add_task(send_confirmation, "reservation_1")


@router.post("/async-sync-mismatch")
async def async_route_with_sync_session(session: Session = Depends(get_sync_session)):
    with session.begin():
        session.add(Reservation())


@router.post("/sync-async-mismatch")
def sync_route_with_async_session(session: AsyncSession = Depends(get_async_session)):
    with session.begin():
        session.add(Reservation())


@router.post("/shared-session")
async def shared_async_session(session: AsyncSession = Depends(get_async_session)):
    await asyncio.gather(
        reserve_stock(session, "item_1"),
        create_payment(session),
    )


@router.post("/multiple-owners")
async def multiple_transaction_owners(session: AsyncSession = Depends(get_async_session)):
    async with session.begin():
        session.add(Reservation())
        await nested_transaction_owner(session)


@router.post("/commit-before-complete")
async def commit_before_complete(session: AsyncSession = Depends(get_async_session)):
    await session.commit()
    session.add(Reservation())
