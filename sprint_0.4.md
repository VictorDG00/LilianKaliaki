# Sprint 0.4 — Blog, Guardrails e Esteira CI/CD

> Documento de referência desta sprint. Mesmo formato da `sprint_0.3.md`: cada seção é uma unidade de
> implementação, marcada `[x]` quando concluída.
>
> Estado inicial: o site está **em produção** em `https://lilian.victordg.dev.br`, servindo serviços
> com agendamento e produtos/curso. Esta sprint acrescenta conteúdo editorial e automatiza o deploy.

## Objetivo

A Lilian precisa publicar textos que apareçam junto dos cards de serviço e produto na home. O blog é
**só conteúdo** — não vende, não cobra, não cria pedido. É o canal de atração; a venda continua sendo
feita pelos fluxos que já existem.

## Decisões fechadas (2026-08-06) — não revisitar sem motivo

| Tema | Decisão | Por quê |
|---|---|---|
| Conteúdo do post | **Texto puro** (textarea + `white-space: pre-wrap`) | Zero dependência nova, zero superfície de XSS. Respeita o guardrail do `CLAUDE.md` de não adicionar lib quando o nativo resolve |
| Imagem de capa | **URL externa** (campo de texto) | Sem rota de upload, sem volume, sem backup de diretório, sem validação de tipo/tamanho |
| Navegação | **Seção na home + `/blog/<slug>`** | Cada post vira URL indexável — é o motivo de ter blog |
| CI/CD | **Esteira completa** `feature → dev → main` com 1 aprovação | Mesmo padrão dos outros 4 projetos da VPS; o gate humano protege um site que cobra dinheiro |

---

## 1. [x] Modelo de Dados — `Post`

Em `app/models.py`, seguindo a convenção de `Servico`/`Produto` (sem relacionamento, sem
`tenant_id`, sem estoque):

```python
class Post(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    titulo: str
    slug: str = Field(index=True, unique=True)
    resumo: Optional[str] = None            # card na home + meta description
    conteudo: str                            # texto puro, quebras de linha preservadas
    imagem_url: Optional[str] = None         # link externo, sem upload
    publicado: bool = Field(default=False)   # rascunho não aparece em lugar nenhum
    publicado_em: Optional[datetime] = None
    criado_em: datetime = Field(default_factory=datetime.utcnow)
```

**O `Post` não tem `preco` nem `status`.** Essa é a diferença estrutural em relação ao `Produto`, e é
o que impede o blog de virar caminho de compra por acidente — ver seção 6.

## 2. [x] Slug sem dependência nova

Novo arquivo `app/slug.py`, só com stdlib (`unicodedata` + `re`):

```python
def slugify(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
```

O slug é gerado a partir do título no `on_model_change` do SQLAdmin. Se já existir um igual, sufixa
`-2`, `-3`… A `unique=True` no banco é a última linha de defesa — mesmo padrão de "checa antes, banco
garante" já usado na `Reserva`.

## 3. [x] Migration

```bash
alembic revision --autogenerate -m "adiciona post"
```

**Revisar o arquivo gerado antes de aplicar.** O autogenerate erra em índices — lição já registrada
no `CLAUDE.md` (seção 7). Conferir especificamente que o índice único do `slug` apareceu no
`upgrade()`.

## 4. [x] Rotas Públicas — `app/routes_public.py`

| Rota | O que faz |
|---|---|
| `GET /` | acrescenta `posts` ao contexto: publicados, ordenados por `publicado_em` desc, **limit 3** |
| `GET /blog` | listagem completa dos publicados |
| `GET /blog/{slug}` | post individual; `publicado=False` ou slug inexistente → **404** |

Todas são `GET` e **nenhuma leva `Depends(verificar_csrf)`** — não há POST no blog, e isso é
intencional, não esquecimento.

Reusar o mesmo padrão de query já usado para `Servico`/`Produto`:
`(await session.exec(select(Post).where(Post.publicado == True))).all()`.

## 5. [x] Templates e SEO

- `templates/index.html` — nova `<section id="blog">` reusando `.grid` e `.card`, que já existem no
  `style.css`. O card leva a `/blog/<slug>` por um **link**, nunca por formulário ou botão de compra.
- `templates/blog.html` — listagem completa.
- `templates/post.html` — estende `base.html`; renderiza `{{ post.conteudo }}` com
  `white-space: pre-wrap`. O Jinja2 escapa por padrão, então texto puro é seguro sem sanitização.
- `templates/static/style.css` — só o mínimo (`.post-body`, `.post-capa`), usando as variáveis
  `:root` que já existem (`--ink`, `--muted`, `--border`, `--radius`).

