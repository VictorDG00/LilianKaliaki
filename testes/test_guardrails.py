"""Travas do que ja esta validado em producao (sprint_0.4, secao 6).

Se um teste daqui quebrar, e regressao — nao "teste desatualizado".
"""

from pathlib import Path

from fastapi.routing import APIRoute
from starlette.routing import Mount

from app.config import Settings
from app.main import app
from app.models import Post

# Guardrail 1: as unicas rotas de escrita do app. Qualquer POST/PUT/PATCH/DELETE
# novo tem que ser adicionado aqui CONSCIENTEMENTE, num PR que explique por que.
ROTAS_DE_ESCRITA_CONHECIDAS = {
    ("/reservar", "POST"),
    ("/comprar", "POST"),
    ("/pagar", "POST"),
    ("/webhook/mercadopago", "POST"),
}

METODOS_DE_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}


def _rotas_de_escrita(rotas) -> set:
    """Percorre a arvore de rotas.

    O FastAPI nao achata os routers incluidos em app.routes — eles viram um
    _IncludedRouter, que guarda o APIRouter original em `original_router`.
    Uma varredura rasa nao enxerga nenhum POST. Se essa estrutura interna mudar
    numa versao futura, o test_varredura_enxerga_as_rotas_de_escrita quebra e
    avisa, em vez deste guardrail passar a aprovar tudo em silencio.

    Mount e ignorado de proposito: sao os sub-apps /admin (SQLAdmin, com forms
    proprios) e /static.
    """
    encontradas = set()
    for rota in rotas:
        if isinstance(rota, Mount):
            continue
        if isinstance(rota, APIRoute):
            encontradas |= {
                (rota.path, metodo) for metodo in rota.methods if metodo in METODOS_DE_ESCRITA
            }
        elif hasattr(rota, "original_router"):
            encontradas |= _rotas_de_escrita(rota.original_router.routes)
        elif hasattr(rota, "routes"):
            encontradas |= _rotas_de_escrita(rota.routes)
    return encontradas


def test_varredura_enxerga_as_rotas_de_escrita():
    """Trava do proprio guardrail: se a varredura voltar vazia, ela nao esta protegendo nada."""
    assert _rotas_de_escrita(app.routes)


def test_nenhuma_rota_de_escrita_inesperada():
    """O blog e so leitura: se ele ganhar um POST, este teste quebra."""
    assert _rotas_de_escrita(app.routes) == ROTAS_DE_ESCRITA_CONHECIDAS


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
