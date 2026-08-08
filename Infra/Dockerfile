# Imagem de producao da app (FastAPI). Postgres roda em container separado (docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ponto de montagem do volume de fotos
RUN mkdir -p /app/media

EXPOSE 8000

# --proxy-headers/--forwarded-allow-ips: a app fica atras do nginx-proxy
# compartilhado da VPS. Sem isso, request.url_for() gera link http:// e o IP
# do cliente vira o IP do proxy.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
