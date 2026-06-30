"""Tests del geocodificador OSM y el enriquecedor (sin red, fetch inyectado)."""

from integraciones.geocodificador_osm import enriquecer, geocodificador


def fetch_ok(url):
    # Simula la respuesta de Nominatim.
    return [{"lat": "10.6116", "lon": "-66.9303", "display_name": "Caracas"}]


def fetch_vacio(url):
    return []


def test_geocodificar_parsea_resultado():
    coords = geocodificador.geocodificar("Caracas, Venezuela", fetch=fetch_ok)
    assert coords == (10.6116, -66.9303)


def test_geocodificar_usa_cache_y_no_vuelve_a_pedir():
    cache = {}
    geocodificador.geocodificar("Hospital Vargas, La Guaira, Venezuela", fetch=fetch_ok, cache=cache)
    # Segunda vez: fetch que explota; debe responder desde caché.
    def fetch_explota(url):
        raise AssertionError("no debería volver a pedir; está en caché")
    coords = geocodificador.geocodificar(
        "hospital vargas,   la guaira, venezuela", fetch=fetch_explota, cache=cache
    )
    assert coords == (10.6116, -66.9303)


def test_geocodificar_cachea_los_no_encontrados():
    cache = {}
    assert geocodificador.geocodificar("Lugar inexistente", fetch=fetch_vacio, cache=cache) is None
    clave = "lugar inexistente"
    assert clave in cache and cache[clave] is None


def test_geocodificar_consulta_vacia():
    assert geocodificador.geocodificar("   ", fetch=fetch_ok) is None


def test_construir_consulta_acota_a_venezuela_y_dedup():
    rec = {"organization": "Hospital Vargas", "city": "La Guaira", "location_name": "La Guaira"}
    q = enriquecer.construir_consulta(rec)
    assert q.endswith(", Venezuela")
    assert q.count("La Guaira") == 1  # no repite city y location_name iguales


def test_enriquecer_rellena_solo_los_que_faltan():
    records = [
        {"id": "a", "organization": "Hospital Vargas", "city": "La Guaira"},   # sin coords
        {"id": "b", "city": "Caracas", "latitude": 1.0, "longitude": 2.0},     # ya tiene coords
        {"id": "c"},  # sin texto ubicable -> no se geocodifica
    ]
    salida, n = enriquecer.enriquecer(records, fetch=fetch_ok, cache={})
    assert n == 1
    assert salida[0]["latitude"] == 10.6116 and salida[0].get("geocodificado") is True
    assert salida[1]["latitude"] == 1.0 and "geocodificado" not in salida[1]  # intacto
    assert "latitude" not in salida[2]


def test_enriquecer_no_muta_original():
    records = [{"id": "a", "city": "Caracas"}]
    enriquecer.enriquecer(records, fetch=fetch_ok, cache={})
    assert "latitude" not in records[0]
