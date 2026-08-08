# Telas de gestão do SQLAdmin (CRM, Reservas, Serviços)

from sqladmin import ModelView, Admin, BaseView, expose
from sqladmin.authentication import AuthenticationBackend
from starlette.exceptions import HTTPException
from starlette.requests import Request
from wtforms import SelectField

from datetime import date, datetime, time

from sqlalchemy import select

from app.agenda import DIAS_DA_SEMANA, erro_nos_intervalos
from app.config import settings
from app.database import SessionLocal
from app.fotos import FotoInvalida, apagar_pasta, remover_arquivo, salvar_foto
from app.models import (
    MAX_FOTOS,
    Ausencia,
    Contato,
    Disponibilidade,
    Foto,
    Pedido,
    Post,
    Produto,
    Reserva,
    Servico,
)
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
    # o bloco de fotos so existe na edicao: antes de salvar nao ha id para
    # pendurar o arquivo
    edit_template = "admin/edit_com_fotos.html"

    async def on_model_delete(self, model, request):
        """Apaga tambem os arquivos — a linha some por cascade, o disco nao."""
        apagar_pasta("servico", model.id)

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

class ContatoAdmin(ModelView, model=Contato):
    column_list = [Contato.nome, Contato.email, Contato.telefone, Contato.consentimento_marketing, Contato.criado_em]

class ReservaAdmin(ModelView, model=Reserva):
    column_list = [Reserva.servico_id, Reserva.contato_id, Reserva.data_hora, Reserva.status, Reserva.expira_em]

class ProdutoAdmin(ModelView, model=Produto):
    column_list = [Produto.titulo, Produto.preco, Produto.ativo]
    edit_template = "admin/edit_com_fotos.html"

    async def on_model_delete(self, model, request):
        """Apaga tambem os arquivos — a linha some por cascade, o disco nao."""
        apagar_pasta("produto", model.id)

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


class FotosView(BaseView):
    """Galeria de fotos embutida no form de Servico e de Produto.

    Nao aparece no menu: e um pedaco da tela de edicao, alimentado por HTMX.
    """

    name = "Fotos"
    identity = "fotos"

    def is_visible(self, request: Request) -> bool:
        return False

    @staticmethod
    def _dono(request: Request) -> tuple[str, int]:
        dono = request.path_params["dono"]
        if dono not in ("servico", "produto"):
            raise HTTPException(status_code=404)
        return dono, int(request.path_params["item_id"])

    async def _galeria(self, request: Request, erro: str | None = None):
        dono, item_id = self._dono(request)
        async with SessionLocal() as s:
            coluna = Foto.servico_id if dono == "servico" else Foto.produto_id
            fotos = (
                await s.execute(select(Foto).where(coluna == item_id).order_by(Foto.ordem))
            ).scalars().all()
        return await self.templates.TemplateResponse(
            request,
            "admin/fotos.html",
            {
                "fotos": fotos,
                "dono": dono,
                "item_id": item_id,
                "max_fotos": MAX_FOTOS,
                "erro": erro,
            },
        )

    @expose("/fotos/{dono}/{item_id}", methods=["GET"], identity="fotos")
    async def galeria(self, request: Request):
        return await self._galeria(request)

    @expose("/fotos/{dono}/{item_id}/upload", methods=["POST"], identity="fotos_upload")
    async def upload(self, request: Request):
        dono, item_id = self._dono(request)
        form = await request.form()
        arquivo = form.get("foto")
        if arquivo is None or not getattr(arquivo, "filename", ""):
            return await self._galeria(request, "Escolha um arquivo.")

        async with SessionLocal() as s:
            coluna = Foto.servico_id if dono == "servico" else Foto.produto_id
            atuais = (
                await s.execute(select(Foto).where(coluna == item_id).order_by(Foto.ordem))
            ).scalars().all()
            if len(atuais) >= MAX_FOTOS:
                return await self._galeria(request, f"Máximo de {MAX_FOTOS} fotos.")
            try:
                caminho = await salvar_foto(arquivo, f"{dono}/{item_id}")
            except FotoInvalida as e:
                return await self._galeria(request, str(e))

            foto = Foto(arquivo=caminho, ordem=len(atuais))
            setattr(foto, f"{dono}_id", item_id)
            s.add(foto)
            await s.commit()
        return await self._galeria(request)

    @expose("/fotos/{dono}/{item_id}/remover/{foto_id}", methods=["POST"], identity="fotos_remover")
    async def remover(self, request: Request):
        dono, item_id = self._dono(request)
        async with SessionLocal() as s:
            foto = await s.get(Foto, int(request.path_params["foto_id"]))
            if foto is not None and getattr(foto, f"{dono}_id") == item_id:
                remover_arquivo(foto.arquivo)
                await s.delete(foto)
                await s.commit()
        return await self._galeria(request)


