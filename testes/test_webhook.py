import hashlib
import hmac
from datetime import datetime, timedelta

import app.routes_webhook as routes_webhook
from app.config import settings
from app.models import Contato, Reserva, Servico, StatusReserva


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


async def _seed_reserva(session):
    servico = Servico(titulo="Corte", duracao_min=30, preco=100.0, ativo=True)
    session.add(servico)
    await session.flush()
    contato = Contato(nome="Ana", email="ana@example.com", telefone="11999999999")
    session.add(contato)
    await session.flush()
    reserva = Reserva(
        servico_id=servico.id,
        contato_id=contato.id,
        data_hora=datetime.utcnow() + timedelta(days=1),
        status=StatusReserva.PENDENTE,
        expira_em=datetime.utcnow() + timedelta(minutes=15),
    )
    session.add(reserva)
    await session.commit()
    await session.refresh(reserva)
    return reserva


async def test_assinatura_valida_confirma_reserva(client, session, monkeypatch):
    reserva = await _seed_reserva(session)
    _FakeSDK.response = {"status": "approved", "external_reference": str(reserva.id)}
    monkeypatch.setattr(routes_webhook.mercadopago, "SDK", _FakeSDK)

    ts = str(int(datetime.utcnow().timestamp()))
    data_id = "123456"
    sig = _signature(data_id, "req-1", ts, settings.MERCADO_PAGO_WEBHOOK_SECRET)

    resp = await client.post(
        "/webhook/mercadopago",
        json={"data": {"id": data_id}},
        headers={"x-signature": sig, "x-request-id": "req-1"},
    )
    assert resp.status_code == 200

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.CONFIRMADA
    assert reserva.mp_payment_id == data_id


async def test_assinatura_invalida_retorna_401_e_nao_altera_banco(client, session, monkeypatch):
    reserva = await _seed_reserva(session)
    _FakeSDK.response = {"status": "approved", "external_reference": str(reserva.id)}
    monkeypatch.setattr(routes_webhook.mercadopago, "SDK", _FakeSDK)

    resp = await client.post(
        "/webhook/mercadopago",
        json={"data": {"id": "123456"}},
        headers={"x-signature": "ts=123,v1=assinatura-errada", "x-request-id": "req-1"},
    )
    assert resp.status_code == 401

    await session.refresh(reserva)
    assert reserva.status == StatusReserva.PENDENTE
    assert reserva.mp_payment_id is None


async def test_assinatura_ausente_retorna_401(client, session, monkeypatch):
    reserva = await _seed_reserva(session)
    resp = await client.post("/webhook/mercadopago", json={"data": {"id": "123456"}})
    assert resp.status_code == 401
    await session.refresh(reserva)
    assert reserva.status == StatusReserva.PENDENTE


async def test_replay_do_mesmo_payment_id_e_idempotente(client, session, monkeypatch):
    reserva = await _seed_reserva(session)
    _FakeSDK.response = {"status": "approved", "external_reference": str(reserva.id)}
    monkeypatch.setattr(routes_webhook.mercadopago, "SDK", _FakeSDK)

    ts = str(int(datetime.utcnow().timestamp()))
    data_id = "123456"
    headers = {
        "x-signature": _signature(data_id, "req-1", ts, settings.MERCADO_PAGO_WEBHOOK_SECRET),
        "x-request-id": "req-1",
    }

    resp1 = await client.post("/webhook/mercadopago", json={"data": {"id": data_id}}, headers=headers)
    resp2 = await client.post("/webhook/mercadopago", json={"data": {"id": data_id}}, headers=headers)

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    await session.refresh(reserva)
    assert reserva.status == StatusReserva.CONFIRMADA
    assert reserva.mp_payment_id == data_id