SEO — o `app/main.py` já tem `/robots.txt` e o middleware de `noindex`. Acrescentar:
- `<title>`, meta description (do `resumo`), canonical e Open Graph no `post.html`
- JSON-LD `Article` no post
- **`/sitemap.xml`** dinâmico com `/`, `/blog` e cada post publicado — e **nunca** `/admin`,
  `/checkout`, `/healthz` ou rascunhos

## 6. [ ] Guardrails — regras que a implementação não pode violar

Cada item aqui tem teste correspondente na seção 7. Se um teste desta lista quebrar, é regressão, não
"teste desatualizado".

1. **Blog não vende.** Nenhuma rota `POST` no blog, nenhum campo de preço no `Post`, nenhum
   `external_reference` do tipo `post:`. O webhook do Mercado Pago segue atendendo só `reserva:` e
   `pedido:`.
2. **CSRF intacto.** `/reservar`, `/comprar` e `/pagar` seguem exigindo o token; `/webhook/*`
   continua sendo a **única** isenção.
3. **`SQL_ECHO` continua `False` por padrão.** Ligado em produção, vaza nome, e-mail e telefone dos
   contatos para o Loki via stdout.
4. **`/healthz` continua respondendo 200** com o banco de pé. O deploy usa `--wait` e falha sem ela.
5. **`/admin` continua com `X-Robots-Tag: noindex`** e fora do `sitemap.xml`.
6. **Rascunho não vaza.** `publicado=False` → 404 na página, ausente da home, da listagem e do
   sitemap.
7. **Sem dependência nova** no `requirements.txt` por causa do blog.

## 7. [ ] Testes

Seguem o padrão do `testes/conftest.py`: Postgres real, fixture `client` já com o header CSRF.

### `testes/test_blog.py`
- post publicado aparece na home e responde 200 em `/blog/<slug>`
- rascunho → 404 na página e ausente da home
- slug duplicado recebe sufixo e não estoura `IntegrityError`
- `/sitemap.xml` contém o publicado e **não** contém rascunho, `/admin` nem `/healthz`
- conteúdo com `<script>` sai escapado no HTML (prova do autoescape)

### `testes/test_guardrails.py`
- `settings.SQL_ECHO is False` e `settings.SESSION_HTTPS_ONLY is True` nos defaults
- `/healthz` → 200
- `/admin` → header `X-Robots-Tag`
- **varredura das rotas do app**: nenhuma rota `POST` fora da lista conhecida (`/reservar`,
  `/comprar`, `/pagar`, `/webhook/mercadopago`, mais as do SQLAdmin)

O último é o guardrail mais valioso da sprint: qualquer rota de escrita criada por descuido quebra o
teste e aparece no PR antes de chegar em produção.

## 8. [ ] Esteira CI/CD

Copiar os três templates de `/home/victor/Projetos/vps-infra/ci/templates/` para
`.github/workflows/`, adaptando só o necessário.

### `ci.yml` — job `test`

Duas adaptações **obrigatórias**, ambas descobertas na prática:

**Postgres real como service container.** SQLite não serve — a trava de reserva usa
`SELECT ... FOR UPDATE`, que o SQLite não implementa de fato, então um teste de concorrência passaria
mesmo com a trava quebrada. Já é regra no `CLAUDE.md`.

```yaml
services:
  postgres:
    image: postgres:16
    env: { POSTGRES_USER: postgres, POSTGRES_PASSWORD: postgres, POSTGRES_DB: app_db_test }
    ports: ["5432:5432"]
    options: >-
      --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10
```

**`python -m pytest`, não `pytest`.** Verificado ao rodar a suíte na VPS: com `pytest` puro o
`conftest.py` estoura `ModuleNotFoundError: No module named 'app'`, porque a raiz do repo não entra
no `sys.path`. O `-m` resolve.

Passos: `setup-python@v5` (3.12) → `pip install -r requirements.txt` → `python -m pytest`, com
`DATABASE_URL` e os `MERCADO_PAGO_*` / `ADMIN_*` de teste no `env` do job.

### `guard-main-source.yml` — job `guard`

Cópia literal do template, sem alteração. Falha o PR para `main` que não venha de `dev`.

### `deploy.yml` — job `deploy`

Baseado no template, com **uma diferença crítica** em relação aos outros 4 projetos: aqui o compose
mora em `Infra/` e o `.env` na raiz, então o `--env-file` é obrigatório. Sem ele, `${DB_PASSWORD}`
resolve para string vazia com apenas um *warning* — não um erro — e a app sobe sem conseguir
autenticar no banco.

```yaml
runs-on: [self-hosted, vps-prod]
env:
  SRC_DIR:   /home/victor/Projetos/Publicado/LilianKaliaki
  REPO:      VictorDG00/LilianKaliaki
  CONTAINER: liliankaliaki
steps:
  - git config --global --add safe.directory "$SRC_DIR"
  - cd "$SRC_DIR" && git fetch <token-url> main && git reset --hard FETCH_HEAD
  - docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build --wait --wait-timeout 180
  - se falhar: docker compose ... logs --tail=80 liliankaliaki
```

