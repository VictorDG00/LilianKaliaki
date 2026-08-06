"""POST de sessao exige o token CSRF; o webhook do Mercado Pago e a unica isencao."""

import hashlib
import hmac
from datetime import datetime

import app.routes_webhook as routes_webhook
from app.config import settings


def _signature(data_id, request_id, ts, secret):
    manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={v1}"


class _FakeSDK:
    """Pagamento nao aprovado — aqui so importa que o request passe do CSRF."""

    def __init__(self, access_token):
        pass

    def payment(self):
        return self

    def get(self, payment_id):
        return {"response": {}}


async def test_reservar_sem_token_csrf_e_recusado(client):
    resp = await client.post(
        "/reservar",
        data={
            "servico_id": 1,
            "data_hora": "2030-01-01T10:00:00",
            "nome": "Ana",
            "email": "ana@example.com",
            "telefone": "11999999999",
        },
        headers={"X-CSRF-Token": ""},
    )

    assert resp.status_code == 403


async def test_comprar_com_token_de_outra_sessao_e_recusado(client):
    resp = await client.post(
        "/comprar",
        data={
            "produto_id": 1,
            "nome": "Ana",
            "email": "ana@example.com",
            "telefone": "11999999999",
        },
        headers={"X-CSRF-Token": "token-de-outra-sessao"},
    )

    assert resp.status_code == 403


async def test_webhook_nao_exige_csrf(client, monkeypatch):
    """Quem autentica o webhook e a assinatura x-signature, nao o cookie de sessao."""
    monkeypatch.setattr(routes_webhook.mercadopago, "SDK", _FakeSDK)

    ts = str(int(datetime.utcnow().timestamp()))
    data_id = "123456"
    sig = _signature(data_id, "req-1", ts, settings.MERCADO_PAGO_WEBHOOK_SECRET)

    resp = await client.post(
        "/webhook/mercadopago",
        json={"data": {"id": data_id}},
        headers={"x-signature": sig, "x-request-id": "req-1", "X-CSRF-Token": ""},
    )

    assert resp.status_code == 200
