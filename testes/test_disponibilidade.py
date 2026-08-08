"""Disponibilidade: semana recorrente, ausencias e a hierarquia de horarios.

O que esta travado aqui e a regra de negocio do agendamento — dia desligado e
periodo bloqueado nao podem, em hipotese nenhuma, oferecer horario ao cliente.
"""

from datetime import date, datetime, time, timedelta

import pytest
from sqlmodel import select

from app.agenda import erro_nos_intervalos, horarios_livres
from app.models import Ausencia, Disponibilidade, Servico
from testes.test_admin import admin  # noqa: F401  (fixture)


def _proxima(weekday: int) -> date:
    """Proxima data futura com esse dia da semana (nunca hoje: slots passados
    do dia corrente sao descartados e o teste ficaria dependendo da hora)."""
    dia = date.today() + timedelta(days=1)
    while dia.weekday() != weekday:
        dia += timedelta(days=1)
    return dia


async def _seed(session, ativo=True, weekday=None):
    dia = _proxima(weekday if weekday is not None else (date.today() + timedelta(days=1)).weekday())
    servico = Servico(titulo="Corte", duracao_min=60, preco=100.0, ativo=True)
    session.add(servico)
    session.add(
        Disponibilidade(
            dia_semana=dia.weekday(), hora_inicio=time(9, 0), hora_fim=time(12, 0), ativo=ativo
        )
    )
    await session.commit()
    await session.refresh(servico)
    return servico, dia


async def test_dia_ativo_oferece_horarios(session):
    servico, dia = await _seed(session)

    slots = await horarios_livres(session, servico, dia)

    assert [s.strftime("%H:%M") for s in slots] == ["09:00", "10:00", "11:00"]


async def test_dia_desligado_nao_oferece_nada(session):
    """O toggle desliga o dia sem apagar o horario cadastrado."""
    servico, dia = await _seed(session, ativo=False)

    assert await horarios_livres(session, servico, dia) == []
    # e o intervalo continua no banco, so que inativo
    assert len((await session.exec(select(Disponibilidade))).all()) == 1


async def test_ausencia_bloqueia_o_dia_inteiro(session):
    servico, dia = await _seed(session)
    session.add(Ausencia(data_inicio=dia, data_fim=dia, motivo="Férias"))
    await session.commit()

    assert await horarios_livres(session, servico, dia) == []


async def test_ausencia_em_intervalo_pega_os_dias_do_meio(session):
    servico, dia = await _seed(session)
    session.add(Ausencia(data_inicio=dia - timedelta(days=2), data_fim=dia + timedelta(days=2)))
    await session.commit()

    assert await horarios_livres(session, servico, dia) == []


async def test_dia_fora_da_ausencia_continua_livre(session):
    servico, dia = await _seed(session)
    session.add(
        Ausencia(data_inicio=dia + timedelta(days=1), data_fim=dia + timedelta(days=3))
    )
    await session.commit()

    assert await horarios_livres(session, servico, dia) != []


@pytest.mark.parametrize(
    "intervalos,tem_erro",
    [
        ([(time(9, 0), time(12, 0))], False),
        ([(time(9, 0), time(12, 0)), (time(14, 0), time(18, 0))], False),
        ([(time(12, 0), time(9, 0))], True),  # fim antes do inicio
        ([(time(9, 0), time(9, 0))], True),  # intervalo de duracao zero
        ([(time(9, 0), time(12, 0)), (time(11, 0), time(13, 0))], True),  # sobreposto
    ],
)
def test_validacao_de_intervalos(intervalos, tem_erro):
    assert (erro_nos_intervalos(intervalos) is not None) is tem_erro


async def test_tela_de_horarios_salva_a_semana(admin, session):  # noqa: F811
    resposta = await admin.post(
        "/admin/horarios/semana",
        data={
            "dia_0_ativo": "on",
            "dia_0_inicio": ["09:00", "14:00"],
            "dia_0_fim": ["12:00", "18:00"],
            "dia_3_inicio": "10:00",  # sem o toggle: fica inativo
            "dia_3_fim": "11:00",
        },
    )

    assert resposta.status_code == 200
    intervalos = (await session.exec(select(Disponibilidade))).all()
    segunda = [i for i in intervalos if i.dia_semana == 0]
    quinta = [i for i in intervalos if i.dia_semana == 3]
    assert len(segunda) == 2 and all(i.ativo for i in segunda)
    assert len(quinta) == 1 and not quinta[0].ativo


async def test_tela_recusa_sobreposicao_e_nao_grava(admin, session):  # noqa: F811
    resposta = await admin.post(
        "/admin/horarios/semana",
        data={
            "dia_1_ativo": "on",
            "dia_1_inicio": ["09:00", "11:00"],
            "dia_1_fim": ["12:00", "13:00"],
        },
    )

    assert "se sobrepondo" in resposta.text
    assert (await session.exec(select(Disponibilidade))).all() == []


async def test_ausencia_de_um_dia_so_e_removivel(admin, session):  # noqa: F811
    amanha = (date.today() + timedelta(days=1)).isoformat()

    await admin.post("/admin/horarios/ausencia", data={"data_inicio": amanha, "motivo": "Consulta"})
    ausencia = (await session.exec(select(Ausencia))).one()
    assert ausencia.data_fim == ausencia.data_inicio  # fim vazio = mesmo dia

    await admin.post(f"/admin/horarios/ausencia/{ausencia.id}/remover")
    assert (await session.exec(select(Ausencia))).all() == []


async def test_horario_da_reserva_ativa_some_da_lista(session):
    from app.models import Reserva, StatusReserva

    servico, dia = await _seed(session)
    from app.models import Contato

    contato = Contato(nome="Ana", email="ana@example.com", telefone="11999999999")
    session.add(contato)
    await session.flush()
    session.add(
        Reserva(
            servico_id=servico.id,
            contato_id=contato.id,
            data_hora=datetime.combine(dia, time(10, 0)),
            status=StatusReserva.PENDENTE,
            expira_em=datetime.utcnow() + timedelta(minutes=15),
        )
    )
    await session.commit()

    slots = await horarios_livres(session, servico, dia)

    assert [s.strftime("%H:%M") for s in slots] == ["09:00", "11:00"]
