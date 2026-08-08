# Preco de uma transacao, sempre lido do banco.
#
# Existe porque o valor NAO pode vir do navegador: quem monta o payload do
# Checkout Bricks e o cliente, e um payload editado no DevTools pagaria o
# servico de R$ 300 por R$ 0,01. Duas portas usam esta funcao — /pagar, para
# definir o transaction_amount, e o webhook, para conferir o que o Mercado Pago
# diz que foi pago.

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Pedido, Produto, Reserva, Servico, StatusPedido, StatusReserva


async def preco_da_referencia(session: AsyncSession, external_reference: str) -> float | None:
    """Quanto custa a transacao de `reserva:<id>` / `pedido:<id>`.

    None quando a referencia nao existe, nao esta pendente ou aponta para um
    item que sumiu — nesse caso nao ha cobranca a fazer.
    """
    tipo, _, id_str = (external_reference or "").partition(":")
    if not id_str.isdigit():
        return None

    if tipo == "reserva":
        reserva = await session.get(Reserva, int(id_str))
        if reserva is None or reserva.status != StatusReserva.PENDENTE:
            return None
        servico = await session.get(Servico, reserva.servico_id)
        return servico.preco if servico else None

    if tipo == "pedido":
        pedido = await session.get(Pedido, int(id_str))
        if pedido is None or pedido.status != StatusPedido.PENDENTE:
            return None
        produto = await session.get(Produto, pedido.produto_id)
        return produto.preco if produto else None

    return None
