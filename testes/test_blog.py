"""Blog: post publicado aparece, rascunho nao vaza, conteudo sai escapado."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Post
from app.slug import slug_unico, slugify


async def _seed_post(session, titulo, slug, publicado, conteudo="Texto do post."):
    post = Post(
        titulo=titulo,
        slug=slug,
        resumo=f"Resumo de {titulo}",
        conteudo=conteudo,
        publicado=publicado,
        publicado_em=datetime.utcnow() - timedelta(days=1) if publicado else None,
    )
    session.add(post)
    await session.commit()
    await session.refresh(post)
    return post


async def test_post_publicado_aparece_na_home_e_tem_pagina(client, session):
    await _seed_post(session, "Cuidados no inverno", "cuidados-inverno", publicado=True)

    home = await client.get("/")
    assert "/blog/cuidados-inverno" in home.text

    pagina = await client.get("/blog/cuidados-inverno")
    assert pagina.status_code == 200
    assert "Cuidados no inverno" in pagina.text


async def test_rascunho_nao_vaza(client, session):
    await _seed_post(session, "Rascunho", "rascunho-secreto", publicado=False)

    home = await client.get("/")
    assert "rascunho-secreto" not in home.text

    listagem = await client.get("/blog")
    assert "rascunho-secreto" not in listagem.text

    # 404 igual ao de slug inexistente: nao revela que o post existe
    assert (await client.get("/blog/rascunho-secreto")).status_code == 404
    assert (await client.get("/blog/nunca-existiu")).status_code == 404


async def test_sitemap_lista_publicado_e_esconde_o_resto(client, session):
    await _seed_post(session, "Publicado", "post-publicado", publicado=True)
    await _seed_post(session, "Rascunho", "post-rascunho", publicado=False)

    sitemap = await client.get("/sitemap.xml")

    assert sitemap.status_code == 200
    assert "/blog/post-publicado" in sitemap.text
    assert "post-rascunho" not in sitemap.text
    assert "/admin" not in sitemap.text
    assert "/healthz" not in sitemap.text


async def test_conteudo_do_post_sai_escapado(client, session):
    await _seed_post(
        session,
        "Com script",
        "com-script",
        publicado=True,
        conteudo="Antes <script>alert(1)</script> depois",
    )

    pagina = await client.get("/blog/com-script")

    assert "<script>alert(1)</script>" not in pagina.text
    assert "&lt;script&gt;" in pagina.text


def test_slugify_normaliza_acento_e_pontuacao():
    assert slugify("Corte & Escova: dicas!") == "corte-escova-dicas"
    assert slugify("Manutenção do cabelo") == "manutencao-do-cabelo"


def test_slug_unico_sufixa_em_colisao():
    assert slug_unico("Cuidados", []) == "cuidados"
    assert slug_unico("Cuidados", ["cuidados"]) == "cuidados-2"
    assert slug_unico("Cuidados", ["cuidados", "cuidados-2"]) == "cuidados-3"


async def test_slug_duplicado_e_rejeitado_pelo_banco(session):
    """A unique=True e a ultima linha de defesa se o slug_unico for contornado."""
    await _seed_post(session, "Primeiro", "mesmo-slug", publicado=True)

    with pytest.raises(IntegrityError):
        await _seed_post(session, "Segundo", "mesmo-slug", publicado=True)

    await session.rollback()
