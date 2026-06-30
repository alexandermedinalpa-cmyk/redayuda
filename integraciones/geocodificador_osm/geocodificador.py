"""Geocodificación con Nominatim (OpenStreetMap) + caché local.

Política de uso de Nominatim (https://operations.osmfoundation.org/policies/nominatim/):
- Máximo 1 petición por segundo.
- User-Agent identificable obligatorio.
- Cachear resultados (no repetir consultas).
Este módulo respeta las tres: pausa entre llamadas reales, User-Agent propio y
caché en disco. Para volumen alto, lo correcto es un Nominatim auto-hospedado.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Callable

NOMINATIM = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "RedRescateVenezuela/0.1 (aporte humanitario altruista)"
PAUSA_SEG = 1.0  # respeta el límite de 1 req/seg

# fetch(url) -> objeto JSON ya parseado (lista de resultados de Nominatim)
Fetch = Callable[[str], object]


def _http_fetch(url: str) -> object:  # pragma: no cover - requiere red
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _clave(consulta: str) -> str:
    return " ".join(consulta.lower().split())


def geocodificar(
    consulta: str,
    *,
    fetch: Fetch | None = None,
    cache: dict | None = None,
    pausa: bool = True,
) -> tuple[float, float] | None:
    """Devuelve (lat, lng) o None. Usa caché (incluso para los 'no encontrado')."""
    consulta = (consulta or "").strip()
    if not consulta:
        return None
    clave = _clave(consulta)
    if cache is not None and clave in cache:
        val = cache[clave]
        return tuple(val) if val else None

    qs = urllib.parse.urlencode({
        "q": consulta, "format": "json", "limit": 1, "countrycodes": "ve",
    })
    url = "%s?%s" % (NOMINATIM, qs)
    usar = fetch or _http_fetch
    if fetch is None and pausa:
        time.sleep(PAUSA_SEG)
    try:
        datos = usar(url)
    except Exception:
        return None

    coords: tuple[float, float] | None = None
    if isinstance(datos, list) and datos:
        try:
            coords = (float(datos[0]["lat"]), float(datos[0]["lon"]))
        except (KeyError, ValueError, TypeError):
            coords = None
    if cache is not None:
        cache[clave] = list(coords) if coords else None
    return coords


def cargar_cache(ruta: str) -> dict:
    if not os.path.exists(ruta):
        return {}
    with open(ruta, "r", encoding="utf-8") as fh:
        return json.load(fh)


def guardar_cache(ruta: str, cache: dict) -> None:
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False, indent=2)
