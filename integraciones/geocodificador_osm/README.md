# Geocodificador OpenStreetMap (Nominatim)

Aporte **aditivo** a redayuda. Convierte la ubicación textual de los registros (hospital, ciudad)
en **coordenadas** usando [Nominatim](https://nominatim.org), el geocodificador gratuito y oficial
de OpenStreetMap, para que aparezcan en el **mapa Leaflet/OSM que redayuda ya tiene**.

## Por qué

El mapa de redayuda solo muestra registros **con coordenadas**, y solo ~9 de los 22 conectores las
aportan. El resto trae "Hospital Vargas, La Guaira" como texto y **no se ve en el mapa**. Este
componente rellena ese hueco sin tocar el núcleo.

## Política de uso de Nominatim (respetada)

- **Máx. 1 petición/segundo** → el módulo pausa entre llamadas reales.
- **User-Agent identificable** → incluido.
- **Cachear resultados** → caché local en disco (incluye los "no encontrado").

Para volumen alto, lo correcto es un Nominatim **auto-hospedado**. Atribución: © OpenStreetMap.

## Uso

```bash
python -m integraciones.geocodificador_osm.cli \
    --entrada registros.json --salida registros_geo.json --cache geocache.json
```

Como librería:

```python
from integraciones.geocodificador_osm import enriquecer, geocodificador
cache = geocodificador.cargar_cache("geocache.json")
enriquecidos, n = enriquecer.enriquecer(registros, cache=cache)
geocodificador.guardar_cache("geocache.json", cache)
```

## Tests

```bash
python -m pytest integraciones/geocodificador_osm/tests -q
```

Corren sin red (el `fetch` HTTP es inyectable).
