import hashlib
import hmac
from datetime import datetime

from sqlmodel import select

import app.routes_webhook as routes_webhook
from app.config import settings
from app.models import Contato, Pedido, Produto, StatusPedido


def _signature(data_id, request_id, ts, secret):
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


class _FakePayment:
    def __init__(self, response):
        self._response = response

    def get(self, payment_id):
        return {"response": self._response}


class _FakeSDK:
    response = {}

    def __init__(self, access_token):
        pass

    def payment(self):
        return _FakePayment(_FakeSDK.response)


async def _seed_produto(session):
    produto = Produto(titulo="Creme de Cabelo", descricao="Hidratação", preco=59.9, ativo=True)
    session.add(produto)
    await session.commit()
    await session.refresh(produto)
    return produto


async def test_compra_de_produto_cria_pedido_pendente(client, session):
    produto = await _seed_produto(session)

    resp = await client.post(
        "/comprar",
        data={
            "produto_id": produto.id,
            "nome": "Diana",
            "email": "diana@example.com",
            "telefone": "11966666666",
        },
    )

    assert resp.status_code == 200
    pedido = (
        await session.exec(select(Pedido).where(Pedido.produto_id == produto.id))
    ).first()
    assert pedido is not None
    assert pedido.status == StatusPedido.PENDENTE


async def test_webhook_confirma_pedido(client, session, monkeypatch):
    produto = await _seed_produto(session)
    contato = Contato(nome="Diana", email="diana@example.com", telefone="11966666666")
    session.add(contato)
    await session.flush()
    pedido = Pedido(produto_id=produto.id, contato_id=contato.id, status=StatusPedido.PENDENTE)
    session.add(pedido)
    await session.commit()
    await session.refresh(pedido)

    _FakeSDK.response = {"status": "approved", "external_reference": f"pedido:{pedido.id}"}
    monkeypatch.setattr(routes_webhook.mercadopago, "SDK", _FakeSDK)

    ts = str(int(datetime.utcnow().timestamp()))
    data_id = "987654"
    sig = _signature(data_id, "req-1", ts, settings.MERCADO_PAGO_WEBHOOK_SECRET)

    resp = await client.post(
        "/webhook/mercadopago",
        json={"data": {"id": data_id}},
        headers={"x-signature": sig, "x-request-id": "req-1"},
    )
    assert resp.status_code == 200

    await session.refresh(pedido)
    assert pedido.status == StatusPedido.CONFIRMADO
    assert pedido.mp_payment_id == data_id
