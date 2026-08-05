# Step-by-step — database.py, admin.py, main.py

> Fecha a etapa 4 (sessão async) e monta o esqueleto que a etapa 5 (rotas públicas) vai usar. Código é escrito pelo Copilot inline; isto é só o roteiro.

## 1. `app/database.py` — feito ✅

- Módulo, sem classe: importa `settings` de `app.config` e cria `engine` e `SessionLocal` **uma vez**, no nível do módulo (não dentro de função — senão recria a pool a cada request).
- `engine = create_async_engine(settings.DATABASE_URL, echo=True)` — lib `sqlalchemy.ext.asyncio`.
- `SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)` — API SQLAlchemy 2.0 (a spec pede especificamente `async_sessionmaker`, não o `sessionmaker(class_=AsyncSession)` antigo).
- `async def get_session()`: generator que faz `async with SessionLocal() as session: yield session` — é a função que as rotas vão usar como `Depends(get_session)`.
- Não criar tabelas aqui (`create_all`) — schema só via Alembic.

## 2. `app/admin.py`

Objetivo: registrar os 4 models no SQLAdmin. Zero painel customizado (guardrail seção 1/5) — o SQLAdmin já resolve list/create/edit/delete sozinho, você só descreve o que mostrar.

- **Imports**: `from sqladmin import Admin, ModelView` (já está no arquivo) + `from app.models import Servico, Disponibilidade, Contato, Reserva`.

- **Classe `ServicoAdmin(ModelView, model=Servico)`**: define `column_list` com os campos que fazem sentido na tabela (`titulo`, `duracao_min`, `preco`, `ativo`). Não precisa de método nenhum, é só atributos de classe — o SQLAdmin lê essas classes por reflexão.

- **Classe `DisponibilidadeAdmin(ModelView, model=Disponibilidade)`**: `column_list` com `dia_semana`, `hora_inicio`, `hora_fim`.

- **Classe `ContatoAdmin(ModelView, model=Contato)`**: `column_list` com `nome`, `email`, `telefone`, `consentimento_marketing`, `criado_em`.

- **Classe `ReservaAdmin(ModelView, model=Reserva)`**: `column_list` com `servico_id`, `contato_id`, `data_hora`, `status`, `expira_em` — é a tela mais importante pra operação do dia a dia (ver reservas pendentes/confirmadas).

- **Função `setup_admin(app, engine) -> Admin`**: instancia `admin = Admin(app, engine)`, chama `admin.add_view(...)` uma vez pra cada uma das 4 classes acima, e retorna `admin`. Essa função é chamada de dentro de `main.py` — o `admin.py` não monta nada sozinho, só define e expõe.

## 3. `app/main.py`

Objetivo: entrypoint FastAPI que junta tudo (engine, admin, templates, routers).

- **Instância `app = FastAPI()`** — no topo do módulo.
- **Reusar a engine de `database.py`**: `from app.database import engine` — não chamar `create_async_engine` de novo aqui, senão você tem duas pools concorrentes pro mesmo banco.
- **Chamar `setup_admin(app, engine)`** importado de `app.admin` — uma linha, monta o painel inteiro em `/admin`.
- **Montar arquivos estáticos**: `app.mount("/static", StaticFiles(directory="static"), name="static")` — lib `fastapi.staticfiles`, pasta `static/` da seção 9 da spec.
- **Instanciar `Jinja2Templates(directory="templates")`** — pode ficar em `main.py` e ser importado por `routes_public.py`, ou instanciar direto lá; só não duplicar a instância.
- **Registrar os routers**: `app.include_router(routes_public.router)` e `app.include_router(routes_webhook.router)` — importados de `app.routes_public` e `app.routes_webhook`. Os dois arquivos ainda são stubs vazios (vão ganhar `router = APIRouter()` e os endpoints nas etapas 5 e 6).
- **Não** adicionar ainda o loop de expiração (`asyncio.create_task(expirar_reservas_loop())`) — isso é etapa 7, só entra no `lifespan` quando a função `expirar_reservas_loop` existir.

## Ordem sugerida

`admin.py` → `main.py` (agora que `database.py` já está pronto). Depois disso, a etapa 5 (rotas públicas) já tem `get_session`, `engine` e templates disponíveis pra usar.
