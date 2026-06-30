"""Genera HTML imprimible a partir de registros del índice.

Funciones puras (reciben una lista de registros tipo IndexedRecord como dicts),
fáciles de testear. El HTML usa CSS de impresión con salto de página por grupo,
pensado para imprimir hojas por hospital/ciudad y pegarlas físicamente.

Privacidad: se listan personas LOCALIZADAS (lo que las familias quieren ver para
reencontrarse). NO se incluye cédula ni contacto de la persona.
"""

from __future__ import annotations

from collections import OrderedDict
from xml.sax.saxutils import escape

TIPOS_LOCALIZADA = {"persona_localizada", "persona_hospitalizada", "persona_fallecida"}


def solo_localizadas(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("record_type") in TIPOS_LOCALIZADA]


def agrupar_por(records: list[dict], campo: str) -> "OrderedDict[str, list[dict]]":
    grupos: "OrderedDict[str, list[dict]]" = OrderedDict()
    for r in records:
        clave = (r.get(campo) or "Sin especificar").strip() or "Sin especificar"
        grupos.setdefault(clave, []).append(r)
    # Orden alfabético de grupos; dentro, por nombre.
    ordenado: "OrderedDict[str, list[dict]]" = OrderedDict()
    for clave in sorted(grupos, key=lambda c: c.lower()):
        filas = sorted(grupos[clave], key=lambda r: (r.get("title") or r.get("person_name") or "").lower())
        ordenado[clave] = filas
    return ordenado


def _fila_persona(r: dict) -> str:
    nombre = escape(str(r.get("title") or r.get("person_name") or "Sin nombre"))
    edad = r.get("age")
    edad_txt = ("%s años" % escape(str(edad))) if edad is not None else "—"
    estado = escape(str(r.get("status") or ""))
    fuente = escape(str(r.get("source_name") or r.get("source_id") or ""))
    return (
        "<tr><td class='n'>%s</td><td>%s</td><td>%s</td><td class='f'>%s</td></tr>"
        % (nombre, edad_txt, estado or "—", fuente)
    )


def html_listado(records: list[dict], titulo: str = "Personas localizadas",
                 agrupar_campo: str = "organization", generado: str = "") -> str:
    locs = solo_localizadas(records)
    grupos = agrupar_por(locs, agrupar_campo)
    secciones = []
    for clave, filas in grupos.items():
        cuerpo = "\n".join(_fila_persona(r) for r in filas)
        secciones.append(
            "<section><h2>%s <span class='cnt'>(%d)</span></h2>"
            "<table><thead><tr><th>Nombre</th><th>Edad</th><th>Estado</th><th>Fuente</th>"
            "</tr></thead><tbody>%s</tbody></table></section>"
            % (escape(clave), len(filas), cuerpo)
        )
    cuerpo_html = "\n".join(secciones) or "<p>No hay personas localizadas para mostrar.</p>"
    pie = ("Generado: %s · " % escape(generado)) if generado else ""
    return """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>%s</title>
<style>
  body{font-family:system-ui,Arial,sans-serif;color:#000;margin:24px;}
  h1{font-size:20px;margin:0 0 4px;} .sub{font-size:12px;color:#444;margin:0 0 16px;}
  section{margin:0 0 20px;} h2{font-size:15px;border-bottom:2px solid #000;padding-bottom:3px;}
  .cnt{font-weight:normal;color:#555;font-size:12px;}
  table{width:100%%;border-collapse:collapse;font-size:13px;} th,td{text-align:left;padding:4px 6px;border-bottom:1px solid #ccc;}
  td.n{font-weight:600;} td.f{color:#555;font-size:11px;}
  @media print{ section{page-break-inside:avoid;} h2{page-break-after:avoid;} body{margin:10mm;} }
</style></head>
<body>
<h1>%s</h1>
<p class="sub">%sRed Rescate Venezuela — lista para imprimir y compartir. Verifica con el centro indicado.</p>
%s
</body></html>""" % (escape(titulo), escape(titulo), pie, cuerpo_html)
