"""Dashboard de reservas: abas, busca, acoes e drawer.

O teste que mais importa e o das abas — reserva na aba errada e a Lilian
perdendo cliente por nao ver que tinha alguem marcado."""

from datetime import datetime, timedelta

import pytest_asyncio
from sqlmodel import select

from app.models import Contato, Reserva, Servico, StatusReserva
from testes.test_admin import admin  # noqa: F401  (fixture)


@pytest_asyncio.fixture
async def agenda(session):
    """Uma reserva em cada estado, para as quatro abas terem conteudo."""
    servico = Servico(titulo="Corte de Cabelo", duracao_min=60, preco=120.0, ativo=True)
    contato = Contato(nome="Ana Souza", email="ana@example.com", telefone="(11) 98888-7777")
    session.add(servico)
    session.add(contato)
    await session.flush()

    agora = datetime.now()
    reservas = {
        "futura_confirmada": Reserva(
            servico_id=servico.id, contato_id=contato.id,
            data_hora=agora + timedelta(days=2), status=StatusReserva.CONFIRMADA,
            expira_em=agora + timedelta(minutes=15),
        ),
        "pendente": Reserva(
            servico_id=servico.id, contato_id=contato.id,
            data_hora=agora + timedelta(days=3), status=StatusReserva.PENDENTE,
            expira_em=agora + timedelta(minutes=15),
        ),
        "passada": Reserva(
            servico_id=servico.id, contato_id=contato.id,
            data_hora=agora - timedelta(days=2), status=StatusReserva.CONFIRMADA,
            expira_em=agora - timedelta(days=2),
        ),
        "cancelada": Reserva(
            servico_id=servico.id, contato_id=contato.id,
            data_hora=agora + timedelta(days=4), status=StatusReserva.CANCELADA,
            expira_em=agora + timedelta(minutes=15),
        ),
    }
    for reserva in reservas.values():
        session.add(reserva)
    await session.commit()
    for reserva in reservas.values():
        await session.refresh(reserva)
    return {"servico": servico, "contato": contato, **reservas}


async def _ids_na_aba(admin, aba):  # noqa: F811
    resposta = await admin.get(f"/admin/reserva/list?aba={aba}")
    assert resposta.status_code == 200
    return resposta.text


async def test_cada_aba_mostra_o_seu_recorte(admin, agenda):  # noqa: F811
    proximos = await _ids_na_aba(admin, "proximos")
    pendente = await _ids_na_aba(admin, "pendente")
    anteriores = await _ids_na_aba(admin, "anteriores")
    cancelados = await _ids_na_aba(admin, "cancelados")

    def tem(corpo, reserva):
        return f"/admin/reserva-detalhe/{reserva.id}" in corpo

    assert tem(proximos, agenda["futura_confirmada"])
    assert not tem(proximos, agenda["pendente"])  # ainda nao pago
    assert not tem(proximos, agenda["passada"])

    assert tem(pendente, agenda["pendente"])
    assert tem(anteriores, agenda["passada"])
    assert not tem(anteriores, agenda["cancelada"])
    assert tem(cancelados, agenda["cancelada"])


async def test_card_mostra_nome_e_servico_em_vez_de_id(admin, agenda):  # noqa: F811
    corpo = await _ids_na_aba(admin, "proximos")

    assert "Ana Souza" in corpo
    assert "Corte de Cabelo" in corpo
    # o telefone vira link de WhatsApp so com digitos
    assert "https://wa.me/5511988887777" in corpo


async def test_busca_por_nome_do_cliente(admin, agenda):  # noqa: F811
    achou = await admin.get("/admin/reserva/list?aba=proximos&search=Ana")
    nao_achou = await admin.get("/admin/reserva/list?aba=proximos&search=Roberto")

    assert "Ana Souza" in achou.text
    assert "Ana Souza" not in nao_achou.text


async def test_confirmar_na_mao_muda_status(admin, agenda, session, caplog):  # noqa: F811
    reserva = agenda["pendente"]

    await admin.get(
        f"/admin/reserva/action/confirmar?pks={reserva.id}", follow_redirects=False
    )

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.CONFIRMADA
    # sem pagamento pelo site: tem que dar para separar isso no log
    assert reserva.mp_payment_id is None


async def test_cancelar_pelo_painel(admin, agenda, session):  # noqa: F811
    reserva = agenda["futura_confirmada"]

    await admin.get(f"/admin/reserva/action/cancelar?pks={reserva.id}", follow_redirects=False)

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.CANCELADA


async def test_drawer_traz_os_dados_completos(admin, agenda):  # noqa: F811
    reserva = agenda["futura_confirmada"]

    resposta = await admin.get(f"/admin/reserva-detalhe/{reserva.id}")

    assert resposta.status_code == 200
    assert "ana@example.com" in resposta.text
    assert "Corte de Cabelo" in resposta.text
    assert "120.00" in resposta.text or "120,00" in resposta.text


async def test_drawer_exige_login(client, agenda):
    resposta = await client.get(
        f"/admin/reserva-detalhe/{agenda['pendente'].id}", follow_redirects=False
    )

    assert resposta.status_code in (302, 303)
