"""Tests de suscripciones y matching de alertas."""

from integraciones.telegram_buscador import alertas


def test_suscribir_y_dedup():
    e = alertas.estado_inicial()
    alertas.suscribir(e, 100, "José Pérez García")
    alertas.suscribir(e, 100, "García Pérez José")  # mismos tokens (orden distinto) -> dedup
    assert len(e["suscripciones"]) == 1


def test_mias_y_quitar():
    e = alertas.estado_inicial()
    alertas.suscribir(e, 1, "Ana Gómez")
    alertas.suscribir(e, 1, "Luis Pérez")
    alertas.suscribir(e, 2, "Otra Persona")
    assert set(alertas.mias(e, 1)) == {"Ana Gómez", "Luis Pérez"}
    alertas.quitar(e, 1, "ana gomez")
    assert alertas.mias(e, 1) == ["Luis Pérez"]


def test_revisar_avisa_solo_apariciones_y_avanza_cursor():
    e = alertas.estado_inicial()
    alertas.suscribir(e, 55, "Carmen Núñez")
    payload = {
        "records": [
            {"person_name": "Carmen Nunez", "record_type": "persona_hospitalizada",
             "organization": "Hospital", "city": "San Felipe"},
            # mismo nombre pero solo "sigue desaparecida": NO debe avisar
            {"person_name": "Carmen Núñez", "record_type": "persona_desaparecida"},
            # otra persona: NO
            {"person_name": "Pedro Ramírez", "record_type": "persona_localizada"},
        ],
        "next_cursor": 99,
    }
    avisos, e = alertas.revisar(e, payload)
    assert len(avisos) == 1
    assert avisos[0][0] == 55
    assert e["cursor"] == 99


def test_match_por_cedula_exacta():
    e = alertas.estado_inicial()
    alertas.suscribir(e, 7, "Nombre Distinto", cedula="12.345.678")
    payload = {"records": [
        {"person_name": "Otro Nombre", "cedula": "12345678",
         "record_type": "persona_localizada"},
    ], "next_cursor": 1}
    avisos, _ = alertas.revisar(e, payload)
    assert len(avisos) == 1  # coincide por cédula aunque el nombre difiera


def test_persistencia_roundtrip(tmp_path):
    ruta = str(tmp_path / "alertas.json")
    e = alertas.estado_inicial()
    alertas.suscribir(e, 9, "Ana Gómez")
    e["cursor"] = 12
    alertas.guardar(ruta, e)
    e2 = alertas.cargar(ruta)
    assert e2["cursor"] == 12
    assert alertas.mias(e2, 9) == ["Ana Gómez"]
