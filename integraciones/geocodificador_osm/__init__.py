"""Geocodificador con OpenStreetMap (Nominatim) para enriquecer registros.

Aporte ADITIVO: muchos registros traen la ubicación como texto (hospital, ciudad)
pero sin coordenadas, así que NO aparecen en el mapa Leaflet/OSM que ya tiene
redayuda. Este componente convierte ese texto en lat/lng usando Nominatim (el
geocodificador gratuito y oficial de OpenStreetMap), con caché local para
respetar su política de uso (máx. 1 petición/seg, User-Agent, cachear).

No modifica el núcleo: produce registros enriquecidos que pueden re-ingerirse.
Sin dependencias externas (solo stdlib).
"""

__version__ = "0.1.0"
