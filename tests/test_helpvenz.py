import pytest

from app import connectors
from app.client import HttpClient
from app.connectors.builtin import helpvenz
from app.connectors.builtin.helpvenz import HV_SOURCE_ID


def test_registry_discovers_helpvenz():
    connectors.load_builtin_connectors(force=True)
    connector = connectors.get(HV_SOURCE_ID)
    assert connector is not None
    assert connector.source.id == HV_SOURCE_ID


def test_source_infos_includes_helpvenz():
    connectors.load_builtin_connectors(force=True)
    ids = {s.id for s in connectors.source_infos()}
    assert HV_SOURCE_ID in ids


def test_map_person_mapea_coordenadas_y_marca_menor():
    row = {
        "id": "42", "tipo": "desaparecida", "nombre": "Ana Pérez", "edad": 8,
        "municipio": "La Guaira", "estado_geo": "La Guaira", "lat": "10.6", "lng": "-66.9",
        "estado": "activo", "es_menor": True, "contacto_whatsapp": "+58 412 000",
        "foto_url": "http://x/a.jpg", "referencia": "Av. Soublette", "created_at": "2026-06-28",
    }
    rec = helpvenz._map_person(row)
    assert rec.record_type == "persona_desaparecida"
    assert rec.person_name == "Ana Pérez"
    assert rec.latitude == 10.6 and rec.longitude == -66.9
    assert rec.city == "La Guaira"
    assert rec.contact == "+58 412 000"
    assert "menor" in rec.tags  # protección de menores aguas abajo
    assert rec.image_url == "http://x/a.jpg"


def test_map_need_es_recurso():
    rec = helpvenz._map_need({"id": "5", "categoria": "salud", "titulo": "Suero fisiológico",
                              "urgencia": "alta", "municipio": "La Guaira"})
    assert rec.record_type == "recurso"
    assert rec.title == "Suero fisiológico"
    assert "necesidad" in rec.tags and "salud" in rec.tags
    assert rec.status == "alta"


_FAKE = {
    "person_reports": [
        {"id": "1", "tipo": "desaparecida", "nombre": "Ana Pérez", "edad": 30,
         "municipio": "Caracas", "lat": 10.5, "lng": -66.9, "estado": "activo"},
        {"id": "2", "tipo": "desaparecida", "nombre": "Niño López", "edad": 8,
         "municipio": "La Guaira", "es_menor": True},
    ],
    "needs": [{"id": "5", "categoria": "salud", "titulo": "Suero", "urgencia": "alta",
               "municipio": "La Guaira"}],
    "offers": [{"id": "7", "categoria": "comida", "titulo": "Agua", "municipio": "Caracas"}],
    "housing": [{"id": "9", "tipo": "refugio", "titulo": "Refugio Escuela", "municipio": "Caracas"}],
}


@pytest.mark.anyio
async def test_sync_persiste_todas_las_tablas(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.store import IndexStore

    async def fake_get_json(self, url, headers=None):
        for tabla, filas in _FAKE.items():
            if "/%s?" % tabla in url:
                return filas
        return []

    monkeypatch.setattr(HttpClient, "get_json", fake_get_json)
    connectors.load_builtin_connectors(force=True)
    connector = connectors.get(HV_SOURCE_ID)

    store = IndexStore(tmp_path / "index.db")
    imported, scanned, pages = await connector.sync(
        store=store, settings=get_settings(), source_limit=1000, max_pages=5,
    )
    assert imported == 5  # 2 personas + 1 need + 1 offer + 1 housing
    assert scanned == 5
    # "perez" identifica solo a Ana Pérez (término único en el set).
    assert store.search_records(query="perez").total_matches == 1
    # El menor quedó marcado para protección aguas abajo.
    nino = store.search_records(query="lopez")
    assert nino.total_matches == 1
    assert "menor" in nino.results[0].record.tags


@pytest.fixture
def anyio_backend():
    return "asyncio"
