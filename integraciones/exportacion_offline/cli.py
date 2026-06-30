"""CLI: genera listas imprimibles desde un volcado JSON o desde la API en vivo.

  # Desde un archivo JSON con una lista de registros o {records:[...]} / {results:[...]}
  python -m integraciones.exportacion_offline.cli --entrada registros.json --salida listas.html

  # Desde la API de redayuda (trae el feed completo)
  python -m integraciones.exportacion_offline.cli --api https://nodo-redayuda --salida listas.html
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

from . import exportar


def _cargar_archivo(ruta: str) -> list[dict]:
    with open(ruta, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "records" in data:
            return data["records"]
        if "results" in data:
            return [r.get("record", r) for r in data["results"]]
    return []


def _cargar_api(base: str, limite: int = 5000) -> list[dict]:
    registros: list[dict] = []
    cursor = 0
    while len(registros) < limite:
        url = "%s/api/records/feed?since=%d&limit=500" % (base.rstrip("/"), cursor)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        lote = data.get("records", [])
        if not lote:
            break
        registros.extend(lote)
        cursor = data.get("next_cursor", cursor)
        if not data.get("has_more"):
            break
    return registros


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="exportacion_offline")
    fuente = p.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--entrada", help="JSON local con registros")
    fuente.add_argument("--api", help="Base de la API de redayuda")
    p.add_argument("--salida", default="listas.html")
    p.add_argument("--agrupar", default="organization",
                   choices=["organization", "city", "state"], help="Campo de agrupación")
    p.add_argument("--titulo", default="Personas localizadas")
    args = p.parse_args(argv)

    registros = _cargar_archivo(args.entrada) if args.entrada else _cargar_api(args.api)
    html = exportar.html_listado(registros, titulo=args.titulo, agrupar_campo=args.agrupar)
    carpeta = os.path.dirname(os.path.abspath(args.salida))
    os.makedirs(carpeta, exist_ok=True)
    with open(args.salida, "w", encoding="utf-8") as fh:
        fh.write(html)
    locs = exportar.solo_localizadas(registros)
    print("OK: %d registros, %d localizadas -> %s" % (len(registros), len(locs), args.salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
