# Endpoints HTMX para a página pública e reservas

import logging
from datetime import date, datetime, timedelta

import mercadopago
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.database import get_session
from app.precos import preco_da_referencia
from app.security import obter_csrf_token, verificar_csrf
from app.models import (
    Contato,
    Disponibilidade,
    Pedido,
    Post,
    Produto,
    Reserva,
    StatusPedido,
    StatusReserva,
    Servico,
)

router = APIRouter()
# O context processor injeta csrf_token em todo template renderizado, sem
# precisar repetir a chave em cada TemplateResponse.
templates = Jinja2Templates(
    directory="templates",
    context_processors=[lambda request: {"csrf_token": obter_csrf_token(request)}],
)
logger = logging.getLogger(__name__)

RESERVA_ATIVA = (StatusReserva.PENDENTE, StatusReserva.CONFIRMADA)

POSTS_NA_HOME = 3


def _posts_publicados(limit: int | None = None):
    """Rascunho (publicado=False) nunca sai daqui — guardrail 6 da sprint_0.4."""
    consulta = (
        select(Post).where(Post.publicado == True).order_by(Post.publicado_em.desc())  # noqa: E712
    )
    return consulta.limit(limit) if limit else consulta


async def _upsert_contato(
    session: AsyncSession, nome: str, email: str, telefone: str, consentimento_marketing: bool
) -> Contato:
    contato = (await session.exec(select(Contato).where(Contato.email == email))).first()
    if contato is None:
        contato = Contato(
            nome=nome, email=email, telefone=telefone, consentimento_marketing=consentimento_marketing
        )
        session.add(contato)
    else:
        contato.nome = nome
        contato.telefone = telefone
        contato.consentimento_marketing = consentimento_marketing
    await session.flush()
    return contato


@router.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    servicos = (await session.exec(select(Servico).where(Servico.ativo == True))).all()
    produtos = (await session.exec(select(Produto).where(Produto.ativo == True))).all()
    posts = (await session.exec(_posts_publicados(POSTS_NA_HOME))).all()
    return templates.TemplateResponse(
        request, "index.html", {"servicos": servicos, "produtos": produtos, "posts": posts}
    )


@router.get("/blog")
async def blog(request: Request, session: AsyncSession = Depends(get_session)):
    posts = (await session.exec(_posts_publicados())).all()
    return templates.TemplateResponse(request, "blog.html", {"posts": posts})


@router.get("/blog/{slug}")
async def post_detalhe(
    request: Request, slug: str, session: AsyncSession = Depends(get_session)
):
    post = (await session.exec(select(Post).where(Post.slug == slug))).first()
    if post is None or not post.publicado:
        # rascunho responde 404 igual a slug inexistente: nao vaza a existencia do post
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "post.html", {"post": post})


@router.get("/agendar/passo-data")
async def agendar_passo_data(
    request: Request, servico_id: int, session: AsyncSession = Depends(get_session)
):
    servico = await session.get(Servico, servico_id)
    if servico is None or not servico.ativo:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": "Serviço indisponível."}, status_code=400
        )
    return templates.TemplateResponse(request, "partials/drawer_data.html", {"servico": servico})


@router.get("/agendar/passo-horarios")
async def agendar_passo_horarios(
    request: Request,
    servico_id: int,
    data_str: str,
    session: AsyncSession = Depends(get_session),
):
    servico = await session.get(Servico, servico_id)
    if servico is None or not servico.ativo:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": "Serviço indisponível."}, status_code=400
        )

    data = date.fromisoformat(data_str)
    weekday = data.weekday()
    disponibilidades = (
        await session.exec(select(Disponibilidade).where(Disponibilidade.dia_semana == weekday))
    ).all()

    duracao = timedelta(minutes=servico.duracao_min)
    candidatos = []
    for disp in disponibilidades:
        slot = datetime.combine(data, disp.hora_inicio)
        fim = datetime.combine(data, disp.hora_fim)
        while slot + duracao <= fim:
            candidatos.append(slot)
            slot += duracao

    dia_inicio = datetime.combine(data, datetime.min.time())
    dia_fim = dia_inicio + timedelta(days=1)
    ocupados = set(
        (
            await session.exec(
                select(Reserva.data_hora).where(
                    Reserva.servico_id == servico_id,
                    Reserva.status.in_(RESERVA_ATIVA),
                    Reserva.data_hora >= dia_inicio,
                    Reserva.data_hora < dia_fim,
                )
            )
        ).all()
    )

    # Os candidatos vem de Disponibilidade (hora de parede do negocio), entao a
    # comparacao tem que ser com a hora local — datetime.utcnow() escondia os
    # horarios das proximas 3h (offset do fuso) no mesmo dia.
    agora = datetime.now()
    slots = [s for s in candidatos if s not in ocupados and s >= agora]

    return templates.TemplateResponse(
        request,
        "partials/horarios_list.html",
        {"servico": servico, "data_str": data_str, "slots": slots},
    )


