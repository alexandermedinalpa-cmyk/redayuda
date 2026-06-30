"""Tests del cliente HTTP (con fetch inyectado, sin red)."""

import json

from integraciones.telegram_buscador import cliente


def test_buscar_devuelve_results():
    payload = {"results": [
        {"score": 10, "record": {"title": "Ana Gómez"}, "also_in_count": 2},
    ]}
    fetch = lambda url: payload
    res = cliente.buscar("http://x", "ana", fetch=fetch)
    assert len(res) == 1
    assert res[0]["record"]["title"] == "Ana Gómez"


def test_buscar_construye_url_con_group_by_entity():
    capturada = {}
    def fetch(url):
        capturada["url"] = url
        return {"results": []}
    cliente.buscar("http://x/", "josé pérez", fetch=fetch)
    assert "/api/records/search?" in capturada["url"]
    assert "group_by_entity=true" in capturada["url"]
    assert "q=jos" in capturada["url"]  # url-encoded


def test_feed_normaliza_respuesta():
    fetch = lambda url: {"records": [{"title": "X"}], "next_cursor": 42, "has_more": True}
    data = cliente.feed("http://x", 0, fetch=fetch)
    assert data["next_cursor"] == 42
    assert len(data["records"]) == 1


def test_feed_tolera_respuesta_invalida():
    data = cliente.feed("http://x", 7, fetch=lambda url: "no soy un dict")
    assert data["records"] == []
    assert data["next_cursor"] == 7
