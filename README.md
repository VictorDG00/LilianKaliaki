# LilianKaliaki

Site + agendamento de serviços + venda de produtos avulsos, com pagamento via
Mercado Pago (Checkout Bricks). App single-tenant (uma instância por
negócio), monolito único em FastAPI — sem microserviços, sem filas
(Celery/Redis), sem front-end SPA.

## Stack

- **Backend:** [FastAPI](https://fastapi.tiangolo.com/) + [SQLModel](https://sqlmodel.tiangolo.com/) (SQLAlchemy async) + [Alembic](https://alembic.sqlalchemy.org/) (migrations)
- **Banco:** PostgreSQL, acesso async via `asyncpg`
- **Painel admin:** [SQLAdmin](https://aminalaee.github.io/sqladmin/) em `/admin` — CRUD de Serviços, Disponibilidade, Contatos, Reservas, Produtos e Pedidos, sem tela custom
- **Front-end:** Jinja2 (server-side) + [HTMX](https://htmx.org/) — sem build step, sem SPA
- **Pagamento:** Mercado Pago Checkout Bricks (cartão, Pix, boleto) + webhook com validação de assinatura HMAC
- **Testes:** `pytest` + `pytest-asyncio` + `httpx.AsyncClient`, rodando contra Postgres real em container (não SQLite — a trava de concorrência das reservas usa `SELECT ... FOR UPDATE`, que SQLite não implementa de fato)

## Como rodar em dev

Pré-requisitos: Python 3.12+, Docker + Docker Compose plugin.

```bash
cp .env.exemple .env          # ajustar credenciais de sandbox do Mercado Pago
pip install -r requirements.txt
python start.py               # sobe Postgres (db + db_test) via Docker e aplica as migrations
uvicorn app.main:app --reload
```

Acesse `http://localhost:8000/`. O painel admin fica em `http://localhost:8000/admin`
(login com `ADMIN_USERNAME`/`ADMIN_PASSWORD` do `.env`).

`start.py` só cuida do banco (`Infra/docker-compose.yml` sobe `db` na porta
`5432` e `db_test` na `5433`) + `alembic upgrade head` — quem sobe o servidor
é o `uvicorn` acima, rodado à parte.

### Rodar os testes

Precisa do `db_test` no ar (o `start.py` já sobe; senão: `docker compose -f Infra/docker-compose.yml up -d`):

```bash
pytest
```

## Fluxo geral da aplicação

**Agendamento de serviço** — visitante escolhe um `Serviço` na home → HTMX
carrega os passos do drawer (data → horários livres, calculados a partir da
`Disponibilidade` cadastrada e das `Reservas` já ocupadas naquele dia →
formulário de contato) → `POST /reservar` cria/atualiza o `Contato`, trava o
horário com `SELECT ... FOR UPDATE` (evita duas pessoas reservando o mesmo
slot ao mesmo tempo) e cria a `Reserva` como `Pendente` com expiração em 15
minutos → mostra o Checkout Brick do Mercado Pago. Um loop `asyncio` em
background (`app/tasks.py`, iniciado no `lifespan` do FastAPI) varre a cada
60s e marca como `Expirada` toda reserva `Pendente` que passou do prazo,
liberando o horário — sem cron externo nem worker separado.

**Compra de produto** — mesma ideia, mas sem conceito de horário: escolhe um
`Produto` → `POST /comprar` cria/atualiza o `Contato` e um `Pedido`
`Pendente` → mostra o mesmo Checkout Brick (partial reaproveitado entre os
dois fluxos).

**Pagamento** — o Brick tokeniza o cartão no browser e envia pro backend em
`POST /pagar`, que repassa pra API do Mercado Pago (`sdk.payment().create`)
e retorna o status; a confirmação de verdade, porém, só acontece via
**webhook** — a resposta síncrona de `/pagar` é só feedback de tela.

**Webhook (`POST /webhook/mercadopago`)** — valida a assinatura `x-signature`
(HMAC com `MERCADO_PAGO_WEBHOOK_SECRET`) antes de processar qualquer coisa,
depois consulta a API do MP pelo `payment_id` (nunca confia direto no
payload) para confirmar que o pagamento foi `approved`. O `external_reference`
da preference tem o formato `"reserva:<id>"` ou `"pedido:<id>"` — o webhook
usa esse prefixo pra saber qual tabela atualizar (`Reserva.status` →
`Confirmada`, ou `Pedido.status` → `Confirmado`) e é idempotente (reenvio do
MP com o mesmo `payment_id` não duplica o efeito).

**Admin (`/admin`)** — gestão de Serviços, Disponibilidade (grade de
horários por dia da semana), Contatos, Reservas, Produtos e Pedidos, tudo via
SQLAdmin (login próprio, sem relação com autenticação de cliente).

## Deploy em produção

Ver [`step-by-step.md`](./step-by-step.md) — build via Docker
(`Infra/Dockerfile` + `Infra/docker-compose.prod.yml`), isolado dos demais
projetos da VPS.

## Guardrails do projeto

Antes de mexer em arquitetura, stack ou escopo, ver [`CLAUDE.md`](./CLAUDE.md)
— stack é travada de propósito (sem multi-tenant, sem microserviços, sem
filas/workers, sem trocar Mercado Pago/HTMX por outra coisa).
