"""Geracao de slug a partir do titulo. Só stdlib — nada de python-slugify."""

import re
import unicodedata


def slugify(texto: str) -> str:
    """"Corte & Escova: dicas!" -> "corte-escova-dicas" """
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")


def slug_unico(texto: str, existentes) -> str:
    """Sufixa -2, -3... se o slug ja estiver em uso.

    A unique=True no banco continua sendo a ultima linha de defesa; isto aqui
    so evita que a Lilian veja um erro ao publicar dois posts de titulo igual.
    """
    base = slugify(texto) or "post"
    existentes = set(existentes)
    if base not in existentes:
        return base
    n = 2
    while f"{base}-{n}" in existentes:
        n += 1
    return f"{base}-{n}"
