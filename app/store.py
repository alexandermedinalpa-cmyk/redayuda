import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from . import entities
from .models import IndexedRecord, IndexedSearchResponse, IndexedSearchResult, SourceInfo
from .search import digits_only, normalize_text, tokenize


SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    url TEXT,
    access TEXT NOT NULL DEFAULT 'open',
    enabled INTEGER NOT NULL DEFAULT 1,
    record_count INTEGER NOT NULL DEFAULT 0,
    last_sync TEXT
);

CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    record_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    person_name TEXT,
    cedula TEXT,
    age INTEGER,
    organization TEXT,
    location_name TEXT,
    city TEXT,
    state TEXT,
    country TEXT NOT NULL DEFAULT 'VE',
    latitude REAL,
    longitude REAL,
    contact TEXT,
    status TEXT,
    verified INTEGER,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    source_record_id TEXT,
    observed_at TEXT,
    updated_at TEXT,
    tags_json TEXT NOT NULL DEFAULT '[]',
    raw_json TEXT NOT NULL DEFAULT '{}',
    search_text TEXT NOT NULL,
    indexed_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id)
);

CREATE INDEX IF NOT EXISTS idx_records_type ON records(record_type);
CREATE INDEX IF NOT EXISTS idx_records_source ON records(source_id);
CREATE INDEX IF NOT EXISTS idx_records_city ON records(city);
CREATE INDEX IF NOT EXISTS idx_records_cedula ON records(cedula);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS peers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    pull_enabled INTEGER NOT NULL DEFAULT 1,
    last_cursor INTEGER NOT NULL DEFAULT 0,
    last_pull_at TEXT,
    last_status TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    canonical_title TEXT,
    canonical_cedula TEXT,
    record_count INTEGER NOT NULL DEFAULT 0,
    strongest_signal TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS match_keys (
    record_id TEXT NOT NULL,
    key TEXT NOT NULL,
    kind TEXT NOT NULL,
    PRIMARY KEY (record_id, key)
);

CREATE INDEX IF NOT EXISTS idx_match_keys_key ON match_keys(key);

CREATE TABLE IF NOT EXISTS entity_overrides (
    record_a TEXT NOT NULL,
    record_b TEXT NOT NULL,
    decision TEXT NOT NULL,
    created_by TEXT,
    created_at TEXT,
    PRIMARY KEY (record_a, record_b)
);

