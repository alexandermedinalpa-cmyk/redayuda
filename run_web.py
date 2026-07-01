"""Punto de entrada: corre la web de redayuda Y el bot de Telegram por WEBHOOK,
en la misma máquina y sin depender de que esté siempre encendida.

Por qué webhook y no polling: en el plan gratuito la máquina se duerme por
inactividad. Con webhook, CADA mensaje de Telegram llega como un POST que
despierta la máquina y se procesa al instante. El polling solo recibe mientras
la máquina está despierta.

Expone `app` (la app de redayuda + la ruta del webhook + cabeceras de seguridad).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import threading
import time

from app.main import app  # la app FastAPI de redayuda (no se modifica su código)


# --- Cabeceras de seguridad (aditivo, no toca el código de redayuda) ---
@app.middleware("http")
async def _cabeceras_seguridad(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
    return resp


_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if _TOKEN:
    from fastapi import Request

    from integraciones.telegram_buscador import alertas
    from integraciones.telegram_buscador import bot as tg

    _BASE = "http://127.0.0.1:8000"  # la web local, misma máquina
    _RUTA = os.environ.get("ALERTAS_DB", "/data/alertas.json")
    _PUBLICA = os.environ.get("PUBLIC_URL", "https://red-rescate-venezuela.fly.dev")
    # Secreto del webhook: independiente del token si se define TG_WEBHOOK_SECRET;
    # si no, se deriva del token (funciona sin configurar nada extra).
    _SECRET = os.environ.get("TG_WEBHOOK_SECRET") or hashlib.sha256(_TOKEN.encode()).hexdigest()[:40]

    _LOCK = threading.Lock()  # serializa la mutación del estado de alertas
    _estado = {"e": alertas.cargar(_RUTA), "ultimo_feed": 0.0}

    @app.post("/tg/webhook", include_in_schema=False)
    async def _tg_webhook(request: Request):
        # Verificación en tiempo constante de que el POST viene de Telegram.
        recibido = request.headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(recibido, _SECRET):
            return {"ok": False}
        try:
            update = await request.json()
        except Exception as exc:
            print("[tg] webhook con cuerpo ilegible:", repr(exc), flush=True)
            return {"ok": True}

        def _manejar():
            with _LOCK:  # evita corrupción/carrera del archivo de suscripciones
                tg.manejar_update(_TOKEN, _BASE, _estado["e"], _RUTA, update)

        try:
            await asyncio.to_thread(_manejar)
        except Exception as exc:  # noqa: BLE001
            print("[tg] error manejando update:", repr(exc), flush=True)

        # Alertas oportunistas: cada vez que la máquina está despierta (máx 1/min).
        if time.time() - _estado["ultimo_feed"] > 60:
            def _revisar():
                with _LOCK:
                    _estado["e"] = tg.revisar_alertas(_TOKEN, _BASE, _estado["e"], _RUTA)
            try:
                await asyncio.to_thread(_revisar)
            except Exception as exc:  # noqa: BLE001
                print("[tg] error revisando alertas:", repr(exc), flush=True)
            _estado["ultimo_feed"] = time.time()
        return {"ok": True}

    def _configurar_webhook():
        # A nivel de módulo (redayuda usa lifespan → FastAPI ignora on_event).
        url = _PUBLICA.rstrip("/") + "/tg/webhook"
        for intento in range(3):
            try:
                tg._api(_TOKEN, "setWebhook", {
                    "url": url,
                    "secret_token": _SECRET,
                    # NO descartar el backlog en cada arranque: si alguien mandó
                    # /urgente durante un redeploy, no debe perderse.
                    "drop_pending_updates": "false",
                    "allowed_updates": '["message","edited_message"]',
                })
                info = tg._api(_TOKEN, "getWebhookInfo", {})
                if (info.get("result") or {}).get("url") == url:
                    print("[tg] webhook OK en", url, flush=True)
                    return
                print("[tg] webhook no coincide, reintento", flush=True)
            except Exception as exc:  # noqa: BLE001
                print("[tg] setWebhook intento %d falló: %r" % (intento + 1, exc), flush=True)
            time.sleep(3 * (intento + 1))
        print("[tg] setWebhook: no verificado tras varios intentos (¡bot podría no recibir!)", flush=True)

    threading.Thread(target=_configurar_webhook, daemon=True).start()
else:
    print("[run_web] sin TELEGRAM_BOT_TOKEN: solo web (bot desactivado).", flush=True)
