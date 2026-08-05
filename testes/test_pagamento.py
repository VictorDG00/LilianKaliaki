import app.routes_public as routes_public


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


async def test_pagar_encaminha_external_reference_e_retorna_status(client, monkeypatch):
    monkeypatch.setattr(routes_public.mercadopago, "SDK", _FakeSDK)

    resp = await client.post(
        "/pagar",
        json={
            "token": "abc",
            "payment_method_id": "visa",
            "transaction_amount": 80.0,
            "installments": 1,
            "external_reference": "reserva:1",
        },
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "approved"}
    assert _FakeSDK.instance.payment().last_payload["external_reference"] == "reserva:1"


async def test_pagar_erro_400_do_mp_nao_confunde_status_http_com_status_pagamento(client, monkeypatch):
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

    resp = await client.post(
        "/pagar", json={"token": "abc", "external_reference": "reserva:1"}
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
