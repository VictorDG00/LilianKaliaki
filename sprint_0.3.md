
# Sprint 0.3 — Spec da Fundação do Projeto

> Documento de referência da arquitetura. Use-o para guiar a implementação de cada parte do app (junto com o Copilot fazendo o código inline).

## 1. [x] Setup & Tooling

### `.env` (variáveis esperadas)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/app_db
SECRET_KEY=troque_por_uma_chave_aleatoria
MERCADO_PAGO_ACCESS_TOKEN=seu_access_token_aqui
MERCADO_PAGO_WEBHOOK_SECRET=seu_webhook_secret_aqui
```

`.env` está no `.gitignore` — nunca commitar valores reais. `.env.exemple` deve conter as mesmas chaves com placeholders.

### Docker

Postgres de dev e de teste já estão definidos em `Infra/docker-compose.yml` (`db` na porta 5432, `db_test` na porta 5433, descartável via `tmpfs`). Suba com `docker compose -f Infra/docker-compose.yml up -d` antes de rodar a app ou os testes.

### `requirements.txt` (referência)

```
fastapi
uvicorn[standard]
sqlmodel
asyncpg
alembic
sqladmin
jinja2
python-multipart
pydantic-settings
mercadopago
pytest
pytest-asyncio
httpx
```

## 2. [x] Modelo de Dados

### Entidades

- **Servico**: `id, titulo, descricao, duracao_min, preco, ativo`
- **Disponibilidade**: `id, dia_semana (0=Segunda..6=Domingo), hora_inicio, hora_fim`
- **Contato** (CRM): `id, nome, email (index), telefone, consentimento_marketing, criado_em`
- **Reserva**: `id, servico_id (FK), contato_id (FK), data_hora (index), status (pendente|confirmada|expirada|cancelada), expira_em, mp_payment_id, criado_em`

Em SQLModel, toda `class Meta`/constraint de tabela vai em `__table_args__` (com os dois underscores de cada lado — sem eles a constraint é ignorada silenciosamente).

### Trava de concorrência: índice único parcial

A `Reserva` **não** deve ter uma unique constraint incondicional em `(servico_id, data_hora)` — isso bloquearia reagendar um horário cuja reserva anterior expirou ou foi cancelada. A trava correta é um **índice único parcial**, que só considera reservas ativas:

```sql
CREATE UNIQUE INDEX unique_reserva_ativa
ON reserva (servico_id, data_hora)
WHERE status IN ('pendente', 'confirmada');
```

Índice parcial não tem suporte na API declarativa do SQLModel — ele é criado via **migration do Alembic** (seção 3), não via `SQLModel.metadata.create_all` e não como SQL solto no código da app.

## 3. [x] Migrations com Alembic

Todo o versionamento de schema é feito com Alembic (padrão do ecossistema SQLAlchemy/SQLModel), não com `create_all` direto em produção.

Passos de setup:

1. Adicionar `alembic` ao `requirements.txt`.
2. Rodar `alembic init alembic` na raiz do projeto — cria a pasta `alembic/` e o `alembic.ini`.
3. Em `alembic/env.py`: setar `target_metadata = SQLModel.metadata` e ler a `DATABASE_URL` de `app.config.settings` (não hardcode). Como a engine é async, usar o padrão oficial do Alembic para SQLAlchemy async (`run_sync` dentro de uma função async em `env.py`).
    1. Importar os models antes de setar o target_metadata

    Se você só fizer target_metadata = SQLModel.metadata sem antes
    importar o módulo onde as classes (Servico, Reserva, etc.) estão
    definidas, o metadata fica vazio — o autogenerate não vai ver nenhuma
    tabela.

    from app.models import *  # garante que as classes registrem suas 
    tabelas no metadata
    from app.config import settings
    target_metadata = SQLModel.metadata

    2. Puxar a DATABASE_URL do seu Settings, não do alembic.ini

    Logo depois de config = context.config, adicione:

    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

    Assim você não duplica a URL do banco em dois lugares (.env e
    alembic.ini).

    3. Trocar a função run_migrations_online pela versão async

    A gerada por padrão usa engine_from_config (sync) — troque por isto:

    import asyncio
    from sqlalchemy.ext.asyncio import async_engine_from_config

    def do_run_migrations(connection):
        context.configure(connection=connection,
    target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

    async def run_migrations_online():
        connectable = async_engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online())

    Depois disso, o fluxo do passo 4 em diante da spec já funciona:

    1. alembic revision --autogenerate -m "schema inicial" → gera um
    arquivo em alembic/versions/.
    2. Abra esse arquivo e confira se as tabelas certas apareceram na
    função upgrade().
    3. Adicione manualmente o op.create_index(..., postgresql_where=...)
    do índice parcial (isso o autogenerate nunca detecta sozinho).
    4. alembic upgrade head — aplica no banco.
4. Gerar a migration inicial: `alembic revision --autogenerate -m "schema inicial"`.
5. O autogenerate **não detecta** índice parcial sozinho — editar a migration gerada e adicionar manualmente:

```python
op.create_index(
    "unique_reserva_ativa",
    "reserva",
    ["servico_id", "data_hora"],
    unique=True,
    postgresql_where=sa.text("status IN ('pendente', 'confirmada')"),
)
```

6. Aplicar: `alembic upgrade head`.

Fluxo do dia a dia: qualquer mudança em `app/models.py` → `alembic revision --autogenerate -m "descrição"` → revisar o arquivo gerado (autogenerate erra às vezes, principalmente em índices/constraints especiais) → `alembic upgrade head`. Isso vale tanto pro banco de dev quanto pro `db_test` usado nos testes.

## 4. [x] Config & Sessão Async

- `Settings` via `pydantic-settings` (`BaseSettings`), lendo do `.env`.
- Sessão async criada com `async_sessionmaker` (API do SQLAlchemy 2.0).

## 5. [x] Rotas Públicas (HTMX) — fluxo em 3 passos

1. `GET /` — lista serviços ativos.
2. `GET /horarios-livres?servico_id&data_str` — retorna partial HTML com horários livres do dia (filtra reservas `pendente`/`confirmada` já ocupando o slot).
3. `POST /reservar` — cria/atualiza `Contato`, tenta criar `Reserva` com `expira_em = now + 15min`.

Concorrência: usar `SELECT ... FOR UPDATE` dentro da transação ao checar o slot, **e** confiar no índice único parcial do banco como última linha de defesa. Se dois requests passarem pela checagem simultaneamente, o índice único rejeita o segundo `INSERT` (`IntegrityError`), que deve ser capturado e traduzido para uma mensagem de erro amigável no partial de erro.

## 6. [x] Webhook Mercado Pago — validação de assinatura

Todo request no endpoint de webhook precisa ser validado antes de processar qualquer payload:

1. Extrair de `x-signature`: `ts` e `v1` (formato `ts=<timestamp>,v1=<hash>`).
2. Montar o manifest: `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`
3. Calcular `hmac.new(MP_WEBHOOK_SECRET, manifest, hashlib.sha256).hexdigest()`.
4. Comparar com `v1` usando `hmac.compare_digest` (nunca `==` direto — evita timing attack).
5. Se não bater, retornar `401` e **não processar** o payload.
6. Se bater, consultar a API do MP pelo `payment_id` para confirmar `status == "approved"`, então atualizar `Reserva.status = CONFIRMADA` e `Reserva.mp_payment_id`.

(Conferir a doc oficial atual da Mercado Pago para exatidão de formatação do manifest — a estrutura acima é a geral.)

## 7. [x] Expiração de Reservas Pendentes

Mecanismo: loop `asyncio` em background, iniciado no startup do FastAPI (sem Celery/cron externo):

```python
async def expirar_reservas_loop():
    while True:
        await asyncio.sleep(60)
        # UPDATE reserva SET status='expirada' WHERE status='pendente' AND expira_em < now()