### Configuração no GitHub e na VPS

1. Criar a branch `dev` a partir da `main`.
2. Registrar o runner **repo-level** em `/home/victor/actions-runner-liliankaliaki/`, labels
   `self-hosted,vps-prod`, serviço systemd como root. Registro **org-level não funciona** — deixa os
   jobs presos em `queued`, lição registrada no `vps-infra/CLAUDE.md`.
3. Aplicar os rulesets:
   ```bash
   gh api -X POST /repos/VictorDG00/LilianKaliaki/rulesets --input vps-infra/ci/rulesets/main.json
   gh api -X POST /repos/VictorDG00/LilianKaliaki/rulesets --input vps-infra/ci/rulesets/dev.json
   gh api -X PATCH /repos/VictorDG00/LilianKaliaki -F allow_auto_merge=true -F delete_branch_on_merge=true
   ```
4. **O repo precisa ser público.** Em conta free, repositório privado não impõe rulesets nem
   auto-merge — o EstudeOAB foi tornado público exatamente por isso.

### ⚠️ Passo 0 — pré-requisito de sequência

A produção hoje roda a partir da branch **`feat/deploy-vps`**, que ainda **não foi mergeada nem
enviada** ao remoto. O `deploy.yml` faz `git reset --hard FETCH_HEAD` da `main`. Ligar a esteira
antes do merge faria:

- o checkout de produção voltar para a `main` antiga, **sem** `/healthz`, sem CSRF e sem os ajustes
  de segurança;
- o `--wait` falhar, porque o healthcheck aponta para uma rota que deixou de existir;
- o site sair do ar até intervenção manual.

**Ordem obrigatória:** mergear `feat/deploy-vps` → `main` e deixar o checkout de produção na `main`
**antes** de registrar o runner e aplicar os rulesets.

## 9. [ ] Como o código passa a ser puxado sozinho

```
você faz push               →  GitHub
PR feature → dev            →  check `test` verde → auto-merge (sem aprovação humana)
PR dev → main               →  checks `test` + `guard` verdes + 1 aprovação sua
merge na main               →  dispara o workflow `deploy`
runner self-hosted na VPS   →  git fetch + reset --hard + compose up --build --wait
                            →  alembic upgrade head roda no start do container
                            →  healthcheck confirma /healthz antes de concluir o deploy
```

O runner **sai** da VPS para buscar trabalho no GitHub — não abre porta nenhuma no UFW. E como o
deploy sempre busca o HEAD atual da `main`, rodar o workflow duas vezes seguidas é idempotente.

---

## Verificação de fim a fim

```bash
# 1. Suíte completa contra Postgres real, em rede Docker isolada.
#    Não usar o Infra/docker-compose.yml aqui: ele publica Postgres em 0.0.0.0,
#    e publicação de porta no Docker fura as regras do UFW.
docker run --rm --network lk-test -v "$PWD":/app -w /app \
  -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@lk-test-db:5432/app_db_test \
  liliankaliaki-app:local python -m pytest -q

# 2. Subir e conferir healthy
docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build --wait
docker exec nginx-proxy wget -qO- http://liliankaliaki:8000/healthz

# 3. Blog no ar
curl -s https://lilian.victordg.dev.br/blog/<slug> | grep -oE "<title>[^<]*</title>"
curl -s https://lilian.victordg.dev.br/sitemap.xml      # publicado sim, rascunho/admin não
curl -sI https://lilian.victordg.dev.br/admin | grep -i x-robots-tag

# 4. Provar que o guardrail trava de verdade: criar uma rota POST qualquer
#    numa branch e confirmar que test_guardrails falha
```

Na esteira: abrir PR `feature → dev` e ver o `test` verde com auto-merge; abrir `dev → main` e ver o
`guard` passar e a aprovação ser exigida; aprovar e confirmar que o container `liliankaliaki` foi
recriado, ficou `healthy` e o post novo está visível no site.

---

## Pendências herdadas da sprint anterior

Não bloqueiam esta sprint, mas seguem abertas:

- `MERCADO_PAGO_ACCESS_TOKEN` / `PUBLIC_KEY` / `WEBHOOK_SECRET` no `.env` de produção ainda são
  placeholders `TROCAR-...` — navegar funciona, o Checkout Bricks não.
- `step-by-step.md` (seção 0) e `CLAUDE.md` (seção 8) descrevem o estado anterior ao deploy: citam
  `/healthz` e a rede `vps-proxy` como pendentes, e o compose com `127.0.0.1:${APP_PORT}`. Ambos já
  foram resolvidos em 06/08/2026.
