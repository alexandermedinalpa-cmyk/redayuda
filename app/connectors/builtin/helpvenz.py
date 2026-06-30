"""Conector: HelpVenz (https://helpvenz.vercel.app).

Supabase PostgREST con clave anon publica (RLS protege la escritura; lectura abierta).
Tablas:
  GET /rest/v1/person_reports -> personas desaparecidas (con lat/lng, es_menor, foto, contacto)
  GET /rest/v1/needs          -> necesidades de insumos (categoria, urgencia, cantidad)
  GET /rest/v1/offers         -> ofertas de insumos
  GET /rest/v1/housing        -> alojamientos / refugios
Paginacion PostgREST: ?limit=&offset= (max 1000). Headers: apikey + Authorization.
La mayoria de registros traen lat/lng, por lo que aparecen en el mapa.
"""

import os

from ...client import HttpClient
from ...models import IndexedRecord, SourceInfo
from ..base import Connector, stamp_and_upsert

HV_SOURCE_ID = "helpvenz"
HV_REST = "https://ggsepuuxuupysldleqpo.supabase.co/rest/v1"
HV_BASE = "https://helpvenz.vercel.app"
# Clave anon (publica por diseno en el cliente). Override por entorno si se desea.
HV_KEY = os.getenv(
    "HELPVENZ_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imdnc2VwdXV4dXVweXNsZGxlcXBvIiwicm9sZSI6"
    "ImFub24iLCJpYXQiOjE3ODIzNTYxNjUsImV4cCI6MjA5NzkzMjE2NX0."
    "ulfNUhiJ5ER1LF7mjHtGDSL8NH6J7Q9_J2D5Lr53lPU",
)
HV_PAGE = 1000


def _headers():
    return {"apikey": HV_KEY, "Authorization": "Bearer " + HV_KEY}


def _person_type(tipo, estado):
    s = ("%s %s" % (tipo or "", estado or "")).lower()
    if any(k in s for k in ("encontr", "localiz", "reunid", "salvo", "con vida")):
        return "persona_localizada"
    if "hospital" in s:
        return "persona_hospitalizada"
    return "persona_desaparecida"


def _contacto(r):
    return r.get("contacto_whatsapp") or r.get("contacto_nombre") or r.get("contacto_email") or None


def _coord(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class HelpVenzConnector(Connector):
    source = SourceInfo(
        id=HV_SOURCE_ID,
        name="HelpVenz",
        kind="persona_desaparecida",
        description="Personas desaparecidas, necesidades, ofertas y alojamientos (con coordenadas).",
        url=HV_BASE,
        access="api_key",
        enabled=True,
    )

    async def sync(self, *, store, settings, source_limit=1000, max_pages=5, desde=None):
        store.upsert_source(self.source)
        client = HttpClient(settings)
        imported = scanned = pages = 0

        for table, mapper in (
            ("person_reports", _map_person),
            ("needs", _map_need),
            ("offers", _map_offer),
            ("housing", _map_housing),
        ):
            offset = 0
            while pages < 2000:
                rows = await client.get_json(
                    "%s/%s?limit=%d&offset=%d&order=created_at.desc" % (HV_REST, table, HV_PAGE, offset),
                    headers=_headers(),
                )
                rows = rows if isinstance(rows, list) else []
                pages += 1
                scanned += len(rows)
                imported += stamp_and_upsert(
                    store, settings, HV_SOURCE_ID, [mapper(r) for r in rows]
                )
                if len(rows) < HV_PAGE:
                    break
                offset += HV_PAGE

        store.touch_source_sync(HV_SOURCE_ID)
        return imported, scanned, pages


def _map_person(r):
    rid = str(r.get("id") or "")
    nombre = r.get("nombre") or "Persona"
    tags = ["persona"]
    if r.get("es_menor"):
        tags.append("menor")
    return IndexedRecord(
        id="%s:p:%s" % (HV_SOURCE_ID, rid),
        record_type=_person_type(r.get("tipo"), r.get("estado")),
        title=nombre,
        summary=r.get("descripcion"),
        person_name=nombre,
        age=r.get("edad"),
        location_name=r.get("referencia") or r.get("parroquia"),
        city=r.get("municipio") or None,
        state=r.get("estado_geo") or None,
        country="VE",
        latitude=_coord(r.get("lat")),
        longitude=_coord(r.get("lng")),
        contact=_contacto(r),
        status=r.get("estado"),
        source_id=HV_SOURCE_ID,
        source_name="HelpVenz",
        source_url=HV_BASE,
        source_record_id="p:" + rid,
        observed_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
        image_url=r.get("foto_url"),
        tags=tags,
        raw=r,
    )


def _map_recurso(r, prefijo, etiqueta_extra):
    rid = str(r.get("id") or "")
    titulo = r.get("titulo") or r.get("descripcion") or "Recurso"
    cat = (r.get("categoria") or r.get("tipo") or "").lower()
    return IndexedRecord(
        id="%s:%s:%s" % (HV_SOURCE_ID, prefijo, rid),
        record_type="recurso",
        title=str(titulo),
        summary=r.get("descripcion"),
        location_name=r.get("referencia") or r.get("parroquia"),
        city=r.get("municipio") or None,
        state=r.get("estado_geo") or None,
        country="VE",
        latitude=_coord(r.get("lat")),
        longitude=_coord(r.get("lng")),
        contact=_contacto(r),
        status=r.get("urgencia") or r.get("estado"),
        source_id=HV_SOURCE_ID,
        source_name="HelpVenz",
        source_url=HV_BASE,
        source_record_id="%s:%s" % (prefijo, rid),
        observed_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
        tags=[etiqueta_extra] + ([cat] if cat else []),
        raw=r,
    )


def _map_need(r):
    return _map_recurso(r, "n", "necesidad")


def _map_offer(r):
    return _map_recurso(r, "o", "oferta")


def _map_housing(r):
    return _map_recurso(r, "h", "alojamiento")


CONNECTOR = HelpVenzConnector()