# no lifespan/startup do FastAPI:
asyncio.create_task(expirar_reservas_loop())
```

## 8. [x] Estratégia de Testes

- `pytest` + `pytest-asyncio` + `httpx.AsyncClient` (via `ASGITransport`) contra o Postgres real do `db_test` (não mocks, não SQLite — a trava de concorrência usa `SELECT FOR UPDATE`, que SQLite não implementa de fato).
- Antes de rodar os testes, aplicar as migrations no `db_test` (`alembic upgrade head` apontando para a `DATABASE_URL` de teste).
- Testes prioritários:
  - Concorrência: dois `POST /reservar` simultâneos no mesmo horário → só um sucesso, o outro recebe o erro amigável.
  - Reagendamento de horário expirado: reserva `EXPIRADA` no slot não deve bloquear uma nova reserva no mesmo slot.
  - Webhook: assinatura válida processa; assinatura inválida/ausente retorna `401` e não altera o banco; replay do mesmo `payment_id` é idempotente.
  - Expiração automática: reserva `PENDENTE` com `expira_em` no passado vira `EXPIRADA` após o loop rodar.
  - CRM: mesmo e-mail em duas reservas não duplica `Contato` (upsert por e-mail).

## 9. [x] Templates

- `base.html`: layout base com bloco `content`.
- `index.html`: lista de serviços + input de data (`hx-get="/horarios-livres"`).
- `partials/horarios_list.html`, `partials/checkout.html`, `partials/erro.html`: fragmentos HTMX retornados pelas rotas.
- `static/`: pasta simples de CSS, sem build tools, referenciada pelos templates (classes como `.card`/`.btn`).
