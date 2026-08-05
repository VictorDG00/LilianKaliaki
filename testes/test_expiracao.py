from datetime import datetime, timedelta

from app.models import Contato, Reserva, Servico, StatusReserva
from app.tasks import expirar_reservas_uma_vez


async def test_reserva_pendente_vencida_vira_expirada(session):
    servico = Servico(titulo="Corte", duracao_min=30, preco=100.0, ativo=True)
    session.add(servico)
    await session.flush()
    contato = Contato(nome="Ana", email="ana@example.com", telefone="11999999999")
    session.add(contato)
    await session.flush()
    reserva = Reserva(
        servico_id=servico.id,
        contato_id=contato.id,
        data_hora=datetime.utcnow() + timedelta(days=1),
        status=StatusReserva.PENDENTE,
        expira_em=datetime.utcnow() - timedelta(minutes=1),
    )
    session.add(reserva)
    await session.commit()

    await expirar_reservas_uma_vez(session)

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.EXPIRADA


async def test_reserva_pendente_nao_vencida_permanece(session):
    servico = Servico(titulo="Corte", duracao_min=30, preco=100.0, ativo=True)
    session.add(servico)
    await session.flush()
    contato = Contato(nome="Ana", email="ana2@example.com", telefone="11999999999")
    session.add(contato)
    await session.flush()
    reserva = Reserva(
        servico_id=servico.id,
        contato_id=contato.id,
        data_hora=datetime.utcnow() + timedelta(days=1),
        status=StatusReserva.PENDENTE,
        expira_em=datetime.utcnow() + timedelta(minutes=15),
    )
    session.add(reserva)
    await session.commit()

    await expirar_reservas_uma_vez(session)

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.PENDENTE
