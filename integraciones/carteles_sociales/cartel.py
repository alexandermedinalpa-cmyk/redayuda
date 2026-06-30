"""Genera un cartel SVG 1080x1080 'SE BUSCA' a partir de un registro.

SVG es texto, sin dependencias, escala sin pérdida y se convierte fácil a PNG.
Pensado para registros de personas desaparecidas (los que se comparten para
encontrar a alguien).
"""

from __future__ import annotations

from xml.sax.saxutils import escape

LIENZO = 1080


def _wrap(texto: str, max_chars: int) -> list[str]:
    palabras = texto.split()
    lineas: list[str] = []
    actual = ""
    for w in palabras:
        if len(actual) + len(w) + 1 <= max_chars:
            actual = (actual + " " + w).strip()
        else:
            if actual:
                lineas.append(actual)
            actual = w
    if actual:
        lineas.append(actual)
    return lineas or [""]


def _tspans(lineas: list[str], x: int, y: int, dy: int) -> str:
    out = []
    for i, ln in enumerate(lineas):
        out.append('<tspan x="%d" y="%d">%s</tspan>' % (x, y + i * dy, escape(ln)))
    return "".join(out)


def cartel_svg(record: dict) -> str:
    nombre = str(record.get("title") or record.get("person_name") or "Persona sin nombre")
    edad = record.get("age")
    visto = record.get("location_name") or record.get("city") or ""
    ciudad = record.get("city") or ""
    contacto = record.get("contact") or ""
    fuente = record.get("source_name") or record.get("source_id") or ""
    foto = record.get("image_url")

    nombre_lineas = _wrap(nombre.upper(), 18)
    nombre_y = 560
    nombre_svg = _tspans(nombre_lineas, 540, nombre_y, 70)

    detalles = []
    if edad is not None:
        detalles.append("Edad aproximada: %s" % escape(str(edad)))
    if visto:
        detalles.append("Visto por última vez: %s" % escape(str(visto)))
    elif ciudad:
        detalles.append("Zona: %s" % escape(str(ciudad)))
    det_y = nombre_y + len(nombre_lineas) * 70 + 20
    det_svg = "".join(
        '<text x="540" y="%d" text-anchor="middle" font-size="30" fill="#1a1a1a">%s</text>'
        % (det_y + i * 44, d) for i, d in enumerate(detalles)
    )

    # Foto opcional (incrustada por URL). Si no hay, marco con iniciales.
    if foto:
        media = ('<image href="%s" x="365" y="150" width="350" height="350" '
                 'preserveAspectRatio="xMidYMid slice"/>' % escape(str(foto)))
    else:
        media = ('<circle cx="540" cy="325" r="175" fill="#e0e0e0"/>'
                 '<text x="540" y="350" text-anchor="middle" font-size="120" fill="#9e9e9e">?</text>')

    contacto_svg = ""
    if contacto:
        contacto_svg = ('<text x="540" y="930" text-anchor="middle" font-size="34" '
                        'font-weight="bold" fill="#fff">Si tienes información: %s</text>'
                        % escape(str(contacto)))

    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{L}" height="{L}" viewBox="0 0 {L} {L}" font-family="Arial, sans-serif">
  <rect width="{L}" height="{L}" fill="#ffffff"/>
  <rect x="0" y="0" width="{L}" height="120" fill="#cf142b"/>
  <text x="540" y="82" text-anchor="middle" font-size="64" font-weight="bold" fill="#fff" letter-spacing="6">SE BUSCA</text>
  {media}
  {nombre}
  {detalles}
  <rect x="0" y="870" width="{L}" height="150" fill="#0b3d91"/>
  {contacto}
  <text x="540" y="985" text-anchor="middle" font-size="22" fill="#cdd6f0">Fuente: {fuente} · Red Rescate Venezuela (sin fines de lucro)</text>
</svg>""".format(
        L=LIENZO,
        media=media,
        nombre='<text text-anchor="middle" font-size="58" font-weight="bold" fill="#0b3d91">%s</text>' % nombre_svg,
        detalles=det_svg,
        contacto=contacto_svg,
        fuente=escape(str(fuente)),
    )


def nombre_archivo(record: dict, indice: int = 0) -> str:
    import unicodedata
    from re import sub

    base = str(record.get("title") or record.get("person_name") or "persona")
    # Quitar acentos (ñ->n incluido) antes de generar el slug.
    base = base.replace("ñ", "n")
    base = "".join(c for c in unicodedata.normalize("NFD", base)
                   if unicodedata.category(c) != "Mn")
    slug = sub(r"[^a-zA-Z0-9]+", "-", base).strip("-").lower() or "persona"
    return "%s-%d.svg" % (slug, indice)
