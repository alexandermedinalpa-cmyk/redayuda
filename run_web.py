"""Punto de entrada: corre la web de redayuda Y el bot de Telegram por WEBHOOK,
en la misma máquina y sin depender de que esté siempre encendida.

Por qué webhook y no polling: en el plan gratuito la máquina se duerme por
inactividad. Con webhook, CADA mensaje de Telegram llega como un POST que
despierta la máquina y se procesa al instante (nada se pierde). El polling, en
cambio, solo recibe mientras la máquina está despierta.

Expone `app` (la app de redayuda + la ruta del webhook) para uvicorn.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time

from app.main import app  # la app FastAPI de redayuda (no se modifica su código)

_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if _TOKEN:
    from fastapi import Request

    from integraciones.telegram_buscador import alertas
    from integraciones.telegram_buscador import bot as tg

    _BASE = "http://127.0.0.1:8000"  # la web local, misma máquina
    _RUTA = os.environ.get("ALERTAS_DB", "/data/alertas.json")
    _PUBLICA = os.environ.get("PUBLIC_URL", "https://red-rescate-venezuela.fly.dev")
    _SECRET = hashlib.sha256(_TOKEN.encode()).hexdigest()[:40]  # valida que el POST venga de Telegram

    _estado = {"e": alertas.cargar(_RUTA), "ultimo_feed": 0.0}

    @app.post("/tg/webhook", include_in_schema=False)
    async def _tg_webhook(request: Request):
        # Solo Telegram conoce este secreto (lo fijamos en setWebhook).
        if request.headers.get("x-telegram-bot-api-secret-token") != _SECRET:
            return {"ok": False}
        try:
            update = await request.json()
        except Exception:
            return {"ok": True}
        # manejar_update hace llamadas HTTP bloqueantes -> a un hilo para no frenar el loop.
        try:
            await asyncio.to_thread(tg.manejar_update, _TOKEN, _BASE, _estado["e"], _RUTA, update)
        except Exception as exc:  # noqa: BLE001
            print("[tg] error manejando update:", repr(exc))
        # Alertas oportunistas: cada vez que la máquina está despierta, revisa el feed (máx 1/min).
        if time.time() - _estado["ultimo_feed"] > 60:
            try:
                _estado["e"] = await asyncio.to_thread(
                    tg.revisar_alertas, _TOKEN, _BASE, _estado["e"], _RUTA
                )
            except Exception as exc:  # noqa: BLE001
                print("[tg] error revisando alertas:", repr(exc))
            _estado["ultimo_feed"] = time.time()
        return {"ok": True}

    import threading

    def _configurar_webhook():
        # A nivel de módulo (no on_event): redayuda usa lifespan y FastAPI ignora
        # los handlers on_event("startup"). setWebhook solo registra la URL en
        # Telegram; no necesita que el servidor local ya esté sirviendo.
        url = _PUBLICA.rstrip("/") + "/tg/webhook"
        try:
            tg._api(_TOKEN, "setWebhook", {
                "url": url,
                "secret_token": _SECRET,
                "drop_pending_updates": "true",  # limpia backlog al cambiar a webhook
                "allowed_updates": '["message","edited_message"]',
            })
            print("[tg] webhook configurado en", url)
        except Exception as exc:  # noqa: BLE001
            print("[tg] setWebhook falló:", repr(exc))

    threading.Thread(target=_configurar_webhook, daemon=True).start()
else:
    print("[run_web] sin TELEGRAM_BOT_TOKEN: solo web (bot desactivado).")
