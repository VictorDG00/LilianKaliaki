"""Travas do que ja esta validado em producao (sprint_0.4, secao 6).

Se um teste daqui quebrar, e regressao — nao "teste desatualizado".
"""

from pathlib import Path

from fastapi.routing import APIRoute

import app.routes_public as routes_public
import app.routes_webhook as routes_webhook
from app.config import Settings
from app.main import app
from app.models import Post

# Routers proprios do app. Um router novo que nao entre aqui ainda e pego pelo
# openapi(), desde que as rotas dele apareçam no schema.
ROUTERS_DO_APP = (routes_public.router, routes_webhook.router)

# Guardrail 1: as unicas rotas de escrita do app. Qualquer POST/PUT/PATCH/DELETE
# novo tem que ser adicionado aqui CONSCIENTEMENTE, num PR que explique por que.
#
# Escopo: rotas publicas. As telas do admin (fotos, horarios, acoes de reserva)
# vivem num sub-app montado pelo SQLAdmin e nao aparecem aqui — quem protege
# elas e o AdminAuth mais o cookie same_site=lax, que nao viaja em POST
# cross-site. Se um dia o admin ganhar rota que mexa em dinheiro, ela precisa
# de guardrail proprio.
ROTAS_DE_ESCRITA_CONHECIDAS = {
    ("/reservar", "POST"),
    ("/comprar", "POST"),
    ("/pagar", "POST"),
    ("/webhook/mercadopago", "POST"),
}

METODOS_DE_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}


def _escrita_pelo_openapi() -> set:
    """Fonte 1: o schema OpenAPI — API publica, enxerga qualquer router incluido.

    Ponto cego: rota declarada com include_in_schema=False nao aparece aqui.
    """
    return {
        (caminho, metodo.upper())
        for caminho, operacoes in app.openapi()["paths"].items()
        for metodo in operacoes
        if metodo.upper() in METODOS_DE_ESCRITA
    }


def _escrita_pelos_routers() -> set:
    """Fonte 2: o atributo publico .routes do app e dos nossos APIRouters.

    Cobre o ponto cego do openapi (include_in_schema=False). Nao percorre a
    arvore de app.routes de proposito: os routers incluidos viram um objeto
    interno do FastAPI, e depender do formato dele deixaria o guardrail refem
    de detalhe de versao. Aqui so se usa atributo publico.

    Os Mounts /admin (SQLAdmin) e /static ficam de fora naturalmente: nao sao
    APIRoute.
    """
    candidatas = list(app.routes) + [r for router in ROUTERS_DO_APP for r in router.routes]
    return {
        (rota.path, metodo)
        for rota in candidatas
        if isinstance(rota, APIRoute)
        for metodo in rota.methods
        if metodo in METODOS_DE_ESCRITA
    }


def rotas_de_escrita() -> set:
    return _escrita_pelo_openapi() | _escrita_pelos_routers()


def test_as_duas_fontes_enxergam_rotas():
    """Trava do proprio guardrail: fonte que volta vazia nao protege nada.

    Se uma versao futura do FastAPI mudar openapi() ou .routes, isto quebra
    antes de o guardrail virar decoracao que aprova tudo em silencio.
    """
    assert _escrita_pelo_openapi()
    assert _escrita_pelos_routers()


def test_nenhuma_rota_de_escrita_inesperada():
    """O blog e so leitura: se ele ganhar um POST, este teste quebra."""
    assert rotas_de_escrita() == ROTAS_DE_ESCRITA_CONHECIDAS


def test_post_nao_tem_campo_de_preco_nem_status():
    """Guardrail 1: e o que diferencia Post de Produto e impede o blog de vender."""
    campos = set(Post.model_fields)

    assert not campos & {"preco", "status", "estoque", "mp_payment_id"}


def test_sql_echo_desligado_por_padrao():
    """Ligado em producao, o stdout vai pro Loki com nome/email/telefone dos contatos."""
    assert Settings.model_fields["SQL_ECHO"].default is False


def test_cookie_de_sessao_exige_https_por_padrao():
    assert Settings.model_fields["SESSION_HTTPS_ONLY"].default is True


async def test_healthz_responde_200(client):
    """O healthcheck do container aponta para ca; sem isso o deploy --wait falha."""
    resposta = await client.get("/healthz")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


async def test_admin_nao_e_indexavel(client):
    resposta = await client.get("/admin/", follow_redirects=True)

    assert resposta.headers["x-robots-tag"] == "noindex, nofollow"
    assert resposta.headers["cache-control"] == "no-store"


async def test_robots_bloqueia_admin(client):
    corpo = (await client.get("/robots.txt")).text

    assert "Disallow: /admin" in corpo


def test_blog_nao_trouxe_dependencia_nova():
    """Guardrail 7: texto puro e slug com stdlib, sem lib de markdown/slug."""
    requirements = Path(__file__).resolve().parent.parent / "requirements.txt"
    conteudo = requirements.read_text().lower()

    for proibida in ("markdown", "mistune", "slugify", "bleach"):
        assert proibida not in conteudo
