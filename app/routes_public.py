# Endpoints HTMX para a página pública e reservas

from datetime import date, datetime, timedelta

import mercadopago
from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import (
    Contato,
    Disponibilidade,
    Pedido,
    Produto,
    Reserva,
    StatusPedido,
    StatusReserva,
    Servico,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")

RESERVA_ATIVA = (StatusReserva.PENDENTE, StatusReserva.CONFIRMADA)


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
    return templates.TemplateResponse(
        request, "index.html", {"servicos": servicos, "produtos": produtos}
    )


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

    agora = datetime.utcnow()
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


@router.post("/reservar")
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
            "email": email,
            "public_key": settings.MERCADO_PAGO_PUBLIC_KEY,
            "titulo": "Reserva criada",
            "mensagem": "Finalize o pagamento para confirmar seu horário (a reserva expira em 15 minutos).",
            "servico_id": servico_id,
        },
    )


@router.post("/comprar")
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
            "email": email,
            "public_key": settings.MERCADO_PAGO_PUBLIC_KEY,
            "titulo": "Pedido criado",
            "mensagem": "Finalize o pagamento para confirmar sua compra.",
        },
    )


@router.post("/pagar")
async def pagar(request: Request):
    payload = await request.json()
    external_reference = payload.pop("external_reference", None)
    if not external_reference:
        return {"status": "rejected"}

    sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
    payload["external_reference"] = external_reference
    try:
        resp = sdk.payment().create(payload)
        status = resp.get("response", {}).get("status", "rejected")
    except Exception:
        status = "rejected"

    return {"status": status}
