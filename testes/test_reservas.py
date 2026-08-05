import asyncio
from datetime import date, datetime, time, timedelta

from sqlmodel import select

from app.models import Contato, Disponibilidade, Reserva, Servico, StatusReserva


async def _seed_servico(session, duracao_min=30, preco=100.0):
    amanha = date.today() + timedelta(days=1)
    servico = Servico(
        titulo="Corte", descricao="Corte de cabelo", duracao_min=duracao_min, preco=preco, ativo=True
    )
    session.add(servico)
    await session.flush()
    disponibilidade = Disponibilidade(
        dia_semana=amanha.weekday(), hora_inicio=time(8, 0), hora_fim=time(18, 0)
    )
    session.add(disponibilidade)
    await session.commit()
    slot = datetime.combine(amanha, time(9, 0))
    return servico, slot


async def test_reserva_concorrente_so_uma_tem_sucesso(client, session):
    servico, slot = await _seed_servico(session)
    base = {"servico_id": servico.id, "data_hora": slot.isoformat(), "telefone": "11999999999"}

    resp1, resp2 = await asyncio.gather(
        client.post("/reservar", data={**base, "nome": "Ana", "email": "ana@example.com"}),
        client.post("/reservar", data={**base, "nome": "Bruno", "email": "bruno@example.com"}),
    )

    assert sorted([resp1.status_code, resp2.status_code]) == [200, 409]

    reservas = (
        await session.exec(
            select(Reserva).where(Reserva.servico_id == servico.id, Reserva.data_hora == slot)
        )
    ).all()
    assert len(reservas) == 1


async def test_reagendamento_de_slot_expirado_libera_horario(client, session):
    servico, slot = await _seed_servico(session)
    contato = Contato(nome="Ana", email="ana@example.com", telefone="11999999999")
    session.add(contato)
    await session.flush()
    session.add(
        Reserva(
            servico_id=servico.id,
            contato_id=contato.id,
            data_hora=slot,
            status=StatusReserva.EXPIRADA,
            expira_em=datetime.utcnow() - timedelta(minutes=1),
        )
    )
    await session.commit()

    resp = await client.post(
        "/reservar",
        data={
            "servico_id": servico.id,
            "data_hora": slot.isoformat(),
            "nome": "Bruno",
            "email": "bruno@example.com",
            "telefone": "11988888888",
        },
    )
    assert resp.status_code == 200

    ativas = (
        await session.exec(
            select(Reserva).where(
                Reserva.servico_id == servico.id,
                Reserva.data_hora == slot,
                Reserva.status.in_([StatusReserva.PENDENTE, StatusReserva.CONFIRMADA]),
            )
        )
    ).all()
    assert len(ativas) == 1


async def test_mesmo_email_nao_duplica_contato(client, session):
    servico, slot = await _seed_servico(session)
    slot2 = slot + timedelta(minutes=servico.duracao_min)
    email = "carla@example.com"

    resp1 = await client.post(
        "/reservar",
        data={
            "servico_id": servico.id,
            "data_hora": slot.isoformat(),
            "nome": "Carla",
            "email": email,
            "telefone": "11977777777",
        },
    )
    resp2 = await client.post(
        "/reservar",
        data={
            "servico_id": servico.id,
            "data_hora": slot2.isoformat(),
            "nome": "Carla",
            "email": email,
            "telefone": "11977777777",
        },
    )

    assert resp1.status_code == 200
    assert resp2.status_code == 200

    contatos = (await session.exec(select(Contato).where(Contato.email == email))).all()
    assert len(contatos) == 1
