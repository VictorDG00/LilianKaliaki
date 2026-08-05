# Deploy na VPS (produção, isolado dos outros projetos)

O repo já vem pronto pra rodar containerizado: `Infra/Dockerfile` +
`Infra/docker-compose.prod.yml` sobem a app e o Postgres em containers
próprios, sem expor o banco ao host e sem tocar em nada dos outros projetos
que já estão na VPS (`srv1662201`). O que falta é só o que só você pode
decidir/fazer na própria VPS — segue abaixo.

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

## 0. Pendências antes de seguir este guia numa VPS de verdade

A `srv1662201` não usa nginx no host + certbot + porta publicada — ela usa um
`nginx-proxy` **em container**, numa rede Docker compartilhada (`vps-proxy`),
com TLS terminado no Cloudflare. Este guia já descreve esse fluxo final, mas
três coisas ainda **não** estão implementadas no repo e precisam ser feitas
antes dos passos 3–4 funcionarem numa VPS real:

- **Rota `/healthz`** — não existe ainda no app (checado: nenhum
  `app/*.py` tem `healthz`/`health_check`). Precisa existir e checar conexão
  com o banco, porque o deploy da VPS usa `--wait` e depende dela.
- **`Infra/docker-compose.prod.yml`** hoje publica porta pro host
  (`127.0.0.1:${APP_PORT}:8000`) e não tem healthcheck no serviço `app`.
  Precisa virar `expose: ["8000"]` + entrar também na rede externa
  `vps-proxy` + `container_name: liliankaliaki` fixo (o proxy resolve o
  upstream por esse nome) + healthcheck usando a rota acima.
- **`Infra/Dockerfile`** sobe o uvicorn sem `--proxy-headers
  --forwarded-allow-ips="*"` — necessário atrás do proxy compartilhado, senão
  `request.url_for()` e o IP do cliente saem errados.

Essas mudanças de infra ficam para depois (fora do escopo desta atualização
do doc) — só o texto do guia foi alinhado com o que a VPS de verdade exige.

## 1. Pré-requisitos na VPS

Só precisa de Docker + Docker Compose plugin instalados:

```bash
docker --version
docker compose version
```

Se não tiver, instalar Docker Engine (docs oficiais do Docker) antes de continuar.

## 2. Copiar o repo e criar o `.env` de produção

Seguindo a convenção de diretório já usada nos outros projetos da VPS:

```bash
git clone <url-do-repo> /home/victor/Projetos/Publicado/liliankaliaki
cd /home/victor/Projetos/Publicado/liliankaliaki
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

Não precisa mais de `APP_PORT`: como a app deixa de publicar porta no host
(rede compartilhada `vps-proxy`, ver seção 0), essa variável some do modelo
final — ela só existe hoje porque o compose ainda usa o formato antigo.

## 3. Subir a stack

```bash
docker compose --env-file .env -f Infra/docker-compose.prod.yml up -d --build
docker compose -f Infra/docker-compose.prod.yml ps
docker compose -f Infra/docker-compose.prod.yml logs -f app
```

Espera-se ver no log o `alembic upgrade head` rodando sem erro e depois o
uvicorn subindo (`Uvicorn running on http://0.0.0.0:8000`). `docker compose ps`
deve mostrar `db` e `app` como `healthy` (assumindo as pendências da seção 0
já resolvidas).

Teste local na própria VPS (antes de configurar o proxy) — como a app não
publica mais porta no host, o teste é de dentro da rede Docker, via o próprio
`nginx-proxy`:

```bash
docker exec nginx-proxy wget -qO- http://liliankaliaki:8000/healthz
```

## 4. Configurar o reverse proxy compartilhado (`nginx-proxy`)

A app **não** é alcançável por `127.0.0.1:porta` — ela só existe dentro da
rede Docker `vps-proxy`, e quem fala com ela de fora é o container
`nginx-proxy` que já roteia os outros projetos da VPS, pelo nome do container
(`liliankaliaki:8000`). TLS é terminado no Cloudflare — a origem fala HTTP
puro, então **não** tem `listen 443`/certbot nesse bloco:

```nginx
server {
    listen 80;
    server_name seudominio.com.br;

    location / {
        proxy_pass http://liliankaliaki:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $http_cf_connecting_ip;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Editar em `vps-infra/proxy/nginx.conf`, copiar para
`/home/victor/codigo/nginx-proxy/nginx.conf` (é de lá que o container monta
o arquivo) e recarregar sem downtime:

```bash
docker exec nginx-proxy nginx -t && docker exec nginx-proxy nginx -s reload
```

No Cloudflare: registro **A → IP da VPS com proxy laranja ligado**, e
**SSL/TLS em "Full" (idealmente "Full Strict" com Origin CA cert)** — não
"Flexible". Esse projeto processa pagamento (Mercado Pago) e dados pessoais
de agendamento/pedido, então vale terminar TLS de verdade na origem em vez de
deixar Cloudflare→VPS em HTTP puro pela internet pública.

## 5. Webhook do Mercado Pago

No painel do Mercado Pago (produção), atualizar a URL de notificação para:

```
https://seudominio.com.br/webhook/mercadopago
```

(a URL pública não muda — quem muda é só o que termina o TLS na frente dela,
ver seção 4). Copiar o webhook secret gerado lá e colar em
`MERCADO_PAGO_WEBHOOK_SECRET` no `.env` da VPS, depois:

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

Deploy aqui é manual (`git pull` + `up -d --build`) — a VPS tem uma esteira
de CI/CD com runner self-hosted disponível para os outros projetos (PR
`dev`→`main` aprovado dispara deploy sozinho), mas configurar isso pra este
projeto é opcional e fica fora do escopo deste guia por enquanto.

## 7. Isolamento — o que isso garante

- Postgres **não** expõe porta nenhuma ao host nem à VPS — só existe dentro
  da rede interna do compose (`liliankaliaki_internal`).
- A app não publica porta nenhuma para fora — só é alcançável dentro da rede
  Docker compartilhada `vps-proxy`, e só o container `nginx-proxy` fala com
  ela (pelo nome do container, não por IP/porta do host).
- Containers, rede e volume são todos namespaced por `liliankaliaki` (campo
  `name:` no `docker-compose.prod.yml`), então não colidem com os outros
  projetos mesmo que usem nomes genéricos como `db` ou `app`.
- `Infra/docker-compose.yml` (usado em dev/Codespace e pela suíte de testes)
  não foi alterado — o fluxo de desenvolvimento continua igual.
