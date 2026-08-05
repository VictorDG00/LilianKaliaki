# Sprint 0.2 — Spec Corrigida (Fundação do Projeto)

> Substitui o `sprint_0.1` original (dump bruto de LLM, com indentação Python quebrada e bugs de arquitetura). Este documento é a referência para implementação — nenhum código aqui foi escrito nos arquivos reais do projeto ainda; isso é feito manualmente + Copilot em cima desta spec.

## 1. Setup & Tooling

### `.env` (variáveis esperadas)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/app_db
SECRET_KEY=troque_por_uma_chave_aleatoria
MERCADO_PAGO_ACCESS_TOKEN=seu_access_token_aqui
MERCADO_PAGO_WEBHOOK_SECRET=seu_webhook_secret_aqui
```

`.env` está no `.gitignore` — nunca commitar valores reais. `.env.exemple` deve conter as mesmas chaves com placeholders.

### `docker-compose.yml` (referência — Postgres dev + Postgres teste)

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app_db
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  db_test:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app_test_db
    ports: ["5433:5432"]
    tmpfs: ["/var/lib/postgresql/data"]  # descartável, sem volume persistente

volumes:
  pgdata:
```

Testes rodam contra Postgres real (`db_test`), não SQLite — a trava de concorrência usa `SELECT ... FOR UPDATE`, que SQLite não implementa de fato (daria falso-positivo de segurança).

### `requirements.txt` (referência)

```
fastapi
uvicorn[standard]
sqlmodel
asyncpg
sqladmin
jinja2
python-multipart
pydantic-settings
mercadopago
pytest
pytest-asyncio
httpx
```

## 2. Modelo de Dados (corrigido)

Bugs corrigidos em relação ao rascunho original:
- `table_args` → `__table_args__` (faltavam os dunders — a constraint nunca era aplicada).
- `UniqueConstraint("servico_id", "data_hora")` incondicional **removida**. Ela bloqueava reagendar um horário cuja reserva anterior expirou/foi cancelada. No lugar, usar um **índice único parcial** (Postgres suporta nativamente), que só considera reservas ativas:

```sql
CREATE UNIQUE INDEX unique_reserva_ativa
ON reserva (servico_id, data_hora)
WHERE status IN ('pendente', 'confirmada');
```

No SQLModel isso é criado via migration/DDL manual (não há suporte direto a índice parcial na API declarativa do SQLModel) — documentar isso como um passo explícito de setup do banco, não algo que `SQLModel.metadata.create_all` resolve sozinho.

### Entidades

- **Servico**: `id, titulo, descricao, duracao_min, preco, ativo`
- **Disponibilidade**: `id, dia_semana (0=Segunda..6=Domingo), hora_inicio, hora_fim`
- **Contato** (CRM): `id, nome, email (index), telefone, consentimento_marketing, criado_em`
- **Reserva**: `id, servico_id (FK), contato_id (FK), data_hora (index), status (pendente|confirmada|expirada|cancelada), expira_em, mp_payment_id, criado_em`

## 3. Config & Sessão Async

- `Settings` via `pydantic-settings` (`BaseSettings`), não `os.getenv` manual solto — mais alinhado ao "usar estritamente pydantic-settings ou python-dotenv" do `CLAUDE.md`, e ganha validação de tipos de graça.
- Sessão async: usar `async_sessionmaker` (API moderna do SQLAlchemy 2.0), não `sessionmaker(class_=AsyncSession)` (padrão antigo usado no rascunho).

## 4. Rotas Públicas (HTMX) — fluxo em 3 passos

Mantém o fluxo do rascunho original, que estava correto conceitualmente:

1. `GET /` — lista serviços ativos.
2. `GET /horarios-livres?servico_id&data_str` — retorna partial HTML com horários livres do dia (filtra reservas `pendente`/`confirmada` já ocupando o slot).
3. `POST /reservar` — cria/atualiza `Contato`, tenta criar `Reserva` com `expira_em = now + 15min`.

Concorrência: manter o `SELECT ... FOR UPDATE` dentro da transação (evita a corrida na leitura), **e** confiar no índice único parcial do banco como última linha de defesa (defesa em profundidade — se dois requests passarem pela checagem simultaneamente, o índice único rejeita o segundo `INSERT`, que deve ser capturado como `IntegrityError` e traduzido para a mensagem de erro amigável).

## 5. Webhook Mercado Pago — validação de assinatura (faltava no rascunho)

O rascunho original só lia os headers `x-signature`/`x-request-id` e ignorava — isso viola a regra do `CLAUDE.md`. Algoritmo correto (conferir a doc oficial atual da MP para exatidão de formatação, isto é a estrutura geral):

1. Extrair de `x-signature`: `ts` e `v1` (formato `ts=<timestamp>,v1=<hash>`).
2. Montar o manifest: `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`
3. Calcular `hmac.new(MP_WEBHOOK_SECRET, manifest, hashlib.sha256).hexdigest()`.
4. Comparar com `v1` usando `hmac.compare_digest` (nunca `==` direto — evita timing attack).
5. Se não bater, retornar `401` e **não processar** o payload.
6. Se bater, consultar a API do MP pelo `payment_id` para confirmar `status == "approved"`, então atualizar `Reserva.status = CONFIRMADA` e `Reserva.mp_payment_id`.

## 6. Expiração de Reservas Pendentes (faltava no rascunho)

Mecanismo escolhido: **loop `asyncio` em background, iniciado no startup do FastAPI** (mais simples que expor endpoint + cron externo, e continua "zero filas/workers complexos" per `CLAUDE.md`):

```python
async def expirar_reservas_loop():
    while True:
        await asyncio.sleep(60)
        # UPDATE reserva SET status='expirada' WHERE status='pendente' AND expira_em < now()

# no lifespan/startup do FastAPI:
asyncio.create_task(expirar_reservas_loop())
```

## 7. Estratégia de Testes

- `pytest` + `pytest-asyncio` + `httpx.AsyncClient` (via `ASGITransport`) contra o Postgres real do `db_test` (não mocks, não SQLite).
- Testes prioritários:
  - Concorrência: dois `POST /reservar` simultâneos no mesmo horário → só um sucesso, o outro recebe o erro amigável.
  - Reagendamento de horário expirado: reserva `EXPIRADA` no slot não deve bloquear uma nova reserva no mesmo slot.
  - Webhook: assinatura válida processa; assinatura inválida/ausente retorna `401` e não altera o banco; replay do mesmo `payment_id` é idempotente.
  - Expiração automática: reserva `PENDENTE` com `expira_em` no passado vira `EXPIRADA` após o loop rodar.
  - CRM: mesmo e-mail em duas reservas não duplica `Contato` (upsert por e-mail).

## 8. Templates

Estrutura de `partials/` do rascunho original estava razoável (horarios_list, checkout, erro) — mantém. Pendências que o rascunho deixou em aberto:
- `base.html` está vazio hoje — precisa ser escrito do zero (layout base + bloco `content`).
- Não há plano de CSS estático — definir uma pasta `static/` simples (sem build tools, per `CLAUDE.md`) antes de referenciar classes como `.card`/`.btn` nos templates.
