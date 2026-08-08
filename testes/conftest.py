import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/app_db_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MERCADO_PAGO_ACCESS_TOKEN", "test-access-token")
os.environ.setdefault("MERCADO_PAGO_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("MERCADO_PAGO_PUBLIC_KEY", "test-public-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin-secreto")

import re
import subprocess
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    # sys.executable -m: funciona com o venv nao ativado (o binario `alembic` so
    # entra no PATH depois do activate; o interpretador atual sempre serve).
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    yield
    async with SessionLocal() as db:
        await db.execute(
            text(
                "TRUNCATE reserva, pedido, contato, servico, produto, disponibilidade, post "
                "RESTART IDENTITY CASCADE"
            )
        )
        await db.commit()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    # base_url https porque o cookie de sessao e Secure (SESSION_HTTPS_ONLY):
    # em http:// o httpx guardaria o cookie mas nunca o devolveria, e o CSRF
    # nunca fecharia. O ASGITransport nao faz TLS de verdade, so muda o scheme.
    async with AsyncClient(transport=transport, base_url="https://test") as ac:
        # GET / cria a sessao e devolve o token no hx-headers do <body>;
        # a partir daqui todo POST do teste ja vai com o header, como o HTMX faz.
        home = await ac.get("/")
        token = re.search(r'X-CSRF-Token": "([^"]+)"', home.text)
        if token:
            ac.headers["X-CSRF-Token"] = token.group(1)
        yield ac


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as db:
        yield db
