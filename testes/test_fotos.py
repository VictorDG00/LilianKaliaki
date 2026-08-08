"""Upload de foto. O que importa aqui e a fronteira: o que chega do navegador
nunca e gravado como veio, e nao passa de 4 por item."""

import io

import pytest
from PIL import Image
from sqlmodel import select

from app.fotos import MEDIA_DIR
from app.models import Foto, Servico
from testes.test_admin import admin  # noqa: F401  (fixture)


def _png(cor="red", tamanho=(2000, 100)):
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buffer, "PNG")
    buffer.seek(0)
    return buffer


@pytest.fixture(autouse=True)
def limpar_media():
    yield
    import shutil

    shutil.rmtree(MEDIA_DIR / "servico", ignore_errors=True)
    shutil.rmtree(MEDIA_DIR / "produto", ignore_errors=True)


async def _seed_servico(session):
    servico = Servico(titulo="Corte", duracao_min=60, preco=100.0, ativo=True)
    session.add(servico)
    await session.commit()
    await session.refresh(servico)
    return servico


async def test_upload_converte_para_webp_e_redimensiona(admin, session):  # noqa: F811
    servico = await _seed_servico(session)

    resposta = await admin.post(
        f"/admin/fotos/servico/{servico.id}/upload",
        files={"foto": ("foto.png", _png(), "image/png")},
    )

    assert resposta.status_code == 200
    foto = (await session.exec(select(Foto))).one()
    assert foto.arquivo.endswith(".webp")
    assert foto.servico_id == servico.id and foto.produto_id is None

    with Image.open(MEDIA_DIR / foto.arquivo) as imagem:
        assert imagem.format == "WEBP"
        assert max(imagem.size) <= 1200  # entrou com 2000px de largura


async def test_arquivo_que_nao_e_imagem_e_recusado(admin, session):  # noqa: F811
    """content-type do navegador nao vale nada — quem valida e o Pillow abrir."""
    servico = await _seed_servico(session)

    resposta = await admin.post(
        f"/admin/fotos/servico/{servico.id}/upload",
        files={"foto": ("virus.jpg", io.BytesIO(b"<?php echo 1; ?>"), "image/jpeg")},
    )

    assert "não é uma imagem válida" in resposta.text
    assert (await session.exec(select(Foto))).all() == []


async def test_limite_de_quatro_fotos(admin, session):  # noqa: F811
    servico = await _seed_servico(session)

    for _ in range(4):
        await admin.post(
            f"/admin/fotos/servico/{servico.id}/upload",
            files={"foto": ("foto.png", _png(tamanho=(50, 50)), "image/png")},
        )
    quinta = await admin.post(
        f"/admin/fotos/servico/{servico.id}/upload",
        files={"foto": ("foto.png", _png(tamanho=(50, 50)), "image/png")},
    )

    assert "Máximo de 4 fotos" in quinta.text
    assert len((await session.exec(select(Foto))).all()) == 4


async def test_remover_foto_apaga_linha_e_arquivo(admin, session):  # noqa: F811
    servico = await _seed_servico(session)
    await admin.post(
        f"/admin/fotos/servico/{servico.id}/upload",
        files={"foto": ("foto.png", _png(tamanho=(50, 50)), "image/png")},
    )
    foto = (await session.exec(select(Foto))).one()
    caminho = MEDIA_DIR / foto.arquivo

    await admin.post(f"/admin/fotos/servico/{servico.id}/remover/{foto.id}")

    assert (await session.exec(select(Foto))).all() == []
    assert not caminho.exists()


async def test_upload_exige_login(client, session):
    servico = await _seed_servico(session)

    resposta = await client.post(
        f"/admin/fotos/servico/{servico.id}/upload",
        files={"foto": ("foto.png", _png(tamanho=(50, 50)), "image/png")},
        follow_redirects=False,
    )

    assert resposta.status_code in (302, 303)
    assert (await session.exec(select(Foto))).all() == []
