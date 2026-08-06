# Entrypoint do FastAPI + Mount do Admin

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware
from app.admin import setup_admin
from app.config import settings
from app.database import engine
from app.tasks import expirar_reservas_loop

import app.routes_public as routes_public
import app.routes_webhook as routes_webhook

# Rotas que nunca devem aparecer em buscador. Cache-Control impede
# armazenamento; X-Robots-Tag impede indexacao — sao controles diferentes.
PREFIXOS_PRIVADOS = ("/admin", "/healthz")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(expirar_reservas_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=settings.SESSION_HTTPS_ONLY,
    same_site="lax",
)
admin = setup_admin(app, engine)

app.mount("/static", StaticFiles(directory="templates/static"), name="static")


@app.middleware("http")
async def marcar_rotas_privadas(request: Request, call_next) -> Response:
    resposta = await call_next(request)
    if request.url.path.startswith(PREFIXOS_PRIVADOS):
        resposta.headers["X-Robots-Tag"] = "noindex, nofollow"
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.get("/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    """Usado pelo healthcheck do container — o deploy da VPS espera ficar healthy."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "erro", "banco": "indisponivel"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.get("/robots.txt", include_in_schema=False)
async def robots() -> PlainTextResponse:
    return PlainTextResponse("User-agent: *\nDisallow: /admin\nDisallow: /healthz\n")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    """So conteudo publico: rascunho, /admin e /healthz nunca entram aqui."""
    from sqlmodel import select

    from app.database import SessionLocal
    from app.models import Post

    base = str(request.base_url).rstrip("/")
    urls = [(f"{base}/", None), (f"{base}/blog", None)]
    async with SessionLocal() as session:
        posts = (
            await session.exec(
                select(Post).where(Post.publicado == True).order_by(Post.publicado_em.desc())  # noqa: E712
            )
        ).all()
    urls += [(f"{base}/blog/{p.slug}", p.publicado_em) for p in posts]

    corpo = "".join(
        f"<url><loc>{loc}</loc>"
        + (f"<lastmod>{quando.date().isoformat()}</lastmod>" if quando else "")
        + "</url>"
        for loc, quando in urls
    )
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{corpo}</urlset>',
        media_type="application/xml",
    )


app.include_router(routes_public.router)
app.include_router(routes_webhook.router)



