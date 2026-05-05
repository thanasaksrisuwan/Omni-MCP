from sqlalchemy.ext.asyncio import AsyncSession


class Reservation:
    pass


async def service_hidden_commit(session: AsyncSession) -> None:
    session.add(Reservation())
    await session.commit()
