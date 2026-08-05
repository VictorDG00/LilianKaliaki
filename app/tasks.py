# Loop asyncio de expiração de reservas pendentes (sem Celery/cron externo)

import asyncio
from datetime import datetime

from sqlmodel import update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import SessionLocal
from app.models import Reserva, StatusReserva


async def expirar_reservas_uma_vez(session: AsyncSession) -> None:
    await session.exec(
        update(Reserva)
        .where(Reserva.status == StatusReserva.PENDENTE, Reserva.expira_em < datetime.utcnow())
        .values(status=StatusReserva.EXPIRADA)
    )
    await session.commit()


async def expirar_reservas_loop() -> None:
    while True:
        await asyncio.sleep(60)
        async with SessionLocal() as session:
            await expirar_reservas_uma_vez(session)
