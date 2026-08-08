"""Telas do painel. O admin e a ferramenta de trabalho diaria — se uma tela
destas responder 500, ninguem consegue operar o negocio."""

import os

import pytest_asyncio


@pytest_asyncio.fixture
async def admin(client):
    """Cliente com a sessao do SQLAdmin aberta."""
    await client.post(
        "/admin/login",
        data={"username": os.environ["ADMIN_USERNAME"], "password": os.environ["ADMIN_PASSWORD"]},
        follow_redirects=False,
    )
    return client


async def test_admin_exige_login(client):
    resposta = await client.get("/admin/servico/list", follow_redirects=False)

    assert resposta.status_code in (302, 303)


async def test_aba_cursos_responde_em_breve(admin):
    resposta = await admin.get("/admin/cursos")

    assert resposta.status_code == 200
    assert "Em breve" in resposta.text


async def test_form_de_servico_oferece_as_quatro_duracoes(admin):
    resposta = await admin.get("/admin/servico/create")

    assert resposta.status_code == 200
    assert "Tempo do serviço" in resposta.text
    for opcao in ("00:30", "01:00", "01:30", "02:00"):
        assert f">{opcao}<" in resposta.text, opcao


async def test_listagem_de_servico_mostra_duracao_formatada(admin, session):
    from app.models import Servico

    session.add(Servico(titulo="Corte", duracao_min=90, preco=100.0, ativo=True))
    await session.commit()

    resposta = await admin.get("/admin/servico/list")

    assert resposta.status_code == 200
    assert "01:30" in resposta.text
