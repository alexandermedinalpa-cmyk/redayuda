"""CLI: enriquece registros con coordenadas (OSM/Nominatim) para que salgan en el mapa.

  python -m integraciones.geocodificador_osm.cli --entrada registros.json \\
      --salida registros_geo.json --cache geocache.json
"""

from __future__ import annotations

import argparse
import json

from . import enriquecer, geocodificador


def _cargar(ruta: str) -> list[dict]:
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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="geocodificador_osm")
    p.add_argument("--entrada", required=True, help="JSON con registros")
    p.add_argument("--salida", required=True, help="JSON de salida (registros enriquecidos)")
    p.add_argument("--cache", default="geocache.json", help="Caché de geocodificación")
    args = p.parse_args(argv)

    registros = _cargar(args.entrada)
    cache = geocodificador.cargar_cache(args.cache)
    enriquecidos, n = enriquecer.enriquecer(registros, cache=cache)
    geocodificador.guardar_cache(args.cache, cache)
    with open(args.salida, "w", encoding="utf-8") as fh:
        json.dump(enriquecidos, fh, ensure_ascii=False, indent=2)
    con_coords = sum(1 for r in enriquecidos
                     if r.get("latitude") is not None and r.get("longitude") is not None)
    print("OK: %d registros, %d geocodificados nuevos, %d con coordenadas en total -> %s"
          % (len(registros), n, con_coords, args.salida))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
