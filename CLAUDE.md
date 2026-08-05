GUARDRAILS & PREMISSAS DO PROJETO 
ATENÇÃO PARA AGENTES DE IA / LLMs:
Este projeto possui escolhas de arquitetura e tecnologia FIXAS E INEGOCIÁVEIS. Nenhuma IA deve sugerir a substituição de frameworks, adição de camadas de complexidade ou refatoração de infraestrutura sem solicitação explícita do usuário.

1. Stack Tecnológica Inegociável (Stack Lock)
Backend: FastAPI + SQLModel (SQLAlchemy Async).

Painel Admin: SQLAdmin (Zero criação de painel administrativo customizado)

Front-end público: Jinja2 Templates + HTMX (Proibido uso de frameworks SPA como React, Vue, Next.js ou build tools como Vite/Webpack).

Banco de Dados: PostgreSQL (Async via asyncpg).

Pagamentos: Mercado Pago Checkout Bricks (Proibido redirecionamento via Checkout Pro ou troca por Stripe).

Agendamento/Reserva: Embed do Cal.com ou fluxo enxuto HTMX no banco próprio (sem sincronizações complexas distribuídas).

Testes: pytest + pytest-asyncio + httpx.AsyncClient, rodando contra Postgres real (via Docker), não mocks nem SQLite — a trava de concorrência usa SELECT FOR UPDATE, que SQLite não implementa de fato.

2. Limites de Escopo & Arquitetura (Anti-Overengineering)
Single-Tenant Estrito:

Proibido adicionar tenant_id, schemas dinâmicos, resolução de subdomínios ou lógica multi-cliente. O app é 1 instância para 1 pessoa/empresa.

Monolito Simples:

Tudo roda no mesmo processo FastAPI. Proibido divisão em microserviços.

Zero Filas / Workers Assíncronos no MVP:

Proibido adicionar Celery, Redis, RabbitMQ ou Background Workers complexos. Tarefas simples (como liberar reserva expirada) usam endpoints simples/crontab ou BackgroundTasks nativo do FastAPI.

Sem APIs REST separadas para o Front-end:

O front-end usa Jinja2 + HTMX retornando fragmentos de HTML (partials/). Não crie endpoints JSON paralelos para alimentar front-end, a menos que seja um Webhook externo.

3. Segurança e Regras de Código
Webhooks: Todo webhook (ex: Mercado Pago) DEVE validar a assinatura (x-signature / HMAC) antes de processar qualquer payload.

Segredos: NENHUMA chave API, token do Mercado Pago ou secret deve ser hardcoded. Usar estritamente pydantic-settings ou python-dotenv.

Concorrência: Reservas/Agendamentos críticos devem usar transações explícitas no banco (SELECT ... FOR UPDATE) somado a um índice único PARCIAL no Postgres (ex: UNIQUE (servico_id, data_hora) WHERE status IN ('pendente','confirmada')) — nunca uma Unique Constraint incondicional, que bloquearia reagendar um horário já expirado/cancelado.

Expiração de reservas: usar um loop asyncio em background iniciado no startup do FastAPI (não Celery/cron externo), consistente com a regra de "zero filas/workers complexos" acima.

4. Protocolo de Git e Commits (Regras da Casa)
Commit granular: Toda alteração ou feature funcional concluída DEVE gerar um commit local com mensagem semântica (ex: feat: adiciona fluxo htmx de horarios).

Regra dos 5 Commits: A cada 5 commits locais, é OBRIGATÓRIO executar git push para o repositório remoto para manter o projeto sincronizado para revisão externa.

5. Instruções para a IA durante o Código
Se a IA precisar criar uma tela nova: Use Jinja2 + HTMX e adicione o model no SQLAdmin. Não crie rotas de CRUD manualmente se o SQLAdmin puder resolver.

Se a IA sugerir uma biblioteca nova: Ela deve verificar se a funcionalidade já não é resolvida por FastAPI, HTMX ou SQLModel nativos.

Se o código ficar complexo: Pare, simplifique e reduza para a solução com menos linhas de código possível.

6. Estado Atual & Notas Operacionais (atualizado 2026-08-05)

Divisão de trabalho antiga (Claude só editava `.md`, Copilot escrevia código) foi **revogada** pelo usuário — Claude agora implementa código diretamente neste projeto.

Todas as seções da `sprint_0.3.md` (1-9) estão implementadas: models, migrations, config/sessão async, rotas públicas HTMX, webhook Mercado Pago, loop de expiração, testes, templates.

Pontos que exigem atenção humana antes de operar em produção:
- `SessionLocal` em `app/database.py` usa `sqlmodel.ext.asyncio.session.AsyncSession` (não a `AsyncSession` pura do SQLAlchemy) — é o que dá o método `.exec()` usado em todas as rotas.
- `MERCADO_PAGO_PUBLIC_KEY` foi adicionada ao `Settings`/`.env`/`.env.exemple` — obrigatória para o Checkout Bricks no browser (`MERCADO_PAGO_ACCESS_TOKEN` continua sendo só server-side).
- Rota do webhook é `POST /webhook/mercadopago` — precisa bater com o que for cadastrado no painel do Mercado Pago.
- O snippet de inicialização do Checkout Bricks em `templates/partials/checkout.html` é melhor esforço — validar contra a doc oficial da MP quando houver conta de sandbox real configurada.
- Upsert de `Contato` por e-mail não tem trava de concorrência dedicada (só `Reserva` tem o índice único parcial) — dois `POST /reservar` simultâneos com e-mail novo idêntico podem, em teoria, criar 2 `Contato`s. Não é um caso coberto pelos testes prioritários da spec; ficou registrado como limitação conhecida, não como bug.
- Testes (`testes/`) exigem o `db_test` (porta 5433) no ar — `docker compose -f Infra/docker-compose.yml up -d` — e mockam a API do Mercado Pago (chamada externa, não banco, por isso não entra na regra "sem mocks" que é especificamente sobre Postgres/`SELECT FOR UPDATE`). Rodar com `pytest` na raiz.