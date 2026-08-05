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
from app.models import Contato, Disponibilidade, Reserva, Servico, StatusReserva

router = APIRouter()
templates = Jinja2Templates(directory="templates")

RESERVA_ATIVA = (StatusReserva.PENDENTE, StatusReserva.CONFIRMADA)


@router.get("/")
async def index(request: Request, session: AsyncSession = Depends(get_session)):
    servicos = (await session.exec(select(Servico).where(Servico.ativo == True))).all()
    return templates.TemplateResponse(request, "index.html", {"servicos": servicos})


@router.get("/horarios-livres")
async def horarios_livres(
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
            {"mensagem": "Esse horário acabou de ser reservado. Escolha outro."},
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
            {"mensagem": "Esse horário acabou de ser reservado. Escolha outro."},
            status_code=409,
        )

    await session.refresh(reserva)

    sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
    preference_resp = sdk.preference().create(
        {
            "items": [{"title": servico.titulo, "quantity": 1, "unit_price": servico.preco}],
            "external_reference": str(reserva.id),
        }
    )
    preference_id = preference_resp["response"]["id"]

    return templates.TemplateResponse(
        request,
        "partials/checkout.html",
        {
            "preference_id": preference_id,
            "public_key": settings.MERCADO_PAGO_PUBLIC_KEY,
            "reserva_id": reserva.id,
        },
    )