class DisponibilidadeView(BaseView):
    """Horários de atendimento: semana recorrente + períodos de ausência.

    Substitui a tabela crua de Disponibilidade — editar linha a linha um horário
    semanal era o pior jeito possível de fazer isso.
    """

    name = "Horários"
    identity = "horarios"
    icon = "fa-solid fa-calendar-days"

    async def _tela(self, request: Request, erro: str | None = None):
        async with SessionLocal() as s:
            intervalos = (
                await s.execute(
                    select(Disponibilidade).order_by(
                        Disponibilidade.dia_semana, Disponibilidade.hora_inicio
                    )
                )
            ).scalars().all()
            ausencias = (
                await s.execute(select(Ausencia).order_by(Ausencia.data_inicio))
            ).scalars().all()

        por_dia = {numero: [] for numero, _ in DIAS_DA_SEMANA}
        ativo = {numero: False for numero, _ in DIAS_DA_SEMANA}
        for intervalo in intervalos:
            por_dia[intervalo.dia_semana].append(intervalo)
            ativo[intervalo.dia_semana] = ativo[intervalo.dia_semana] or intervalo.ativo

        return await self.templates.TemplateResponse(
            request,
            "admin/horarios.html",
            {
                "dias": DIAS_DA_SEMANA,
                "por_dia": por_dia,
                "ativo": ativo,
                "ausencias": ausencias,
                "hoje": date.today().isoformat(),
                "erro": erro,
            },
        )

    @expose("/horarios", methods=["GET"], identity="horarios")
    async def tela(self, request: Request):
        return await self._tela(request)

    @expose("/horarios/semana", methods=["POST"], identity="horarios_semana")
    async def salvar_semana(self, request: Request):
        """Recebe a semana inteira e reescreve as linhas.

        Idempotente de proposito: acertar um diff incremental de intervalo
        custaria mais codigo do que apagar e regravar sete dias.
        """
        form = await request.form()
        novos: dict[int, tuple[bool, list[tuple[time, time]]]] = {}

        for numero, nome in DIAS_DA_SEMANA:
            inicios = form.getlist(f"dia_{numero}_inicio")
            fins = form.getlist(f"dia_{numero}_fim")
            intervalos = [
                (time.fromisoformat(i), time.fromisoformat(f))
                for i, f in zip(inicios, fins)
                if i and f
            ]
            erro = erro_nos_intervalos(intervalos)
            if erro:
                return await self._tela(request, f"{nome}: {erro}")
            novos[numero] = (form.get(f"dia_{numero}_ativo") is not None, intervalos)

        async with SessionLocal() as s:
            for intervalo in (await s.execute(select(Disponibilidade))).scalars().all():
                await s.delete(intervalo)
            await s.flush()
            for numero, (dia_ativo, intervalos) in novos.items():
                for inicio, fim in intervalos:
                    s.add(
                        Disponibilidade(
                            dia_semana=numero, hora_inicio=inicio, hora_fim=fim, ativo=dia_ativo
                        )
                    )
            await s.commit()
        return await self._tela(request)

    @expose("/horarios/ausencia", methods=["POST"], identity="horarios_ausencia")
    async def criar_ausencia(self, request: Request):
        form = await request.form()
        inicio_str, fim_str = form.get("data_inicio"), form.get("data_fim")
        if not inicio_str:
            return await self._tela(request, "Escolha a data de início da ausência.")
        inicio = date.fromisoformat(inicio_str)
        # Um dia só: fim em branco vira o próprio início.
        fim = date.fromisoformat(fim_str) if fim_str else inicio
        if fim < inicio:
            return await self._tela(request, "A ausência termina antes de começar.")

        motivo = (form.get("motivo") or "").strip() or None
        async with SessionLocal() as s:
            s.add(Ausencia(data_inicio=inicio, data_fim=fim, motivo=motivo))
            await s.commit()
        return await self._tela(request)

    @expose(
        "/horarios/ausencia/{ausencia_id}/remover",
        methods=["POST"],
        identity="horarios_ausencia_remover",
    )
    async def remover_ausencia(self, request: Request):
        async with SessionLocal() as s:
            ausencia = await s.get(Ausencia, int(request.path_params["ausencia_id"]))
            if ausencia is not None:
                await s.delete(ausencia)
                await s.commit()
        return await self._tela(request)


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
    admin.add_view(ContatoAdmin)
    admin.add_view(ReservaAdmin)
    admin.add_view(ProdutoAdmin)
    admin.add_view(PedidoAdmin)
    # ordem do menu lateral: Cursos entra logo depois de Pedidos
    admin.add_base_view(DisponibilidadeView)
    admin.add_base_view(FotosView)
    admin.add_base_view(CursosView)
    admin.add_view(PostAdmin)
    return admin