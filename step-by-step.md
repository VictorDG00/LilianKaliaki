# Deploy na VPS (produção, isolado dos outros projetos)

O repo já vem pronto pra rodar containerizado: `Infra/Dockerfile` +
`Infra/docker-compose.prod.yml` sobem a app e o Postgres em containers
próprios, numa rede interna própria (`liliankaliaki`), sem expor o banco ao
host e sem tocar em nada dos outros projetos que já estão na VPS. O que
falta é só o que só você pode decidir/fazer na própria VPS — segue abaixo.

Todos os comandos abaixo rodam **a partir da raiz do repo** (não de dentro de
`Infra/`) e sempre com `--env-file .env` — o arquivo de compose fica em
`Infra/` mas o `.env` de segredos fica na raiz, e por padrão o Docker Compose
só procura `.env` na pasta onde está o arquivo de compose. Se preferir não
digitar o `--env-file .env` toda hora, dá pra fixar isso na sessão do shell:

```bash
alias dc='docker compose --env-file .env -f Infra/docker-compose.prod.yml'
```

(daí os comandos viram só `dc up -d --build`, `dc ps`, etc. — opcional, os
exemplos abaixo usam a forma completa para não depender do alias).

## 1. Pré-requisitos na VPS

Só precisa de Docker + Docker Compose plugin instalados:

```bash
docker --version
docker compose version
```

Se não tiver, instalar Docker Engine (docs oficiais do Docker) antes de continuar.

## 2. Copiar o repo e criar o `.env` de produção

```bash
git clone <url-do-repo> liliankaliaki
cd liliankaliaki
cp .env.exemple .env
```

**Não copie o `.env` de dev/Codespace para a VPS.** Edite o `.env` novo com
valores reais de produção:

- `DATABASE_URL` — pode deixar como está no exemplo (`localhost`), o
  `docker-compose.prod.yml` sobrescreve isso automaticamente para apontar
  pro container `db`.
- `SECRET_KEY` — gere uma nova (não reaproveite a de dev):
  `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
- `MERCADO_PAGO_ACCESS_TOKEN` / `MERCADO_PAGO_PUBLIC_KEY` — as credenciais de
  **produção** do Mercado Pago (as `TEST-...` são só para sandbox).
- `MERCADO_PAGO_WEBHOOK_SECRET` — vem do passo 5 abaixo, pode deixar
  placeholder por enquanto.
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — credenciais reais do `/admin`, senha forte.
- `DB_PASSWORD` — senha forte só para o Postgres de produção (variável nova,
  usada pelo `docker-compose.yml`).
- `APP_PORT=9765` — porta escolhida para não colidir com os outros projetos
  da VPS (já é o padrão do compose, só precisa bater se você quiser mudar).

## 3. Subir a stack

```bash
docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build
docker compose -f Infra/docker-compose.prod.yml ps
docker compose -f Infra/docker-compose.prod.yml logs -f app
```

Espera-se ver no log o `alembic upgrade head` rodando sem erro e depois o
uvicorn subindo (`Uvicorn running on http://0.0.0.0:8000`). `docker compose ps`
deve mostrar `db` como `healthy` e `app` como `running`.

Teste local na própria VPS (antes de configurar o proxy):

```bash
curl -i http://127.0.0.1:9765/
```

## 4. Configurar o reverse proxy existente

A app só escuta em `127.0.0.1:9765` — não é exposta à internet diretamente,
só o reverse proxy que já roda os outros projetos da VPS enxerga essa porta.
Exemplo de bloco nginx (adaptar para o seu domínio e para o padrão de TLS que
os outros projetos já usam, ex: certbot):

```nginx
server {
    server_name seudominio.com.br;

    location / {
        proxy_pass http://127.0.0.1:9765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Depois de configurar, `nginx -t && systemctl reload nginx` (ou equivalente).

## 5. Webhook do Mercado Pago

No painel do Mercado Pago (produção), atualizar a URL de notificação para:

```
https://seudominio.com.br/webhook/mercadopago
```

Copiar o webhook secret gerado lá e colar em `MERCADO_PAGO_WEBHOOK_SECRET`
no `.env` da VPS, depois:

```bash
docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build
```

(reinicia a app já com o secret novo carregado).

## 6. Manutenção

Sempre com `-f Infra/docker-compose.prod.yml` (e `--env-file .env` nos
comandos que sobem/recriam containers, como `up`):

- Ver logs: `docker compose -f Infra/docker-compose.prod.yml logs -f` (todos)
  ou `... logs -f app`
- Reiniciar só a app: `docker compose -f Infra/docker-compose.prod.yml restart app`
- Atualizar após `git pull`:
  `docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build`
  (reaplica `alembic upgrade head` automaticamente no start do container)
- Derrubar tudo: `docker compose -f Infra/docker-compose.prod.yml down` —
  **não** apaga o volume `pgdata`, os dados do banco continuam. Para apagar
  de fato: `docker compose -f Infra/docker-compose.prod.yml down -v`
  (cuidado, isso é destrutivo).

## 7. Isolamento — o que isso garante

- Postgres **não** expõe porta nenhuma ao host nem à VPS — só existe dentro
  da rede interna do compose (`liliankaliaki_internal`).
- A app só é alcançável via `127.0.0.1:9765`, ou seja, só o processo do
  reverse proxy da própria VPS consegue falar com ela — nada é exposto
  diretamente à internet pelo container.
- Containers, rede e volume são todos namespaced por `liliankaliaki` (campo
  `name:` no `docker-compose.prod.yml`), então não colidem com os outros
  projetos mesmo que usem nomes genéricos como `db` ou `app`.
- `Infra/docker-compose.yml` (usado em dev/Codespace e pela suíte de testes)
  não foi alterado — o fluxo de desenvolvimento continua igual.
