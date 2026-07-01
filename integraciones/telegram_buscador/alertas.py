"""Suscripciones a alertas: avisa cuando una persona buscada aparece en el índice.

Estado persistido en un JSON liviano:
{
  "cursor": <int feed_seq ya consumido>,
  "suscripciones": [{"chat_id":..., "nombre":..., "cedula":..., "tokens":[...]}]
}

El cursor usa el feed incremental de redayuda (/api/records/feed?since=cursor),
así que no se reprocesan registros viejos.
"""

from __future__ import annotations

import json
import os

from .formato import es_aparicion
from .normaliza import solo_digitos, tokens


# Tope de suscripciones por usuario (evita que uno solo infle el estado / DoS).
MAX_ALERTAS_POR_USUARIO = 20


def estado_inicial() -> dict:
    return {"cursor": 0, "suscripciones": []}


def cargar(ruta: str) -> dict:
    if not os.path.exists(ruta):
        return estado_inicial()
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError, ValueError):
        # Archivo corrupto (p. ej. escritura interrumpida): no morir, reiniciar estado.
        return estado_inicial()
    if not isinstance(data, dict):
        return estado_inicial()
    data.setdefault("cursor", 0)
    data.setdefault("suscripciones", [])
    return data


def guardar(ruta: str, estado: dict) -> None:
    """Escritura ATÓMICA: escribe a un temporal y renombra, para sobrevivir a
    crashes/OOM (Fly puede matar el proceso) sin corromper el archivo."""
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(estado, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, ruta)  # rename atómico


def cuenta_usuario(estado: dict, chat_id) -> int:
    return sum(1 for s in estado["suscripciones"] if s["chat_id"] == chat_id)


def suscribir(estado: dict, chat_id, nombre: str, cedula: str | None = None) -> dict:
    sub = {
        "chat_id": chat_id,
        "nombre": nombre.strip(),
        "cedula": solo_digitos(cedula) or None,
        # Ordenados: la clave de nombre es independiente del orden de los apellidos.
        "tokens": sorted(tokens(nombre)),
    }
    if not sub["tokens"]:
        return estado
    for s in estado["suscripciones"]:
        if s["chat_id"] == chat_id and s["tokens"] == sub["tokens"]:
            return estado  # ya suscrito
    if cuenta_usuario(estado, chat_id) >= MAX_ALERTAS_POR_USUARIO:
        return estado  # tope alcanzado; no se añade
    estado["suscripciones"].append(sub)
    return estado


def quitar(estado: dict, chat_id, nombre: str) -> dict:
    tk = sorted(tokens(nombre))
    estado["suscripciones"] = [
        s for s in estado["suscripciones"]
        if not (s["chat_id"] == chat_id and s["tokens"] == tk)
    ]
    return estado


def mias(estado: dict, chat_id) -> list[str]:
    return [s["nombre"] for s in estado["suscripciones"] if s["chat_id"] == chat_id]


def _coincide(sub: dict, rec: dict) -> bool:
    # Cédula exacta gana (más fuerte y sin falsos positivos).
    ced_rec = solo_digitos(rec.get("cedula"))
    if sub.get("cedula") and ced_rec and sub["cedula"] == ced_rec:
        return True
    nombre_rec = tokens(rec.get("person_name") or rec.get("title"))
    if not sub["tokens"] or not nombre_rec:
        return False
    # Todos los tokens del nombre buscado deben estar en el nombre del registro.
    return all(t in nombre_rec for t in sub["tokens"])


def revisar(estado: dict, payload: dict) -> tuple[list[tuple], dict]:
    """Compara el lote del feed con las suscripciones.

    Devuelve (avisos, estado), donde avisos = [(chat_id, record), ...] solo para
    registros que sean una APARICIÓN (viva/herida/en necesidad/fallecida), no para
    nuevos reportes de "sigue desaparecida". Avanza el cursor.
    """
    avisos: list[tuple] = []
    for rec in payload.get("records", []):
        if not es_aparicion(rec):
            continue
        for sub in estado["suscripciones"]:
            if _coincide(sub, rec):
                avisos.append((sub["chat_id"], rec))
    nc = payload.get("next_cursor")
    if isinstance(nc, int):
        estado["cursor"] = nc
    return avisos, estado
