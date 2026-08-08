from datetime import datetime, timedelta

import app.routes_public as routes_public
from app.models import Contato, Reserva, Servico, StatusReserva


async def _seed_reserva(session, preco=80.0):
    """Reserva pendente de verdade: o /pagar agora le o preco do banco."""
    servico = Servico(titulo="Corte", duracao_min=30, preco=preco, ativo=True)
    contato = Contato(nome="Ana", email="ana@example.com", telefone="11999999999")
    session.add(servico)
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


class _FakePayment:
    def __init__(self):
        self.last_payload = None

    def create(self, payload):
        self.last_payload = payload
        return {"status": 201, "response": {"status": "approved", "id": "12345"}}


class _FakeSDK:
    instance = None

    def __init__(self, access_token):
        _FakeSDK.instance = self
        self._payment = _FakePayment()

    def payment(self):
        return self._payment


async def test_pagar_encaminha_external_reference_e_retorna_status(client, session, monkeypatch):
    reserva = await _seed_reserva(session)
    monkeypatch.setattr(routes_public.mercadopago, "SDK", _FakeSDK)

    resp = await client.post(
        "/pagar",
        json={
            "token": "abc",
            "payment_method_id": "visa",
            "transaction_amount": 80.0,
            "installments": 1,
            "external_reference": f"reserva:{reserva.id}",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "approved"}
    assert _FakeSDK.instance.payment().last_payload["external_reference"] == f"reserva:{reserva.id}"


async def test_valor_e_definido_no_servidor_nao_pelo_navegador(client, session, monkeypatch):
    """Se o payload do cliente mandasse o preco, dava para pagar R$ 300 por 1 centavo."""
    reserva = await _seed_reserva(session, preco=300.0)
    monkeypatch.setattr(routes_public.mercadopago, "SDK", _FakeSDK)

    resp = await client.post(
        "/pagar",
        json={
            "token": "abc",
            "transaction_amount": 0.01,
            "external_reference": f"reserva:{reserva.id}",
        },
    )

    assert resp.status_code == 200
    assert _FakeSDK.instance.payment().last_payload["transaction_amount"] == 300.0


async def test_pagar_com_referencia_inexistente_ou_ja_paga_nao_chama_o_mp(client, session, monkeypatch):
    class _NaoDeveriaSerChamado:
        def __init__(self, access_token):
            raise AssertionError("SDK nao deveria ser instanciado sem preco no banco")

    monkeypatch.setattr(routes_public.mercadopago, "SDK", _NaoDeveriaSerChamado)
    reserva = await _seed_reserva(session)
    reserva.status = StatusReserva.CONFIRMADA
    session.add(reserva)
    await session.commit()

    for referencia in ("reserva:999999", "pedido:1", "reserva:abc", "outro:1", f"reserva:{reserva.id}"):
        resp = await client.post("/pagar", json={"token": "abc", "external_reference": referencia})
        assert resp.json() == {"status": "rejected"}, referencia


async def test_pagar_erro_400_do_mp_nao_confunde_status_http_com_status_pagamento(client, session, monkeypatch):
    class _FakePaymentErro:
        def create(self, payload):
            # o corpo de erro do MP tambem tem um campo "status" (o codigo
            # HTTP repetido) - nao pode ser confundido com approved/pending
            return {"status": 400, "response": {"status": 400, "message": "erro", "cause": []}}

    class _FakeSDKErro:
        def __init__(self, access_token):
            self._payment = _FakePaymentErro()

        def payment(self):
            return self._payment

    monkeypatch.setattr(routes_public.mercadopago, "SDK", _FakeSDKErro)

    reserva = await _seed_reserva(session)
    resp = await client.post(
        "/pagar", json={"token": "abc", "external_reference": f"reserva:{reserva.id}"}
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "rejected"}


async def test_pagar_sem_external_reference_nao_chama_mp(client, monkeypatch):
    class _NaoDeveriaSerChamado:
        def __init__(self, access_token):
            raise AssertionError("SDK nao deveria ser instanciado sem external_reference")

    monkeypatch.setattr(routes_public.mercadopago, "SDK", _NaoDeveriaSerChamado)

    resp = await client.post("/pagar", json={"token": "abc"})

    assert resp.status_code == 200
    assert resp.json() == {"status": "rejected"}
