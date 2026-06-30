"""Tests de la lógica de respuesta (pura, sin HTTP)."""

import json

from integraciones.telegram_buscador import alertas
from integraciones.whatsapp_buscador import app


def _fetch_resultados(payload):
    return lambda url: payload


def test_nombre_directo_busca():
    payload = {"results": [{"record": {"title": "José Pérez", "record_type": "persona_hospitalizada",
                                       "organization": "Hospital Vargas", "city": "La Guaira"}}]}
    e = alertas.estado_inicial()
    msg = app.responder("José Pérez", "584120000000", e, "http://x", fetch=_fetch_resultados(payload))
    assert "José Pérez" in msg
    assert "Hospital Vargas" in msg


def test_hola_devuelve_ayuda():
    msg = app.responder("hola", "584120000000", alertas.estado_inicial(), "http://x",
                        fetch=lambda u: {"results": []})
    assert "Red Rescate Venezuela" in msg


def test_alerta_suscribe():
    e = alertas.estado_inicial()
    msg = app.responder("alerta Carmen Núñez", "584120000000", e, "http://x")
    assert "Te avisaré" in msg
    assert alertas.mias(e, "584120000000") == ["Carmen Núñez"]


def test_sin_resultados_ofrece_alerta():
    e = alertas.estado_inicial()
    msg = app.responder("Inexistente", "584120000000", e, "http://x",
                        fetch=lambda u: {"results": []})
    assert "alerta" in msg.lower()


def test_quitar_y_mis_alertas():
    e = alertas.estado_inicial()
    app.responder("alerta Ana Gómez", "584120000000", e, "http://x")
    assert "Ana Gómez" in app.responder("mis alertas", "584120000000", e, "http://x",
                                        fetch=lambda u: {"results": []})
    app.responder("quitar Ana Gómez", "584120000000", e, "http://x")
    assert alertas.mias(e, "584120000000") == []
