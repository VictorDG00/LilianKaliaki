# Endpoint para Webhook do Mercado Pago (com verificação)

import hashlib
import hmac
import logging

import mercadopago
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import settings
from app.database import get_session
from app.models import Pedido, Reserva, StatusPedido, StatusReserva
from app.precos import preco_da_referencia

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook/mercadopago")
async def mercadopago_webhook(request: Request, session: AsyncSession = Depends(get_session)):
    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")
    body = await request.json()
    data_id = str(body.get("data", {}).get("id", ""))

    partes = dict(p.split("=", 1) for p in x_signature.split(",") if "=" in p)
    ts, v1 = partes.get("ts"), partes.get("v1")
    if not ts or not v1 or not data_id:
        raise HTTPException(status_code=401)

    manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    esperado = hmac.new(
        settings.MERCADO_PAGO_WEBHOOK_SECRET.encode(), manifest.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(esperado, v1):
        raise HTTPException(status_code=401)

    sdk = mercadopago.SDK(settings.MERCADO_PAGO_ACCESS_TOKEN)
    pagamento = sdk.payment().get(data_id)["response"]
    if pagamento.get("status") != "approved":
        return {"status": "ignored"}

    external_reference = pagamento.get("external_reference") or ""
    tipo, _, id_str = external_reference.partition(":")
    if not id_str.isdigit():
        return {"status": "ignored"}

    # Segunda tranca do valor: /pagar ja manda o preco do banco, mas quem
    # confirma a venda e esta rota, e ela nao confia no que veio de fora.
    # Valor diferente do esperado nao confirma nada — fica para olho humano.
    valor_esperado = await preco_da_referencia(session, external_reference)
    if valor_esperado is not None and float(pagamento.get("transaction_amount") or 0) != float(
        valor_esperado
    ):
        logger.warning(
            "Pagamento %s aprovado com valor divergente (%s, esperado %s): %s",
            data_id, pagamento.get("transaction_amount"), valor_esperado, external_reference,
        )
        return {"status": "ignored"}

    if tipo == "reserva":
        reserva = await session.get(Reserva, int(id_str))
        if reserva is None:
            return {"status": "ignored"}
        if reserva.status == StatusReserva.CONFIRMADA and reserva.mp_payment_id == data_id:
            return {"status": "ok"}
        reserva.status = StatusReserva.CONFIRMADA
        reserva.mp_payment_id = data_id
        session.add(reserva)
        await session.commit()
        return {"status": "ok"}

    if tipo == "pedido":
        pedido = await session.get(Pedido, int(id_str))
        if pedido is None:
            return {"status": "ignored"}
        if pedido.status == StatusPedido.CONFIRMADO and pedido.mp_payment_id == data_id:
            return {"status": "ok"}
        pedido.status = StatusPedido.CONFIRMADO
        pedido.mp_payment_id = data_id
        session.add(pedido)
        await session.commit()
        return {"status": "ok"}

    return {"status": "ignored"}
