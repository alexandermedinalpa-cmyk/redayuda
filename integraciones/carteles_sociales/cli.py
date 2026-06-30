"""CLI: genera carteles SVG 'SE BUSCA' para personas desaparecidas.

  python -m integraciones.carteles_sociales.cli --entrada registros.json --salida carteles/
  python -m integraciones.carteles_sociales.cli --api https://nodo-redayuda --salida carteles/
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.request

from . import cartel


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


def _cargar_api(base: str, limite: int = 2000) -> list[dict]:
    url = "%s/api/records/search?q=&record_type=persona_desaparecida&limit=100" % base.rstrip("/")
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [r.get("record", r) for r in data.get("results", [])][:limite]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="carteles_sociales")
    fuente = p.add_mutually_exclusive_group(required=True)
    fuente.add_argument("--entrada", help="JSON local con registros")
    fuente.add_argument("--api", help="Base de la API de redayuda")
    p.add_argument("--salida", default="carteles")
    p.add_argument("--incluir-menores", action="store_true",
                   help="Generar también carteles de menores (ver nota ética en README)")
    args = p.parse_args(argv)

    registros = _cargar_archivo(args.entrada) if args.entrada else _cargar_api(args.api)
    desaparecidos = [r for r in registros if r.get("record_type") == "persona_desaparecida"]
    os.makedirs(args.salida, exist_ok=True)

    generados = omitidos_menor = 0
    for i, r in enumerate(desaparecidos):
        edad = r.get("age")
        es_menor = isinstance(edad, int) and edad < 18
        if es_menor and not args.incluir_menores:
            omitidos_menor += 1
            continue
        svg = cartel.cartel_svg(r)
        ruta = os.path.join(args.salida, cartel.nombre_archivo(r, i))
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(svg)
        generados += 1

    print("OK: %d carteles en %s/" % (generados, args.salida))
    if omitidos_menor:
        print("   %d menores omitidos (usa --incluir-menores solo con coordinación familiar/autoridad)"
              % omitidos_menor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
