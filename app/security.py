# Protecao CSRF das rotas POST de sessao (o webhook do MP e isento: quem
# autentica ele e a assinatura x-signature, nao o cookie de sessao).
#
# O token vive na sessao (cookie assinado com SECRET_KEY) e vai para o browser
# no atributo hx-headers do <body> em base.html, entao todo request do HTMX ja
# manda o header sozinho. A unica chamada fora do HTMX e o fetch("/pagar") do
# Checkout Bricks, que manda o header explicitamente (partials/checkout.html).
#
# O /admin (SQLAdmin) NAO passa por aqui: os forms dele sao proprios da lib e
# nao carregam nosso token. A defesa la e o SameSite=Lax do cookie de sessao,
# que impede o browser de mandar o cookie num POST vindo de outro site.

import secrets

from fastapi import HTTPException, Request

CHAVE_SESSAO = "csrf_token"
HEADER = "X-CSRF-Token"


def obter_csrf_token(request: Request) -> str:
    """Token da sessao atual, criado na primeira renderizacao que precisar dele."""
    token = request.session.get(CHAVE_SESSAO)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CHAVE_SESSAO] = token
    return token


async def verificar_csrf(request: Request) -> None:
    esperado = request.session.get(CHAVE_SESSAO)
    enviado = request.headers.get(HEADER, "")
    if not esperado or not secrets.compare_digest(esperado, enviado):
        raise HTTPException(status_code=403, detail="CSRF token invalido ou ausente")
