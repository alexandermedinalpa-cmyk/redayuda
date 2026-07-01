"""App webhook de WhatsApp (FastAPI) que reutiliza la lógica del bot de Telegram.

Recibe el webhook de Evolution API, decide la respuesta y la envía por WhatsApp.
La función `responder()` es pura (sin HTTP) para poder testearla.
"""

from __future__ import annotations

import os

from ..telegram_buscador import alertas, cliente, formato
from .evolution import Evolution
from .webhook import parse_incoming

AYUDA = (
    "🇻🇪 *Red Rescate Venezuela* — búsqueda de personas tras los terremotos.\n\n"
    "• Escribe un *nombre* para buscarlo en todas las fuentes.\n"
    "• `alerta Nombre Apellido` — te aviso si aparece (vivo, herido, en necesidad o fallecido).\n"
    "• `mis alertas` — ver tus alertas · `quitar Nombre` — eliminar una.\n\n"
    "_Gratuito y sin fines de lucro. Verifica siempre con el hospital o la fuente._"
)


def _arg(texto: str) -> str:
    partes = texto.split(None, 1)
    return partes[1].strip() if len(partes) > 1 else ""


def responder(texto: str, numero: str, estado: dict, base: str, *, fetch=None) -> str:
    """Devuelve el texto de respuesta. Puede mutar `estado` (alertas)."""
    t = texto.strip()
    low = t.lower()

    if low in ("hola", "buenas", "ayuda", "help", "menu", "menú", "/start", "/ayuda"):
        return AYUDA
    if low.startswith(("alerta", "/alerta")):
        q = _arg(t)
        if not q:
            return "Escribe: *alerta Nombre Apellido*"
        alertas.suscribir(estado, numero, q)
        return "🔔 Listo. Te avisaré si aparece “%s”. Para quitarla: *quitar %s*" % (q, q)
    if low.startswith(("quitar", "/quitar")):
        q = _arg(t)
        alertas.quitar(estado, numero, q)
        return "Quité la alerta de “%s”." % q
    if low in ("mis alertas", "misalertas", "/misalertas"):
        ms = alertas.mias(estado, numero)
        if ms:
            return "Tus alertas:\n" + "\n".join("• " + m for m in ms)
        return "No tienes alertas. Crea una con: *alerta Nombre Apellido*"

    # Por defecto: buscar el texto como nombre (lo natural en WhatsApp).
    q = _arg(t) if low.startswith(("buscar", "/buscar")) else t
    if not q:
        return AYUDA
    try:
        res = cliente.buscar(base, q, fetch=fetch)
    except Exception:
        return "No pude consultar ahora. Intenta de nuevo en un momento."
    if not res:
        return ("No encontré coincidencias para “%s”. La información se actualiza; "
                "puedes crear una alerta: *alerta %s*" % (q, q))
    cuerpo = "\n\n".join(formato.formato_resultado(r) for r in res[:5])
    return ("Resultados para “%s”:\n\n%s\n\n⚠️ Verifica con el hospital o la fuente "
            "antes de actuar." % (q, cuerpo))


def crear_app():  # pragma: no cover - integración FastAPI
    import hmac

    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    base = os.environ.get("REDAYUDA_API", "http://127.0.0.1:8000")
    ruta = os.environ.get("ALERTAS_DB", "/data/alertas_wa.json")
    # Secreto para autenticar que el webhook viene de Evolution (header Authorization).
    webhook_secret = os.environ.get("EVOLUTION_WEBHOOK_SECRET", "")
    evo = Evolution()
    app = FastAPI(title="Red Rescate Venezuela — WhatsApp")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/webhook/whatsapp")
    async def webhook(request: Request):
        # Si hay secreto configurado, exige que Evolution lo envíe (anti-spoofing).
        if webhook_secret:
            recibido = request.headers.get("authorization", "")
            if not hmac.compare_digest(recibido, webhook_secret):
                return JSONResponse(status_code=401, content={"ok": False})
        try:
            payload = await request.json()
        except Exception as exc:
            print("[wa] webhook con cuerpo ilegible:", repr(exc), flush=True)
            return {"ok": True, "skipped": "bad json"}
        ent = parse_incoming(payload)
        if ent is None:
            return {"ok": True, "skipped": "ignored"}
        estado = alertas.cargar(ruta)
        reply = responder(ent.texto, ent.numero, estado, base)
        alertas.guardar(ruta, estado)
        try:
            evo.enviar_texto(ent.numero, reply)
        except Exception as exc:
            # Loggea y devuelve 502 para que Evolution reintente la entrega.
            print("[wa] envío falló a %s (%r): %r" % (ent.numero, reply[:60], exc), flush=True)
            return JSONResponse(status_code=502, content={"ok": False, "error": "send_failed"})
        return {"ok": True}

    return app


# Punto de entrada para uvicorn (None si FastAPI no está disponible, p. ej. en tests
# que solo prueban `responder`).
try:  # pragma: no cover
    app = crear_app()
except Exception as _exc:  # pragma: no cover
    print("[wa] no se pudo crear la app:", repr(_exc), flush=True)
    app = None
