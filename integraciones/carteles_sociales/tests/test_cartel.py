"""Tests del generador de carteles SVG."""

from html.parser import HTMLParser

from integraciones.carteles_sociales import cartel


def _bien_formado(svg: str) -> None:
    # SVG es marcado; validamos que parsea sin error con html.parser (no XXE).
    HTMLParser().feed(svg)


def test_cartel_contiene_datos_clave():
    rec = {
        "title": "José Pérez García", "record_type": "persona_desaparecida",
        "age": 34, "location_name": "Edificio Sol, La Guaira", "city": "La Guaira",
        "contact": "+58 412 0000001", "source_name": "Te Busco",
    }
    svg = cartel.cartel_svg(rec)
    _bien_formado(svg)
    assert svg.startswith("<?xml")
    assert "SE BUSCA" in svg
    assert "JOSÉ PÉREZ GARCÍA" in svg  # nombre en mayúsculas, con acentos
    assert "34" in svg
    assert "La Guaira" in svg
    assert "+58 412 0000001" in svg
    assert "Te Busco" in svg


def test_escapa_caracteres_peligrosos():
    rec = {"title": 'Ana <b>"&"</b>', "record_type": "persona_desaparecida"}
    svg = cartel.cartel_svg(rec)
    _bien_formado(svg)
    assert "<b>" not in svg  # debe quedar escapado
    assert "&lt;b&gt;" in svg or "&amp;" in svg


def test_sin_foto_usa_placeholder():
    svg = cartel.cartel_svg({"title": "Sin Foto", "record_type": "persona_desaparecida"})
    assert "<circle" in svg  # placeholder
    assert "<image" not in svg


def test_con_foto_incrusta_imagen():
    svg = cartel.cartel_svg({"title": "Con Foto", "image_url": "https://x/f.jpg",
                             "record_type": "persona_desaparecida"})
    assert "<image" in svg
    assert "https://x/f.jpg" in svg


def test_nombre_archivo_es_slug_seguro():
    n = cartel.nombre_archivo({"title": "José Pérez/García"}, 3)
    assert n == "jose-perez-garcia-3.svg"


def test_nombre_largo_se_envuelve():
    svg = cartel.cartel_svg({"title": "Maria De Los Angeles Rodriguez Hernandez",
                             "record_type": "persona_desaparecida"})
    # Varias líneas -> varios tspan en el bloque de nombre.
    assert svg.count("<tspan") >= 2
