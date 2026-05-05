from fastapi import APIRouter, Depends, Security
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


def get_session() -> AsyncSession:
    raise NotImplementedError


def get_current_user():
    raise NotImplementedError


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.post("/reservations")
async def create_reservation(
    session: AsyncSession = Depends(get_session),
    user=Security(get_current_user, scopes=["reservation:create"]),
):
    return {"id": "reservation_1"}


@router.patch(path="/reservations/{reservation_id}")
async def update_reservation(
    reservation_id: str,
    session: AsyncSession = Depends(get_session),
):
    return {"id": reservation_id}
