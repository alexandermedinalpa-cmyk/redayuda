"""Tests de formateo y, sobre todo, del trato ético/compasivo."""

from integraciones.telegram_buscador import formato


def test_resultado_incluye_lo_util_y_oculta_datos_sensibles():
    rec = {
        "title": "José Pérez", "record_type": "persona_hospitalizada",
        "organization": "Hospital Vargas", "city": "La Guaira", "age": 34,
        "status": "estable", "source_name": "Hospitales VE",
        "cedula": "12345678", "contact": "+58 412 0000000",
    }
    msg = formato.formato_resultado({"record": rec, "also_in_count": 3})
    assert "José Pérez" in msg
    assert "Hospital Vargas" in msg
    assert "Hospitales VE" in msg
    assert "3 fuente" in msg
    # NUNCA exponer cédula ni contacto.
    assert "12345678" not in msg
    assert "+58 412" not in msg


def test_es_aparicion_cubre_vivo_herido_necesidad_y_fallecido():
    assert formato.es_aparicion({"record_type": "persona_localizada"})
    assert formato.es_aparicion({"record_type": "persona_hospitalizada"})
    assert formato.es_aparicion({"record_type": "persona_desaparecida", "status": "con vida"})
    assert formato.es_aparicion({"record_type": "persona_desaparecida", "status": "herido"})
    assert formato.es_aparicion({"record_type": "persona_desaparecida", "status": "necesita ayuda"})
    assert formato.es_aparicion({"record_type": "persona_desaparecida", "status": "fallecida"})


def test_un_nuevo_reporte_de_sigue_desaparecida_no_es_aparicion():
    assert not formato.es_aparicion(
        {"record_type": "persona_desaparecida", "status": "desaparecida"}
    )
    assert not formato.es_aparicion({"record_type": "persona_desaparecida"})


def test_caso_fallecimiento_es_sensible_y_no_afirma():
    rec = {"title": "María López", "record_type": "persona_localizada", "status": "fallecida",
           "source_name": "Registro Civil"}
    assert formato.es_sensible(rec) is True
    msg = formato.formato_alerta(rec)
    # Trato compasivo y NO aseverativo: redirige a la fuente, no declara la muerte.
    assert "podría" in msg.lower()
    assert "Registro Civil" in msg
    assert "acompañamos" in msg.lower()
    # No debe contener afirmaciones tajantes de muerte.
    assert "está muerto" not in msg.lower()


def test_alerta_normal_pide_verificar():
    rec = {"title": "Luis Pérez", "record_type": "persona_hospitalizada",
           "organization": "Hospital X", "city": "Caracas", "source_name": "Fuente Y"}
    assert formato.es_sensible(rec) is False
    msg = formato.formato_alerta(rec)
    assert "Luis Pérez" in msg
    assert "verifica" in msg.lower()


def test_resultado_incluye_enlaces_de_ubicacion():
    rec = {"title": "Ana", "record_type": "persona_hospitalizada",
           "latitude": 10.6, "longitude": -66.9}
    msg = formato.formato_resultado({"record": rec})
    assert "google.com/maps/search/?api=1&query=10.6,-66.9" in msg
    assert "map_action=pano" in msg  # Street View


def test_resultado_sin_coords_no_pone_enlaces():
    msg = formato.formato_resultado({"record": {"title": "Ana", "record_type": "recurso"}})
    assert "google.com/maps" not in msg
