"""Normalización de texto, espejo de app/search.py de redayuda.

Se replica aquí (en vez de importar app.search) para que el bot sea un
componente independiente y sin dependencias del backend; el algoritmo es el
mismo: minúsculas, ñ→n, sin acentos, solo alfanumérico, espacios colapsados.
"""

from __future__ import annotations

import re
import unicodedata

_NONALNUM = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")


def normalizar(value) -> str:
    if value is None:
        return ""
    text = str(value).lower().replace("ñ", "n")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = _NONALNUM.sub(" ", text)
    return _WS.sub(" ", text).strip()


def tokens(value) -> list[str]:
    return [t for t in normalizar(value).split(" ") if t]


def solo_digitos(value) -> str:
    return re.sub(r"\D+", "", str(value or ""))
