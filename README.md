# Red Humanitaria de Datos

API en FastAPI con frontend web para indexar informacion humanitaria de multiples fuentes abiertas. El objetivo es que apps de personas desaparecidas, centros de acopio, donaciones y otras fuentes puedan consultar una red comun y tambien aportar datos normalizados.

> ### 🔗 Demo en vivo: **https://red-rescate-venezuela.fly.dev**
> Web pública con 120k+ registros · Bot de Telegram **@red_ayuda_bot** (búsqueda, alertas, `/urgente`) · Mapa.
> Para colaboradores: úsalo para probar tu aporte en funcionamiento. *(Plan gratuito: el primer acceso tras inactividad puede tardar unos segundos en despertar.)*

## Requisitos

- Python 3.10+ (FastAPI 0.138.1 lo exige).
- Clave de la API externa de hospitales en `HOSPITALES_API_KEY` si se va a sincronizar esa fuente.
- `INGEST_API_KEY` para proteger escrituras de apps aliadas.
- `ADMIN_API_KEY` para proteger sincronizaciones, peers y revision de propuestas.

FastAPI queda fijado a `0.138.1`, la version mas reciente verificada para este proyecto.

> Seguridad: por defecto las escrituras estan cerradas (fail-closed). Si una clave
> no esta configurada, el endpoint responde `503` en lugar de quedar abierto. Para
> desarrollo local sin claves, usa `ALLOW_OPEN_WRITES=1`.

## Instalacion

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
```

Edita `.env` y agrega tu clave:

```bash
HOSPITALES_API_KEY=tu_clave_real
INGEST_API_KEY=clave_para_apps_aliadas
ADMIN_API_KEY=clave_para_sincronizar_fuentes
```

## Ejecutar

```bash
fastapi dev app/main.py
```

La documentacion interactiva queda en:

```text
http://127.0.0.1:8000/docs
```

El frontend queda en:

```text
http://127.0.0.1:8000/
```

## Endpoints

Red federada:

- `GET /`: frontend web de busqueda.
- `GET /contribuir`: formulario self-service para que colaboradores registren su API.
- `GET /api`: informacion basica de la API.
- `GET /api/sources`: fuentes registradas en la red.
- `GET /api/network/stats`: resumen del indice.
- `GET /api/records/search`: busqueda unificada (FTS5 + BM25). Soporta `group_by_entity`.
- `GET /api/records/feed`: feed incremental por cursor (`?since=`) para que otros nodos se nutran.
- `GET /api/records/{id}`: detalle de un registro normalizado.
- `POST /api/ingest`: ingestion desde apps aliadas (requiere `x-ingest-key`).
- `POST /api/sources/{id}/sync`: sincroniza un conector al indice (requiere `x-admin-key`).
- `GET /api/entities/{id}`: vista de "misma persona entre fuentes".
- `POST /api/entities/link` y `/api/entities/unlink`: ajuste manual de enlaces (admin).

Federacion entre nodos (admin):

- `GET|POST|DELETE /api/peers`, `POST /api/peers/{id}/pull`: registro y sondeo de peers.

Registro self-service de conectores:

- `GET /api/connectors/schema`: contrato publico (esquema y ejemplo).
- `POST /api/connectors/proposals`: envia una propuesta de fuente (publica, rate-limited).
- `GET /api/connectors/proposals[/{id}]`, `POST /api/connectors/proposals/{id}/review`: revision (admin).

Legacy / fuente directa:

- `GET /buscar` y `GET /search`: busqueda legacy directa sobre Hospitales en Venezuela.
- `GET /pacientes`: proxy paginado directo a la API externa.
- `GET /frescura`: consulta minima con `limit=1` para leer `total` y `generado`.
- `GET /health`: salud local y estado de configuracion.

## Agregar un conector

Una fuente nueva = 1 archivo en `app/connectors/builtin/` que expone `CONNECTOR`.
Tambien se puede proponer desde `/contribuir` sin tocar el codigo (queda pendiente
de revision admin).

## Ejemplos

Buscar en el indice:

```bash
curl "http://127.0.0.1:8000/api/records/search?q=Jose%20Perez&limit=10"
```

Buscar por cedula en cualquier fuente:

```bash
curl "http://127.0.0.1:8000/api/records/search?cedula=12345678"
```

Filtrar por tipo y ciudad:

```bash
curl "http://127.0.0.1:8000/api/records/search?record_type=centro_acopio&city=Caracas"
```

Sincronizar Hospitales en Venezuela al indice:

```bash
curl -X POST "http://127.0.0.1:8000/api/sources/hospitales_venezuela/sync?source_limit=5000&max_pages=6" \
  -H "x-admin-key: tu_admin_key"
```

Ingestar registros desde una app aliada:

```bash
curl -X POST "http://127.0.0.1:8000/api/ingest" \
  -H "content-type: application/json" \
  -H "x-ingest-key: tu_ingest_key" \
  -d '{
    "source": {
      "id": "app_desaparecidos_demo",
      "name": "App Desaparecidos Demo",
      "kind": "desaparecidos",
      "description": "Fuente aliada de prueba"
    },
    "records": [
      {
        "id": "app_desaparecidos_demo:1",
        "record_type": "persona_desaparecida",
        "title": "Maria Perez",
        "person_name": "Maria Perez",
        "city": "Caracas",
        "source_id": "app_desaparecidos_demo",
        "source_name": "App Desaparecidos Demo",
        "tags": ["persona", "desaparecida"]
      }
    ]
  }'
```

## Pruebas

```bash
pytest
```

## Contribuir

Este proyecto es **open source** y la idea es que la comunidad lo continúe: una sola
red para que las apps de ayuda dejen de duplicar el mismo índice.

Formas de aportar:

- **Conectar una fuente sin tocar código:** expón un endpoint JSON de lectura y
  regístralo desde `/contribuir` (queda pendiente de revisión).
- **Agregar un conector:** una fuente nueva = un archivo en `app/connectors/builtin/`
  que expone `CONNECTOR` (ver los ejemplos existentes).
- **Mejorar el frontend/UX, la resolución de entidades o la federación:** abre un
  issue o un pull request.

Antes de un PR: `pytest` debe pasar. Las escrituras son *fail-closed* por defecto
(ver Seguridad arriba); no subas claves ni datos personales (el `.gitignore` ya
excluye `.env*` y las bases `*.db`).

## Privacidad

El índice contiene datos sensibles (personas desaparecidas, cédulas). La base de
datos **no se versiona**: vive solo en cada nodo. Trata cualquier despliegue con el
cuidado que merece esta información.

## Licencia

[MIT](LICENSE) © Erik Taveras y colaboradores.
