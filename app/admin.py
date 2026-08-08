# Telas de gestão do SQLAdmin (CRM, Reservas, Serviços)

from sqladmin import ModelView, Admin, BaseView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from wtforms import SelectField

from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Servico, Disponibilidade, Contato, Reserva, Produto, Pedido, Post
from app.slug import slug_unico


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        if form.get("username") == settings.ADMIN_USERNAME and form.get("password") == settings.ADMIN_PASSWORD:
            request.session.update({"autenticado": True})
            return True
        return False

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        return bool(request.session.get("autenticado"))

# Tempo de atendimento oferecido. A coluna continua sendo minutos (int) — isto
# aqui e so a forma de escolher, para nao existir servico de 47 minutos.
DURACOES = [(30, "00:30"), (60, "01:00"), (90, "01:30"), (120, "02:00")]


def hhmm(minutos: int | None) -> str:
    """90 -> '01:30'."""
    if minutos is None:
        return ""
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


class ServicoAdmin(ModelView, model=Servico):
    column_list = [Servico.titulo, Servico.duracao_min, Servico.preco, Servico.ativo]
    column_labels = {Servico.duracao_min: "Tempo do serviço"}
    column_formatters = {Servico.duracao_min: lambda m, a: hhmm(m.duracao_min)}
    form_overrides = {"duracao_min": SelectField}
    form_args = {"duracao_min": {"choices": DURACOES, "coerce": int, "label": "Tempo do serviço"}}

    async def scaffold_form(self, rules=None):
        """Duracao fora do padrao (cadastrada antes desta tela) entra na lista.

        Sem isto, abrir um servico de 45 min para mexer no preco salvaria ele
        como 30 min sem ninguem perceber.
        """
        form = await super().scaffold_form(rules)
        async with SessionLocal() as s:
            existentes = set((await s.execute(select(Servico.duracao_min))).scalars().all())
        extras = sorted(existentes - {m for m, _ in DURACOES})
        if extras:
            form.duracao_min.kwargs["choices"] = DURACOES + [(m, hhmm(m)) for m in extras]
        return form

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

class PostAdmin(ModelView, model=Post):
    column_list = [Post.titulo, Post.slug, Post.publicado, Post.publicado_em]
    # slug sai do form: e derivado do titulo em on_model_change
    form_excluded_columns = [Post.slug, Post.criado_em]

    async def on_model_change(self, data, model, is_created, request):
        """Gera o slug do titulo e carimba publicado_em na primeira publicacao."""
        if is_created or not getattr(model, "slug", None):
            async with SessionLocal() as s:
                usados = (await s.execute(select(Post.slug))).scalars().all()
            data["slug"] = slug_unico(data.get("titulo") or "", usados)
        if data.get("publicado") and not data.get("publicado_em"):
            data["publicado_em"] = datetime.utcnow()


class CursosView(BaseView):
    """Placeholder. Vira ModelView quando existir a tabela de curso."""

    name = "Cursos"
    identity = "cursos"
    icon = "fa-solid fa-graduation-cap"

    @expose("/cursos", identity="cursos")
    async def pagina(self, request: Request):
        return await self.templates.TemplateResponse(request, "admin/cursos.html")


def setup_admin(app, engine) -> Admin:
    admin = Admin(app, engine, authentication_backend=AdminAuth(secret_key=settings.SECRET_KEY))
    admin.add_view(ServicoAdmin)
    admin.add_view(DisponibilidadeAdmin)
    admin.add_view(ContatoAdmin)
    admin.add_view(ReservaAdmin)
    admin.add_view(ProdutoAdmin)
    admin.add_view(PedidoAdmin)
    # ordem do menu lateral: Cursos entra logo depois de Pedidos
    admin.add_base_view(CursosView)
    admin.add_view(PostAdmin)
    return admin