"""Tests de la exportación imprimible."""

from integraciones.exportacion_offline import exportar

REGS = [
    {"title": "José Pérez", "record_type": "persona_hospitalizada",
     "organization": "Hospital Vargas", "city": "La Guaira", "age": 34, "status": "estable",
     "source_name": "Hospitales VE", "cedula": "12345678", "contact": "+58 412 000"},
    {"title": "Ana Gómez", "record_type": "persona_hospitalizada",
     "organization": "Hospital Vargas", "city": "La Guaira", "age": 28, "source_name": "Hospitales VE"},
    {"title": "Carmen Núñez", "record_type": "persona_localizada",
     "organization": "Hospital Central", "city": "San Felipe", "source_name": "Colaborativo"},
    # un desaparecido: NO debe salir en la lista de localizadas
    {"title": "Luis Alberto", "record_type": "persona_desaparecida", "city": "Caracas"},
]


def test_solo_localizadas_filtra_desaparecidos():
    locs = exportar.solo_localizadas(REGS)
    assert len(locs) == 3
    assert all(r["record_type"] != "persona_desaparecida" for r in locs)


def test_agrupar_por_organizacion_ordena():
    grupos = exportar.agrupar_por(exportar.solo_localizadas(REGS), "organization")
    assert list(grupos.keys()) == ["Hospital Central", "Hospital Vargas"]
    assert len(grupos["Hospital Vargas"]) == 2
    # dentro del grupo, orden alfabético por nombre
    assert grupos["Hospital Vargas"][0]["title"] == "Ana Gómez"


def test_html_es_valido_y_contiene_personas():
    html = exportar.html_listado(REGS, agrupar_campo="organization", generado="2026-06-30")
    # Validamos que el HTML se parsea sin error con html.parser (no vulnerable a XXE).
    from html.parser import HTMLParser

    HTMLParser().feed(html)  # lanza si el marcado está roto
    # Una sección por grupo (dos hospitales).
    assert html.count("<section>") == 2
    assert "José Pérez" in html
    assert "Hospital Vargas" in html
    assert "2026-06-30" in html


def test_html_no_expone_cedula_ni_contacto():
    html = exportar.html_listado(REGS)
    assert "12345678" not in html
    assert "+58 412" not in html


def test_html_vacio_no_rompe():
    html = exportar.html_listado([], generado="")
    assert "No hay personas localizadas" in html
