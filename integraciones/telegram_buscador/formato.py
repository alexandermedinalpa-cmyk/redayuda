"""Formateo de registros a mensajes de chat, con cuidado ético.

Reglas:
- NUNCA se expone cédula ni contacto de la persona buscada en el mensaje público.
- Las coincidencias delicadas (fallecimiento) NO se afirman: se redirige a la
  fuente/autoridad para confirmación humana, con un tono compasivo.
- Siempre se recuerda verificar (puede haber homónimos).
"""

from __future__ import annotations

from .normaliza import normalizar

TIPO_LEGIBLE = {
    "persona_desaparecida": "🔴 Reportada como desaparecida",
    "persona_localizada": "🟢 Localizada",
    "persona_hospitalizada": "🏥 En un centro de salud",
    "centro_acopio": "📦 Centro de acopio",
    "centro_donacion": "📦 Centro de donación",
    "recurso": "ℹ️ Recurso",
}

# Estados que indican que la persona "apareció" (hay noticia de ella).
_FALLECIDA = {"fallecida", "fallecido", "fallecimiento", "muerto", "muerta", "occiso", "deceased"}
_CON_NOVEDAD = {
    "localizada", "localizado", "encontrada", "encontrado", "viva", "vivo",
    "con vida", "salvo", "a salvo", "hospitalizada", "hospitalizado",
    "atendida", "atendido", "herida", "herido", "enferma", "enfermo",
    "necesita", "rescate", "rescatada", "rescatado",
}


def _lugar(rec: dict) -> str | None:
    org = rec.get("organization")
    city = rec.get("city")
    if org and city:
        return "%s (%s)" % (org, city)
    return org or rec.get("location_name") or city


def es_sensible(rec: dict) -> bool:
    """True si la coincidencia involucra un posible fallecimiento (trato delicado)."""
    st = normalizar(rec.get("status"))
    return any(k in st for k in _FALLECIDA) or normalizar(rec.get("record_type")) == "persona_fallecida"


def es_aparicion(rec: dict) -> bool:
    """True si el registro da NOTICIA de la persona (viva, herida, en necesidad o
    fallecida). Un nuevo reporte de "sigue desaparecida" no cuenta."""
    rt = rec.get("record_type")
    if rt in ("persona_localizada", "persona_hospitalizada", "persona_fallecida"):
        return True
    st = normalizar(rec.get("status"))
    return any(k in st for k in (_FALLECIDA | _CON_NOVEDAD))


def _ubicacion(rec: dict) -> str | None:
    """Enlaces directos a la ubicación GPS (Google Maps + Street View), si hay coords."""
    lat, lng = rec.get("latitude"), rec.get("longitude")
    if lat is None or lng is None:
        return None
    return (
        "🗺️ Google Maps: https://www.google.com/maps/search/?api=1&query=%s,%s\n"
        "🧍 Street View: https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=%s,%s"
        % (lat, lng, lat, lng)
    )


def formato_resultado(res: dict) -> str:
    """Formatea un resultado de búsqueda (/buscar)."""
    rec = res.get("record", res)
    nombre = rec.get("title") or rec.get("person_name") or "Sin nombre"
    partes = ["*%s*" % nombre]
    tipo = TIPO_LEGIBLE.get(rec.get("record_type"), rec.get("record_type") or "")
    if tipo:
        partes.append(tipo)
    lugar = _lugar(rec)
    if lugar:
        partes.append("📍 %s" % lugar)
    ubic = _ubicacion(rec)
    if ubic:
        partes.append(ubic)
    if rec.get("age") is not None:
        partes.append("Edad aprox: %s" % rec["age"])
    if rec.get("status"):
        partes.append("Estado: %s" % rec["status"])
    partes.append("Fuente: %s" % (rec.get("source_name") or rec.get("source_id") or "—"))
    also = res.get("also_in_count") or 0
    if also:
        partes.append("También aparece en %s fuente(s) más" % also)
    return "\n".join(partes)


def formato_alerta(rec: dict) -> str:
    """Formatea un aviso de alerta, con trato compasivo en casos delicados."""
    nombre = rec.get("title") or rec.get("person_name") or "la persona que buscas"
    fuente = rec.get("source_name") or rec.get("source_id") or "la fuente original"
    if es_sensible(rec):
        return (
            "🕊️ Encontramos un registro que *podría* coincidir con *%s*, en una fuente "
            "que maneja información delicada.\n\n"
            "Por respeto, no podemos confirmarlo automáticamente. Por favor comunícate "
            "directamente con %s para recibir información verificada.\n\n"
            "Lamentamos profundamente este momento y te acompañamos." % (nombre, fuente)
        )
    lugar = _lugar(rec)
    detalle = "\n\n" + formato_resultado({"record": rec})
    return (
        "🔔 Posible novedad sobre *%s*.%s\n\n"
        "⚠️ Verifica directamente con %s antes de actuar; puede haber personas con el "
        "mismo nombre." % (nombre, detalle, ("el lugar indicado" if lugar else fuente))
    )
