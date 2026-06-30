"""Tests de la capa de verificación ciudadana."""

import pytest

from integraciones.verificacion_ciudadana import logica


def test_registrar_y_resumen():
    e = logica.estado_inicial()
    logica.registrar(e, "src:1", "confirma", autor="a")
    logica.registrar(e, "src:1", "confirma", autor="b")
    r = logica.resumen(e, "src:1")
    assert r["confirma"] == 2
    assert r["etiqueta"] == "verificado_comunidad"


def test_un_autor_un_voto_por_registro():
    e = logica.estado_inicial()
    logica.registrar(e, "src:1", "confirma", autor="a")
    logica.registrar(e, "src:1", "desmiente", autor="a")  # cambia su voto
    r = logica.resumen(e, "src:1")
    assert r["confirma"] == 0
    assert r["desmiente"] == 1
    assert r["total"] == 1


def test_tipo_invalido_falla():
    e = logica.estado_inicial()
    with pytest.raises(ValueError):
        logica.registrar(e, "src:1", "me_gusta", autor="a")


def test_clasificar_posible_desinformacion():
    assert logica.clasificar(0, 0, 2, 0) == "posible_desinformacion"
    assert logica.clasificar(1, 0, 2, 0) == "posible_desinformacion"


def test_clasificar_en_disputa_y_duplicado():
    assert logica.clasificar(1, 2, 0, 0) == "en_disputa"
    assert logica.clasificar(0, 0, 0, 2) == "posible_duplicado"


def test_clasificar_sin_verificar_y_parcial():
    assert logica.clasificar(0, 0, 0, 0) == "sin_verificar"
    assert logica.clasificar(1, 0, 0, 0) == "confirmacion_parcial"


def test_overlay_no_muta_original():
    e = logica.estado_inicial()
    logica.registrar(e, "src:1", "sospecha", autor="a")
    logica.registrar(e, "src:1", "sospecha", autor="b")
    originales = [{"id": "src:1", "title": "X"}, {"id": "src:2", "title": "Y"}]
    con_overlay = logica.aplicar_overlay(e, originales)
    assert "verificacion" not in originales[0]  # original intacto
    assert con_overlay[0]["verificacion"]["etiqueta"] == "posible_desinformacion"
    assert con_overlay[1]["verificacion"]["etiqueta"] == "sin_verificar"


def test_persistencia_roundtrip(tmp_path):
    ruta = str(tmp_path / "votos.json")
    e = logica.estado_inicial()
    logica.registrar(e, "src:9", "confirma", autor="a")
    logica.guardar(ruta, e)
    e2 = logica.cargar(ruta)
    assert logica.resumen(e2, "src:9")["confirma"] == 1
