# Telas de gestão do SQLAdmin (CRM, Reservas, Serviços)

from sqladmin import ModelView, Admin
from app.models import Servico, Disponibilidade, Contato, Reserva, Produto, Pedido

class ServicoAdmin(ModelView, model=Servico):
    column_list = [Servico.titulo, Servico.duracao_min, Servico.preco, Servico.ativo]

class DisponibilidadeAdmin(ModelView, model=Disponibilidade):
    column_list = [Disponibilidade.dia_semana, Disponibilidade.hora_inicio, Disponibilidade.hora_fim]

class ContatoAdmin(ModelView, model=Contato):
    column_list = [Contato.nome, Contato.email, Contato.telefone, Contato.consentimento_marketing, Contato.criado_em]

class ReservaAdmin(ModelView, model=Reserva):
    column_list = [Reserva.servico_id, Reserva.contato_id, Reserva.data_hora, Reserva.status, Reserva.expira_em]

class ProdutoAdmin(ModelView, model=Produto):
    column_list = [Produto.titulo, Produto.preco, Produto.ativo]

class PedidoAdmin(ModelView, model=Pedido):
    column_list = [Pedido.produto_id, Pedido.contato_id, Pedido.status, Pedido.mp_payment_id, Pedido.criado_em]

def setup_admin(app, engine) -> Admin:
    admin = Admin(app, engine)
    admin.add_view(ServicoAdmin)
    admin.add_view(DisponibilidadeAdmin)
    admin.add_view(ContatoAdmin)
    admin.add_view(ReservaAdmin)
    admin.add_view(ProdutoAdmin)
    admin.add_view(PedidoAdmin)
    return admin