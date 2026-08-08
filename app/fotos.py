# Upload de foto de servico/produto.
#
# Tudo que entra vira WebP redimensionado. Nao existe caminho que grave o
# arquivo do jeito que veio: e o que garante que nao da para subir um .php
# renomeado para .jpg, e de quebra corta ~30% do peso na tela do cliente.

import shutil
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

MEDIA_DIR = Path("media")
LADO_MAXIMO = 1200
QUALIDADE = 82
TAMANHO_MAXIMO = 8 * 1024 * 1024  # 8 MB


class FotoInvalida(Exception):
    """Arquivo que nao vira foto — a mensagem vai direto para a tela."""


async def salvar_foto(upload: UploadFile, pasta: str) -> str:
    """Grava a imagem como WebP e devolve o caminho relativo a media/.

    `pasta` e algo como "servico/3". A validacao de verdade e o Pillow abrir o
    arquivo: content-type e extensao vem do navegador e nao valem nada.
    """
    conteudo = await upload.read()
    if len(conteudo) > TAMANHO_MAXIMO:
        raise FotoInvalida("Imagem acima de 8 MB.")

    try:
        imagem = Image.open(BytesIO(conteudo))
        imagem.load()
    except (UnidentifiedImageError, OSError):
        raise FotoInvalida("Arquivo não é uma imagem válida.")

    # WebP nao aceita paleta/CMYK; RGBA sobrevive (transparencia do PNG).
    if imagem.mode not in ("RGB", "RGBA"):
        imagem = imagem.convert("RGBA" if "A" in imagem.getbands() else "RGB")
    imagem.thumbnail((LADO_MAXIMO, LADO_MAXIMO))

    destino_dir = MEDIA_DIR / pasta
    destino_dir.mkdir(parents=True, exist_ok=True)
    nome = f"{uuid.uuid4().hex}.webp"
    imagem.save(destino_dir / nome, "WEBP", quality=QUALIDADE)
    return f"{pasta}/{nome}"


def remover_arquivo(caminho_relativo: str) -> None:
    """Apaga o arquivo do disco. Ausente ja e o estado desejado."""
    (MEDIA_DIR / caminho_relativo).unlink(missing_ok=True)


def apagar_pasta(dono: str, item_id: int) -> None:
    """Chamado quando o servico/produto some: leva os arquivos junto."""
    shutil.rmtree(MEDIA_DIR / dono / str(item_id), ignore_errors=True)
