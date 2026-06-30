"""Lógica de votos de verificación y cálculo de la etiqueta de confianza.

Estado (dict serializable a JSON):
  { "<record_id>": [ {"tipo": ..., "autor": ...}, ... ], ... }

Tipos de voto:
  - "confirma"   : confirmo que esta información es correcta / la persona apareció
  - "desmiente"  : esto es incorrecto / no es así
  - "sospecha"   : posible desinformación (foto falsa, reciclada)
  - "duplicado"  : este registro repite a otro

Anti-abuso: un autor solo cuenta UNA vez por registro (su último voto reemplaza
al anterior), evitando inflar la señal con votos repetidos.
"""

from __future__ import annotations

import json
import os
from collections import Counter

TIPOS = {"confirma", "desmiente", "sospecha", "duplicado"}


def estado_inicial() -> dict:
    return {}


def cargar(ruta: str) -> dict:
    if not os.path.exists(ruta):
        return estado_inicial()
    with open(ruta, "r", encoding="utf-8") as fh:
        return json.load(fh)


def guardar(ruta: str, estado: dict) -> None:
    carpeta = os.path.dirname(os.path.abspath(ruta))
    os.makedirs(carpeta, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(estado, fh, ensure_ascii=False, indent=2)


def registrar(estado: dict, record_id: str, tipo: str, autor: str) -> dict:
    if tipo not in TIPOS:
        raise ValueError("tipo de voto inválido: %r (válidos: %s)" % (tipo, sorted(TIPOS)))
    if not record_id or not autor:
        raise ValueError("record_id y autor son obligatorios")
    votos = estado.setdefault(record_id, [])
    # Un autor, un voto por registro: reemplaza su voto previo.
    votos[:] = [v for v in votos if v.get("autor") != autor]
    votos.append({"tipo": tipo, "autor": autor})
    return estado


def clasificar(confirma: int, desmiente: int, sospecha: int, duplicado: int) -> str:
    negativos = desmiente + sospecha
    if sospecha >= 2 and sospecha >= confirma:
        return "posible_desinformacion"
    if negativos >= 2 and negativos > confirma:
        return "en_disputa"
    if duplicado >= 2 and duplicado > confirma:
        return "posible_duplicado"
    if confirma >= 2 and negativos == 0:
        return "verificado_comunidad"
    if confirma >= 1 and negativos == 0:
        return "confirmacion_parcial"
    if negativos >= 1:
        return "en_disputa"
    return "sin_verificar"


def resumen(estado: dict, record_id: str) -> dict:
    votos = estado.get(record_id, [])
    c = Counter(v.get("tipo") for v in votos)
    etiqueta = clasificar(c["confirma"], c["desmiente"], c["sospecha"], c["duplicado"])
    return {
        "record_id": record_id,
        "confirma": c["confirma"],
        "desmiente": c["desmiente"],
        "sospecha": c["sospecha"],
        "duplicado": c["duplicado"],
        "total": len(votos),
        "etiqueta": etiqueta,
    }


def aplicar_overlay(estado: dict, records: list[dict]) -> list[dict]:
    """Devuelve copias de los registros con un campo 'verificacion' superpuesto.

    No muta los registros originales ni el índice de redayuda.
    """
    salida = []
    for r in records:
        rid = r.get("id")
        copia = dict(r)
        if rid:
            copia["verificacion"] = resumen(estado, rid)
        salida.append(copia)
    return salida