CREATE TABLE IF NOT EXISTS connector_proposals (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending',
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    endpoint_url TEXT NOT NULL,
    http_method TEXT NOT NULL DEFAULT 'GET',
    auth_type TEXT NOT NULL DEFAULT 'none',
    auth_header TEXT,
    pagination_json TEXT NOT NULL DEFAULT '{}',
    data_path TEXT,
    field_mapping_json TEXT NOT NULL DEFAULT '{}',
    connector_spec_json TEXT NOT NULL DEFAULT '{}',
    sample_response TEXT,
    docs TEXT,
    contact_name TEXT,
    contact_email TEXT,
    submitter_ip TEXT,
    review_notes TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_proposals_status ON connector_proposals(status);

CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    title, person_name, organization, location_name,
    city, state, summary, tags,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS records_ai AFTER INSERT ON records BEGIN
    INSERT INTO records_fts(
        rowid, title, person_name, organization, location_name,
        city, state, summary, tags
    ) VALUES (
        new.rowid, new.title, new.person_name, new.organization,
        new.location_name, new.city, new.state, new.summary, new.tags_json
    );
END;

CREATE TRIGGER IF NOT EXISTS records_ad AFTER DELETE ON records BEGIN
    DELETE FROM records_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS records_au AFTER UPDATE ON records BEGIN
    DELETE FROM records_fts WHERE rowid = old.rowid;
    INSERT INTO records_fts(
        rowid, title, person_name, organization, location_name,
        city, state, summary, tags
    ) VALUES (
        new.rowid, new.title, new.person_name, new.organization,
        new.location_name, new.city, new.state, new.summary, new.tags_json
    );
END;
"""


# Columnas anadidas despues de la version inicial; se aplican a DBs existentes
# via _migrate() porque CREATE TABLE IF NOT EXISTS no altera tablas ya creadas.
_RECORD_MIGRATIONS = [
    ("origin_node", "ALTER TABLE records ADD COLUMN origin_node TEXT"),
    ("origin_source", "ALTER TABLE records ADD COLUMN origin_source TEXT"),
    ("feed_seq", "ALTER TABLE records ADD COLUMN feed_seq INTEGER"),
    ("entity_id", "ALTER TABLE records ADD COLUMN entity_id TEXT"),
    ("content_hash", "ALTER TABLE records ADD COLUMN content_hash TEXT"),
    ("image_url", "ALTER TABLE records ADD COLUMN image_url TEXT"),
]

_FEED_SEQ_KEY = "feed_seq"

# Tope de candidatos recuperados antes del re-ranking en Python. Acota el costo
# del re-rank manteniendo cobertura amplia para el tamano de este indice.
_CANDIDATE_LIMIT = 5000


class IndexStore:
    def __init__(self, database_path, busy_timeout_ms=5000):
        self.database_path = Path(database_path)
        self.busy_timeout_ms = busy_timeout_ms
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self):
        connection = sqlite3.connect(
            str(self.database_path),
            timeout=self.busy_timeout_ms / 1000,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = %d" % self.busy_timeout_ms)
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        except sqlite3.OperationalError:
            # Algunos sistemas de archivos (p.ej. volúmenes externos/red) no
            # soportan el locking de WAL; degradamos al journal por defecto.
            pass
        return connection

    def init_db(self):
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    def _migrate(self, connection):
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(records)").fetchall()
        }
        added = []
        for column, ddl in _RECORD_MIGRATIONS:
            if column not in existing:
                connection.execute(ddl)
                added.append(column)

        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_records_feed_seq "
            "ON records(feed_seq)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_origin_node "
            "ON records(origin_node)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_records_entity ON records(entity_id)"
        )

        # Backfill de feed_seq para filas previas a la federacion.
        if "feed_seq" in added or self._feed_needs_backfill(connection):
            self._backfill_feed_seq(connection)

        # Backfill del indice FTS si quedo vacio con registros presentes.
        fts_count = connection.execute(
            "SELECT COUNT(*) FROM records_fts"
        ).fetchone()[0]
        rec_count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
        if rec_count and not fts_count:
            connection.execute(
                """
                INSERT INTO records_fts(
                    rowid, title, person_name, organization, location_name,
                    city, state, summary, tags
                )
                SELECT rowid, title, person_name, organization, location_name,
                       city, state, summary, tags_json
                FROM records
                """
            )

    def _feed_needs_backfill(self, connection):
        return (
            connection.execute(
                "SELECT COUNT(*) FROM records WHERE feed_seq IS NULL"
            ).fetchone()[0]
            > 0
        )

    def _backfill_feed_seq(self, connection):
        start = self._read_feed_seq(connection)
        rows = connection.execute(
            "SELECT rowid FROM records WHERE feed_seq IS NULL ORDER BY rowid ASC"
        ).fetchall()
        for offset, row in enumerate(rows, start=1):
            connection.execute(
                "UPDATE records SET feed_seq = ? WHERE rowid = ?",
                (start + offset, row["rowid"]),
            )
        if rows:
            self._write_feed_seq(connection, start + len(rows))

    def _read_feed_seq(self, connection):
        row = connection.execute(
            "SELECT value FROM meta WHERE key = ?", (_FEED_SEQ_KEY,)
        ).fetchone()
        return int(row["value"]) if row else 0

    def _write_feed_seq(self, connection, value):
        connection.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_FEED_SEQ_KEY, str(value)),
        )

    def upsert_source(self, source):
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sources (
                    id, name, kind, description, url, access, enabled,
                    record_count, last_sync
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    kind = excluded.kind,
                    description = excluded.description,
                    url = excluded.url,
                    access = excluded.access,
                    enabled = excluded.enabled,
                    record_count = excluded.record_count,
                    last_sync = COALESCE(excluded.last_sync, sources.last_sync)
                """,
                (
                    source.id,
                    source.name,
                    source.kind,
                    source.description,
                    source.url,
                    source.access,
                    int(source.enabled),
                    source.record_count,
                    _datetime_to_text(source.last_sync),
                ),
            )

    def touch_source_sync(self, source_id):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM records WHERE source_id = ?",
                (source_id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE sources SET record_count = ?, last_sync = ? WHERE id = ?",
                (count, now, source_id),
            )

    def ensure_source(self, source_id, source_name=None, kind="federado"):
        """Crea una fuente minima si no existe (sin sobreescribir la existente).

        Necesario para satisfacer la FK de records al ingerir datos federados
        cuyas fuentes aun no estan registradas localmente.
        """
        with self.connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO sources (
                    id, name, kind, description, access, enabled, record_count
                ) VALUES (?, ?, ?, ?, ?, 1, 0)
                """,
                (
                    source_id,
                    source_name or source_id,
                    kind,
                    "Fuente federada recibida de un peer.",
                    "open",
                ),
            )

    def list_sources(self):
        # record_count se calcula en vivo desde records para que el directorio
        # coincida siempre con la busqueda; la columna sources.record_count puede
        # quedar rezagada (p.ej. ingestas federadas sin touch_source_sync).
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT s.*, COALESCE(r.cnt, 0) AS live_count
                FROM sources s
                LEFT JOIN (
                    SELECT source_id, COUNT(*) AS cnt FROM records GROUP BY source_id
                ) r ON r.source_id = s.id
                ORDER BY s.enabled DESC, s.name ASC
                """
            ).fetchall()
        return [_source_from_row(row) for row in rows]

    # ----- Peers (federacion) -------------------------------------------------

    def add_peer(self, peer):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO peers (
                    id, name, base_url, api_key, enabled, pull_enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    base_url = excluded.base_url,
                    api_key = COALESCE(excluded.api_key, peers.api_key),
                    enabled = excluded.enabled,
                    pull_enabled = excluded.pull_enabled
                """,
                (
                    peer.id,
                    peer.name,
                    peer.base_url,
                    peer.api_key,
                    int(peer.enabled),
                    int(peer.pull_enabled),
                    now,
                ),
            )
        return self.get_peer(peer.id)

    def list_peers(self):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM peers ORDER BY name ASC"
            ).fetchall()
        return [_peer_from_row(row) for row in rows]

    def get_peer(self, peer_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM peers WHERE id = ?", (peer_id,)
            ).fetchone()
        return _peer_from_row(row) if row else None

    def delete_peer(self, peer_id):
        with self.connect() as connection:
            cur = connection.execute(
                "DELETE FROM peers WHERE id = ?", (peer_id,)
            )
        return cur.rowcount > 0

    def peer_pull_targets(self):
        """Filas crudas (incluyen api_key y cursor) para el loop de pull."""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM peers WHERE enabled = 1 AND pull_enabled = 1"
            ).fetchall()
        return [dict(row) for row in rows]

    def update_peer_cursor(self, peer_id, cursor, status):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                "UPDATE peers SET last_cursor = ?, last_pull_at = ?, "
                "last_status = ? WHERE id = ?",
                (cursor, now, status, peer_id),
            )

    def upsert_records(self, records):
        indexed_at = datetime.now(timezone.utc).isoformat()
        changed = 0
        with self.connect() as connection:
            next_seq = self._read_feed_seq(connection)
            for record in records:
                content_hash = _content_hash(record)
                existing = connection.execute(
                    "SELECT content_hash FROM records WHERE id = ?", (record.id,)
                ).fetchone()
                if existing is not None and existing[0] == content_hash:
                    # Sin cambios reales: no re-escribir, no re-resolver entidad,
                    # no consumir feed_seq. Hace los re-sync casi gratis.
                    continue
                changed += 1
                next_seq += 1
                connection.execute(
                    """
                    INSERT INTO records (
                        id, record_type, title, summary, person_name, cedula, age,
                        organization, location_name, city, state, country, latitude,
                        longitude, contact, status, verified, source_id, source_name,
                        source_url, source_record_id, observed_at, updated_at,
                        tags_json, raw_json, search_text, indexed_at,
                        origin_node, origin_source, feed_seq, image_url, content_hash
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(id) DO UPDATE SET
                        record_type = excluded.record_type,
                        title = excluded.title,
                        summary = excluded.summary,
                        person_name = excluded.person_name,
                        cedula = excluded.cedula,
                        age = excluded.age,
                        organization = excluded.organization,
                        location_name = excluded.location_name,
                        city = excluded.city,
                        state = excluded.state,
                        country = excluded.country,
                        latitude = excluded.latitude,
                        longitude = excluded.longitude,
                        contact = excluded.contact,
                        status = excluded.status,
                        verified = excluded.verified,
                        source_id = excluded.source_id,
                        source_name = excluded.source_name,
                        source_url = excluded.source_url,
                        source_record_id = excluded.source_record_id,
                        observed_at = excluded.observed_at,
                        updated_at = excluded.updated_at,
                        tags_json = excluded.tags_json,
                        raw_json = excluded.raw_json,
                        search_text = excluded.search_text,
                        indexed_at = excluded.indexed_at,
                        origin_node = COALESCE(records.origin_node, excluded.origin_node),
                        origin_source = COALESCE(records.origin_source, excluded.origin_source),
                        feed_seq = excluded.feed_seq,
                        image_url = excluded.image_url,
                        content_hash = excluded.content_hash
                    """,
                    _record_values(record, indexed_at, next_seq, content_hash),
                )
                self._resolve_entity(connection, record)
            self._write_feed_seq(connection, next_seq)
        return changed

    def feed_records(self, since_seq=0, limit=100, exclude_origin=None):
        with self.connect() as connection:
            sql = "SELECT * FROM records WHERE feed_seq > ?"
            values = [since_seq]
            if exclude_origin:
                sql += " AND (origin_node IS NULL OR origin_node != ?)"
                values.append(exclude_origin)
            sql += " ORDER BY feed_seq ASC LIMIT ?"
            values.append(limit)
            rows = connection.execute(sql, values).fetchall()

        records = [_record_from_row(row) for row in rows]
        next_cursor = rows[-1]["feed_seq"] if rows else since_seq
        has_more = len(rows) == limit
        return records, next_cursor, has_more

    # ----- Resolucion de entidades -------------------------------------------

    def _resolve_entity(self, connection, record):
        """Enlaza el registro recien escrito con su entidad probable.

        Corre en la misma transaccion que el upsert. Conserva la procedencia:
        solo asigna records.entity_id; nunca modifica los datos del registro.
        """
        this = _match_dict_from_record(record)
        keys = entities.match_keys(this)

        # Refrescar match_keys del registro.
        connection.execute(
            "DELETE FROM match_keys WHERE record_id = ?", (record.id,)
        )
        for key, kind in keys:
            connection.execute(
                "INSERT OR IGNORE INTO match_keys (record_id, key, kind) "
                "VALUES (?, ?, ?)",
                (record.id, key, kind),
            )

        if not keys:
            return  # no es persona: no participa en clustering

        overrides = _load_overrides(connection, record.id)
        candidate_ids = _candidate_ids(connection, [k for k, _ in keys], record.id)

        matched = []
        for cand_id in candidate_ids:
            decision = overrides.get(cand_id)
            if decision == "split":
                continue
            cand = _match_dict_by_id(connection, cand_id)
            if cand is None:
                continue
            if decision == "link" or entities.match_decision(this, cand) is not None:
                matched.append(cand)

        if not matched:
            return  # singleton: entity_id queda NULL

        existing = sorted({c["entity_id"] for c in matched if c.get("entity_id")})
        if not existing:
            entity_id = uuid.uuid4().hex
            self._create_entity(connection, entity_id)
        elif len(existing) == 1:
            entity_id = existing[0]
        else:
            entity_id = existing[0]
            for other in existing[1:]:
                connection.execute(
                    "UPDATE records SET entity_id = ? WHERE entity_id = ?",
                    (entity_id, other),
                )
                connection.execute("DELETE FROM entities WHERE id = ?", (other,))

        ids_to_assign = [record.id] + [c["id"] for c in matched]
        connection.executemany(
            "UPDATE records SET entity_id = ? WHERE id = ?",
            [(entity_id, rid) for rid in ids_to_assign],
        )
        self._recompute_entity(connection, entity_id)

    def _create_entity(self, connection, entity_id):
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT OR IGNORE INTO entities (id, created_at, updated_at) "
            "VALUES (?, ?, ?)",
            (entity_id, now, now),
        )

    def _recompute_entity(self, connection, entity_id):
        rows = connection.execute(
            "SELECT title, cedula FROM records WHERE entity_id = ?",
            (entity_id,),
        ).fetchall()
        # Una entidad existe solo con 2+ miembros; si queda 1 o 0 se disuelve.
        if len(rows) < 2:
            connection.execute(
                "UPDATE records SET entity_id = NULL WHERE entity_id = ?",
                (entity_id,),
            )
            connection.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            return
        canonical_title = rows[0]["title"]
        canonical_cedula = next(
            (r["cedula"] for r in rows if r["cedula"]), None
        )
        strongest = "cedula" if canonical_cedula else "nombre"
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "UPDATE entities SET canonical_title = ?, canonical_cedula = ?, "
            "record_count = ?, strongest_signal = ?, updated_at = ? WHERE id = ?",
            (canonical_title, canonical_cedula, len(rows), strongest, now, entity_id),
        )

    def get_entity(self, entity_id):
        with self.connect() as connection:
            ent = connection.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            if ent is None:
                return None
            rows = connection.execute(
                "SELECT * FROM records WHERE entity_id = ? "
                "ORDER BY updated_at DESC, indexed_at DESC",
                (entity_id,),
            ).fetchall()
        members = [_record_from_row(row) for row in rows]
        return dict(ent), members

    def link_records(self, record_a, record_b, created_by="admin"):
        """Fuerza el enlace de dos registros (override manual reversible)."""
        a, b = entities.override_key(record_a, record_b)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO entity_overrides (record_a, record_b, decision, "
                "created_by, created_at) VALUES (?, ?, 'link', ?, ?) "
                "ON CONFLICT(record_a, record_b) DO UPDATE SET decision='link', "
                "created_by=excluded.created_by, created_at=excluded.created_at",
                (a, b, created_by, now),
            )
            record = self.get_record(record_b)
            if record is not None:
                self._resolve_entity(connection, record)

    def unlink_record(self, record_id, created_by="admin"):
        """Saca un registro de su entidad y registra overrides de split."""
        with self.connect() as connection:
            row = connection.execute(
                "SELECT entity_id FROM records WHERE id = ?", (record_id,)
            ).fetchone()
            entity_id = row["entity_id"] if row else None
            if not entity_id:
                return False

            now = datetime.now(timezone.utc).isoformat()
            others = connection.execute(
                "SELECT id FROM records WHERE entity_id = ? AND id != ?",
                (entity_id, record_id),
            ).fetchall()
            for other in others:
                a, b = entities.override_key(record_id, other["id"])
                connection.execute(
                    "INSERT INTO entity_overrides (record_a, record_b, decision, "
                    "created_by, created_at) VALUES (?, ?, 'split', ?, ?) "
                    "ON CONFLICT(record_a, record_b) DO UPDATE SET decision='split', "
                    "created_by=excluded.created_by, created_at=excluded.created_at",
                    (a, b, created_by, now),
                )
            connection.execute(
                "UPDATE records SET entity_id = NULL WHERE id = ?", (record_id,)
            )
            self._recompute_entity(connection, entity_id)
        return True

    # ----- Propuestas de conectores ------------------------------------------

    def insert_proposal(self, proposal, source_id, spec, ip=None):
        proposal_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO connector_proposals (
                    id, status, source_id, source_name, kind, description,
                    endpoint_url, http_method, auth_type, auth_header,
                    pagination_json, data_path, field_mapping_json,
                    connector_spec_json, sample_response, docs, contact_name,
                    contact_email, submitter_ip, created_at
                ) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal_id,
                    source_id,
                    proposal.source_name,
                    proposal.kind,
                    proposal.description,
                    proposal.endpoint_url,
                    proposal.http_method,
                    proposal.auth_type,
                    proposal.auth_header,
                    json.dumps(proposal.pagination.model_dump(), ensure_ascii=False),
                    proposal.data_path,
                    json.dumps(proposal.field_mapping, ensure_ascii=False),
                    json.dumps(spec, ensure_ascii=False),
                    proposal.sample_response,
                    proposal.docs,
                    proposal.contact_name,
                    proposal.contact_email,
                    ip,
                    now,
                ),
            )
        return proposal_id

    def list_proposals(self, status=None):
        with self.connect() as connection:
            if status:
                rows = connection.execute(
                    "SELECT * FROM connector_proposals WHERE status = ? "
                    "ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM connector_proposals ORDER BY created_at DESC"
                ).fetchall()
        return [dict(row) for row in rows]

    def get_proposal(self, proposal_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM connector_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        return dict(row) if row else None

    def set_proposal_status(self, proposal_id, status, review_notes=None):
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as connection:
            cur = connection.execute(
                "UPDATE connector_proposals SET status = ?, review_notes = ?, "
                "reviewed_at = ? WHERE id = ?",
                (status, review_notes, now, proposal_id),
            )
        return cur.rowcount > 0

    def get_record(self, record_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM records WHERE id = ?",
                (record_id,),
            ).fetchone()
        return _record_from_row(row) if row else None

    def search_records(
        self,
        query="",
        limit=20,
        offset=0,
        record_type=None,
        source_id=None,
        city=None,
        cedula=None,
        group_by_entity=False,
    ):
        started = perf_counter()

        # Filtros estructurados (sobre el alias r de la tabla records).
        filters = []
        filter_values = []
        if record_type:
            filters.append("r.record_type = ?")
            filter_values.append(record_type)
        if source_id:
            filters.append("r.source_id = ?")
            filter_values.append(source_id)
        if city:
            filters.append("r.search_text LIKE ?")
            filter_values.append("%" + normalize_text(city) + "%")
        if cedula:
            filters.append("r.cedula = ?")
            filter_values.append(digits_only(cedula))

        combined = " ".join(part for part in [query or "", cedula or ""] if part).strip()
        text_tokens = [token for token in tokenize(combined) if not token.isdigit()]
        query_digits = digits_only(combined)
        has_query = bool(text_tokens) or bool(query_digits)

        with self.connect() as connection:
            source_count = connection.execute(
                "SELECT COUNT(*) FROM sources"
            ).fetchone()[0]

            if not has_query:
                ranked, total_matches = self._browse(
                    connection, filters, filter_values, limit, offset
                )
                if group_by_entity:
                    ranked = _collapse_entities(ranked)
                page = ranked
            else:
                candidates = self._search_candidates(
                    connection,
                    filters,
                    filter_values,
                    text_tokens,
                    query_digits,
                )
                ranked = []
                for record in candidates:
                    score, reasons = rank_indexed_record(
                        record, query=query, cedula=cedula
                    )
                    if score > 0:
                        ranked.append((score, reasons, record))
                ranked.sort(
                    key=lambda item: (
                        -item[0],
                        normalize_text(item[2].title),
                        item[2].updated_at.isoformat() if item[2].updated_at else "",
                    )
                )
                if group_by_entity:
                    ranked = _collapse_entities(ranked)
                total_matches = len(ranked)
                page = ranked[offset : offset + limit]

            entity_counts = self._entity_counts(
                connection,
                {rec.entity_id for _, _, rec in page if rec.entity_id},
            )

        elapsed_ms = int((perf_counter() - started) * 1000)

        return IndexedSearchResponse(
            query=query or "",
            count=len(page),
            total_matches=total_matches,
            returned_offset=offset,
            returned_limit=limit,
            source_count=source_count,
            record_types=sorted({item[2].record_type for item in ranked}),
            elapsed_ms=elapsed_ms,
            results=[
                IndexedSearchResult(
                    score=score,
                    reasons=reasons,
                    record=record,
                    entity_id=record.entity_id,
                    also_in_count=max(0, entity_counts.get(record.entity_id, 0) - 1),
                )
                for score, reasons, record in page
            ],
        )

    def _entity_counts(self, connection, entity_ids):
        ids = [eid for eid in entity_ids if eid]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        rows = connection.execute(
            "SELECT id, record_count FROM entities WHERE id IN (%s)" % placeholders,
            ids,
        ).fetchall()
        return {row["id"]: row["record_count"] for row in rows}

    def _browse(self, connection, filters, filter_values, limit, offset):
        """Sin consulta: pagina por recencia en SQL (sin ranking)."""
        where = (" WHERE " + " AND ".join(filters)) if filters else ""
        total = connection.execute(
            "SELECT COUNT(*) FROM records r" + where, filter_values
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT r.* FROM records r"
            + where
            + " ORDER BY r.updated_at DESC, r.indexed_at DESC LIMIT ? OFFSET ?",
            filter_values + [limit, offset],
        ).fetchall()
        page = [
            (1, ["sin_consulta"], _record_from_row(row)) for row in rows
        ]
        return page, total

    def _search_candidates(
        self, connection, filters, filter_values, text_tokens, query_digits
    ):
        """Recupera candidatos via FTS5 (BM25) y/o coincidencia de cedula."""
        by_id = {}
        filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

        if text_tokens:
            match_expr = " OR ".join(
                '"%s"' % token.replace('"', "") for token in text_tokens
            )
            sql = (
                "SELECT r.* FROM records r "
                "JOIN records_fts ON r.rowid = records_fts.rowid "
                "WHERE records_fts MATCH ?" + filter_sql + " "
                "ORDER BY bm25(records_fts) ASC LIMIT ?"
            )
            rows = connection.execute(
                sql, [match_expr] + filter_values + [_CANDIDATE_LIMIT]
            ).fetchall()
            for row in rows:
                by_id[row["id"]] = row

        if query_digits:
            sql = (
                "SELECT r.* FROM records r "
                "WHERE (r.cedula = ? OR r.cedula LIKE ?)" + filter_sql + " "
                "LIMIT ?"
            )
            rows = connection.execute(
                sql,
                [query_digits, query_digits + "%"] + filter_values + [_CANDIDATE_LIMIT],
            ).fetchall()
            for row in rows:
                by_id[row["id"]] = row

        return [_record_from_row(row) for row in by_id.values()]

    def stats(self):
        with self.connect() as connection:
            total_records = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
            type_rows = connection.execute(
                "SELECT record_type, COUNT(*) AS count FROM records GROUP BY record_type"
            ).fetchall()
        sources = self.list_sources()
        return {
            "total_records": total_records,
            "total_sources": len(sources),
            "record_types": {row["record_type"]: row["count"] for row in type_rows},
            "sources": sources,
        }


def rank_indexed_record(record, query="", cedula=None):
    combined = " ".join(part for part in [query or "", cedula or ""] if part).strip()
    normalized_query = normalize_text(combined)
    tokens = tokenize(combined)
    query_digits = digits_only(combined)

    if not normalized_query and not query_digits:
        return 1, ["sin_consulta"]

    score = 0
    reasons = []

    record_cedula = digits_only(record.cedula)
    if query_digits and record_cedula:
        if query_digits == record_cedula:
            score = _add_score(score, reasons, 1000, "cedula_exacta")
        elif record_cedula.startswith(query_digits):
            score = _add_score(score, reasons, 450, "cedula_prefijo")

    fields = {
        "titulo": record.title,
        "persona": record.person_name,
        "organizacion": record.organization,
        "ubicacion": " ".join(
            part
            for part in [
                record.location_name,
                record.city,
                record.state,
                record.country,
            ]
            if part
        ),
        "resumen": record.summary,
        "etiquetas": " ".join(record.tags),
    }
    weights = {
        "titulo": 85,
        "persona": 90,
        "organizacion": 45,
        "ubicacion": 35,
        "resumen": 25,
        "etiquetas": 30,
    }

    if normalized_query:
        for field in ["titulo", "persona"]:
            normalized_field = normalize_text(fields[field])
            if normalized_query == normalized_field:
                score = _add_score(score, reasons, 650, "%s_exacto" % field)
            elif normalized_query and normalized_query in normalized_field:
                score = _add_score(score, reasons, 360, "%s_contiene" % field)

    if tokens:
        for field, weight in weights.items():
            field_tokens = set(tokenize(fields[field]))
            matched = [token for token in tokens if token in field_tokens]
            if matched:
                score = _add_score(score, reasons, weight * len(matched), field)

    # Bonus si TODAS las palabras de la consulta (>=2) estan en el nombre o el
    # titulo: prioriza coincidencias de NOMBRE COMPLETO sobre las parciales, para
    # que quien busca un nombre entero vea arriba a las personas mas parecidas.
    if len(tokens) >= 2:
        for field in ("persona", "titulo"):
            field_tokens = set(tokenize(fields[field]))
            if field_tokens and all(token in field_tokens for token in tokens):
                score = _add_score(score, reasons, 400, "%s_completo" % field)
                break

    if record.age is not None and str(record.age) in tokens:
        score = _add_score(score, reasons, 60, "edad")

    return score, reasons


def _add_score(score, reasons, amount, reason):
    score += amount
    if reason not in reasons:
        reasons.append(reason)
    return score


def _content_hash(record):
    """Hash del contenido sustantivo (excluye timestamps/feed/origin/indexed_at).

    Permite saltar re-escrituras cuando el registro no cambio realmente, aunque
    la fuente regenere campos de fecha en cada respuesta.
    """
    parts = [
        record.record_type, record.title, record.summary, record.person_name,
        digits_only(record.cedula), record.age, record.organization,
        record.location_name, record.city, record.state, record.country,
        record.latitude, record.longitude, record.contact, record.status,
        record.verified, record.source_id, record.source_record_id,
        record.tags, record.raw, record.image_url,
    ]
    blob = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _record_values(record, indexed_at, feed_seq, content_hash):
    return (
        record.id,
        record.record_type,
        record.title,
        record.summary,
        record.person_name,
        digits_only(record.cedula) or None,
        record.age,
        record.organization,
        record.location_name,
        record.city,
        record.state,
        record.country,
        record.latitude,
        record.longitude,
        record.contact,
        record.status,
        _bool_to_int(record.verified),
        record.source_id,
        record.source_name,
        record.source_url,
        record.source_record_id,
        _datetime_to_text(record.observed_at),
        _datetime_to_text(record.updated_at),
        json.dumps(record.tags, ensure_ascii=False),
        json.dumps(record.raw, ensure_ascii=False, default=str),
        _search_text(record),
        indexed_at,
        record.origin_node,
        record.origin_source,
        feed_seq,
        record.image_url,
        content_hash,
    )


def _search_text(record):
    return normalize_text(
        " ".join(
            str(part)
            for part in [
                record.title,
                record.summary,
                record.person_name,
                record.cedula,
                record.age,
                record.organization,
                record.location_name,
                record.city,
                record.state,
                record.country,
                record.contact,
                record.status,
                " ".join(record.tags),
            ]
            if part is not None
        )
    )


def _record_from_row(row):
    raw = dict(row)
    return IndexedRecord(
        id=raw["id"],
        record_type=raw["record_type"],
        title=raw["title"],
        summary=raw["summary"],
        person_name=raw["person_name"],
        cedula=raw["cedula"],
        age=raw["age"],
        organization=raw["organization"],
        location_name=raw["location_name"],
        city=raw["city"],
        state=raw["state"],
        country=raw["country"],
        latitude=raw["latitude"],
        longitude=raw["longitude"],
        contact=raw["contact"],
        status=raw["status"],
        verified=_int_to_bool(raw["verified"]),
        source_id=raw["source_id"],
        source_name=raw["source_name"],
        source_url=raw["source_url"],
        source_record_id=raw["source_record_id"],
        observed_at=_text_to_datetime(raw["observed_at"]),
        updated_at=_text_to_datetime(raw["updated_at"]),
        tags=json.loads(raw["tags_json"] or "[]"),
        raw=json.loads(raw["raw_json"] or "{}"),
        origin_node=raw["origin_node"],
        origin_source=raw["origin_source"],
        entity_id=raw["entity_id"],
        image_url=raw["image_url"],
    )


def _collapse_entities(ranked):
    """Colapsa resultados a uno por entidad (conserva el de mayor score).

    Los registros sin entity_id se mantienen individualmente.
    """
    seen = set()
    collapsed = []
    for item in ranked:
        record = item[2]
        if record.entity_id:
            if record.entity_id in seen:
                continue
            seen.add(record.entity_id)
        collapsed.append(item)
    return collapsed


def _match_dict_from_record(record):
    return {
        "id": record.id,
        "cedula": record.cedula,
        "person_name": record.person_name,
        "city": record.city,
        "age": record.age,
    }


def _match_dict_by_id(connection, record_id):
    row = connection.execute(
        "SELECT id, cedula, person_name, city, age, entity_id "
        "FROM records WHERE id = ?",
        (record_id,),
    ).fetchone()
    return dict(row) if row else None


def _load_overrides(connection, record_id):
    """Devuelve {otro_record_id: 'link'|'split'} para el registro dado."""
    rows = connection.execute(
        "SELECT record_a, record_b, decision FROM entity_overrides "
        "WHERE record_a = ? OR record_b = ?",
        (record_id, record_id),
    ).fetchall()
    result = {}
    for row in rows:
        other = row["record_b"] if row["record_a"] == record_id else row["record_a"]
        result[other] = row["decision"]
    return result


def _candidate_ids(connection, keys, self_id):
    if not keys:
        return []
    placeholders = ",".join("?" for _ in keys)
    rows = connection.execute(
        "SELECT DISTINCT record_id FROM match_keys "
        "WHERE key IN (%s) AND record_id != ?" % placeholders,
        keys + [self_id],
    ).fetchall()
    return [row["record_id"] for row in rows]


def _source_from_row(row):
    raw = dict(row)
    return SourceInfo(
        id=raw["id"],
        name=raw["name"],
        kind=raw["kind"],
        description=raw["description"],
        url=raw["url"],
        access=raw["access"],
        enabled=bool(raw["enabled"]),
        record_count=raw["live_count"] if "live_count" in raw else raw["record_count"],
        last_sync=_text_to_datetime(raw["last_sync"]),
    )


def _peer_from_row(row):
    from .models import PeerInfo

    raw = dict(row)
    return PeerInfo(
        id=raw["id"],
        name=raw["name"],
        base_url=raw["base_url"],
        enabled=bool(raw["enabled"]),
        pull_enabled=bool(raw["pull_enabled"]),
        last_cursor=raw["last_cursor"],
        last_pull_at=_text_to_datetime(raw["last_pull_at"]),
        last_status=raw["last_status"],
        created_at=_text_to_datetime(raw["created_at"]),
    )


def _datetime_to_text(value):
    if value is None:
        return None
    return value.isoformat()


def _text_to_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _bool_to_int(value):
    if value is None:
        return None
    return int(bool(value))


def _int_to_bool(value):
    if value is None:
        return None
    return bool(value)