@router.get("/agendar/passo-form")
async def agendar_passo_form(
    request: Request,
    servico_id: int,
    data_hora: datetime,
    session: AsyncSession = Depends(get_session),
):
    servico = await session.get(Servico, servico_id)
    if servico is None or not servico.ativo:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": "Serviço indisponível."}, status_code=400
        )
    return templates.TemplateResponse(
        request, "partials/drawer_form.html", {"servico": servico, "data_hora": data_hora}
    )


@router.post("/reservar", dependencies=[Depends(verificar_csrf)])
async def reservar(
    request: Request,
    servico_id: int = Form(...),
    data_hora: datetime = Form(...),
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(...),
    consentimento_marketing: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    servico = await session.get(Servico, servico_id)
    if servico is None or not servico.ativo:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": "Serviço indisponível."}, status_code=400
        )

    contato = await _upsert_contato(session, nome, email, telefone, consentimento_marketing)

    slot_ocupado = (
        await session.exec(
            select(Reserva)
            .where(
                Reserva.servico_id == servico_id,
                Reserva.data_hora == data_hora,
                Reserva.status.in_(RESERVA_ATIVA),
            )
            .with_for_update()
        )
    ).first()
    if slot_ocupado is not None:
        await session.rollback()
        return templates.TemplateResponse(
            request,
            "partials/erro.html",
            {
                "mensagem": "Esse horário acabou de ser reservado. Escolha outro.",
                "voltar_servico_id": servico_id,
                "voltar_data_str": data_hora.date().isoformat(),
            },
            status_code=409,
        )

    reserva = Reserva(
        servico_id=servico_id,
        contato_id=contato.id,
        data_hora=data_hora,
        status=StatusReserva.PENDENTE,
        expira_em=datetime.utcnow() + timedelta(minutes=15),
    )
    session.add(reserva)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return templates.TemplateResponse(
            request,
            "partials/erro.html",
            {
                "mensagem": "Esse horário acabou de ser reservado. Escolha outro.",
                "voltar_servico_id": servico_id,
                "voltar_data_str": data_hora.date().isoformat(),
            },
            status_code=409,
        )

    await session.refresh(reserva)

    return templates.TemplateResponse(
        request,
        "partials/checkout.html",
        {
            "amount": servico.preco,
            "external_reference": f"reserva:{reserva.id}",
            "public_key": settings.MERCADO_PAGO_PUBLIC_KEY,
            "titulo": "Reserva criada",
            "mensagem": "Finalize o pagamento para confirmar seu horário (a reserva expira em 15 minutos).",
            "servico_id": servico_id,
        },
    )


@router.post("/comprar", dependencies=[Depends(verificar_csrf)])
async def comprar(
    request: Request,
    produto_id: int = Form(...),
    nome: str = Form(...),
    email: str = Form(...),
    telefone: str = Form(...),
    consentimento_marketing: bool = Form(False),
    session: AsyncSession = Depends(get_session),
):
    produto = await session.get(Produto, produto_id)
    if produto is None or not produto.ativo:
        return templates.TemplateResponse(
            request, "partials/erro.html", {"mensagem": "Produto indisponível."}, status_code=400
        )

    contato = await _upsert_contato(session, nome, email, telefone, consentimento_marketing)

    pedido = Pedido(produto_id=produto_id, contato_id=contato.id, status=StatusPedido.PENDENTE)
    session.add(pedido)
    await session.commit()
    await session.refresh(pedido)

    return templates.TemplateResponse(
        request,
        "partials/checkout.html",
        {
            "amount": produto.preco,
            "external_reference": f"pedido:{pedido.id}",
            "public_key": settings.MERCADO_PAGO_PUBLIC_KEY,
            "titulo": "Pedido criado",
            "mensagem": "Finalize o pagamento para confirmar sua compra.",
        },
    )


@router.post("/pagar", dependencies=[Depends(verificar_csrf)])
async def pagar(request: Request, session: AsyncSession = Depends(get_session)):
    payload = await request.json()
    external_reference = payload.pop("external_reference", None)
    if not external_reference:
        return {"status": "rejected"}

    # O valor e definido AQUI, no servidor. O payload do navegador so escolhe
    # COMO paga (cartao, parcelas, token do Brick), nunca QUANTO.
    valor = await preco_da_referencia(session, external_reference)
    if valor is None:
        return {"status": "rejected"}

    sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
    payload["external_reference"] = external_reference
    payload["transaction_amount"] = float(valor)
    payload_log = {**payload, "token": "***"} if "token" in payload else payload
    logger.info("Enviando pagamento para o MP: %s", payload_log)
    try:
        resp = sdk.payment().create(payload)
        corpo = resp.get("response", {})
        # resp["status"] é o status HTTP da chamada; resp["response"]["status"]
        # só é o status do pagamento (approved/pending/rejected) quando a
        # chamada deu certo — em erro, o corpo do MP também tem um campo
        # "status" com o código HTTP repetido, então não dá pra confiar nele
        # sem checar o status HTTP primeiro.
        if resp.get("status", 500) >= 300:
            logger.warning("Pagamento nao aprovado: %s", corpo)
            status = "rejected"
        else:
            status = corpo.get("status", "rejected")
    except Exception:
        logger.exception("Falha ao chamar sdk.payment().create()")
        status = "rejected"

    return {"status": status}
