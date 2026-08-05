import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5433/app_db_test"
)
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MERCADO_PAGO_ACCESS_TOKEN", "test-access-token")
os.environ.setdefault("MERCADO_PAGO_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("MERCADO_PAGO_PUBLIC_KEY", "test-public-key")

import subprocess

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    yield
    async with SessionLocal() as db:
        await db.execute(
            text("TRUNCATE reserva, contato, servico, disponibilidade RESTART IDENTITY CASCADE")
        )
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
def mock_mercadopago_preference(monkeypatch):
    class _FakePreference:
        def create(self, data):
            return {"response": {"id": "fake-preference-id"}}

    class _FakeSDK:
        def __init__(self, access_token):
            pass

        def preference(self):
            return _FakePreference()

    monkeypatch.setattr("app.routes_public.mercadopago.SDK", _FakeSDK)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as db:
        yield db
