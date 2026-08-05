# Entrypoint do FastAPI + Mount do Admin

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from app.admin import setup_admin
from app.database import engine
from app.tasks import expirar_reservas_loop

import app.routes_public as routes_public
import app.routes_webhook as routes_webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(expirar_reservas_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
admin = setup_admin(app, engine)

app.mount("/static", StaticFiles(directory="templates/static"), name="static")

app.include_router(routes_public.router)
app.include_router(routes_webhook.router)



