"""Enriquece registros sin coordenadas usando el geocodificador OSM.

Conservador: solo rellena cuando faltan lat/lng; nunca sobrescribe coordenadas
existentes. Marca los registros geocodificados con `geocodificado=True` para
trazabilidad.
"""

from __future__ import annotations

from collections.abc import Callable

from . import geocodificador


def construir_consulta(rec: dict) -> str:
    """Arma la mejor consulta textual disponible, acotada a Venezuela."""
    partes = []
    for campo in ("organization", "location_name", "city", "state"):
        v = rec.get(campo)
        if v and str(v).strip() and str(v).strip().lower() not in [p.lower() for p in partes]:
            partes.append(str(v).strip())
    if not partes:
        return ""
    return ", ".join(partes) + ", Venezuela"


def tiene_coordenadas(rec: dict) -> bool:
    return rec.get("latitude") is not None and rec.get("longitude") is not None


def enriquecer(
    records: list[dict],
    *,
    cache: dict | None = None,
    geocode: Callable[..., tuple | None] | None = None,
    fetch=None,
) -> tuple[list[dict], int]:
    """Devuelve (registros_enriquecidos, cuántos se geocodificaron).

    No muta los registros originales.
    """
    if cache is None:
        cache = {}
    geo = geocode or geocodificador.geocodificar
    salida: list[dict] = []
    geocodificados = 0
    for rec in records:
        copia = dict(rec)
        if not tiene_coordenadas(copia):
            consulta = construir_consulta(copia)
            if consulta:
                coords = geo(consulta, fetch=fetch, cache=cache)
                if coords:
                    copia["latitude"], copia["longitude"] = coords[0], coords[1]
                    copia["geocodificado"] = True
                    geocodificados += 1
        salida.append(copia)
    return salida, geocodificados
