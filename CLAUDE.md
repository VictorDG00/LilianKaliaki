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