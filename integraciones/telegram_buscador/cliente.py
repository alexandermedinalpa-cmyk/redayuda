"""Cliente HTTP del índice de redayuda (solo stdlib, fetch inyectable para tests)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

Fetch = Callable[[str], dict]


def _get_json(url: str, fetch: Fetch | None = None, timeout: int = 20) -> dict:
    if fetch is not None:
        return fetch(url)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL de config)
        return json.loads(resp.read().decode("utf-8"))


def buscar(
    base: str,
    q: str,
    *,
    limit: int = 10,
    group_by_entity: bool = True,
    fetch: Fetch | None = None,
) -> list[dict]:
    """GET /api/records/search -> lista de resultados [{score, record, also_in_count}]."""
    qs = urllib.parse.urlencode({
        "q": q or "",
        "limit": limit,
        "group_by_entity": "true" if group_by_entity else "false",
    })
    data = _get_json("%s/api/records/search?%s" % (base.rstrip("/"), qs), fetch)
    if not isinstance(data, dict):
        return []
    return data.get("results", [])


def feed(base: str, since: int = 0, *, limit: int = 200, fetch: Fetch | None = None) -> dict:
    """GET /api/records/feed -> {records, next_cursor, count, has_more}."""
    qs = urllib.parse.urlencode({"since": since, "limit": limit})
    data = _get_json("%s/api/records/feed?%s" % (base.rstrip("/"), qs), fetch)
    if not isinstance(data, dict):
        return {"records": [], "next_cursor": since, "count": 0, "has_more": False}
    data.setdefault("records", [])
    data.setdefault("next_cursor", since)
    return data
