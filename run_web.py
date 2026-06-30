"""Punto de entrada combinado: corre la web (uvicorn) Y el bot de Telegram en un
hilo, en la MISMA máquina. Así no hace falta una máquina extra para el bot
(opción gratuita dentro del plan trial de Fly).

El bot solo arranca si existe TELEGRAM_BOT_TOKEN. Si no, corre solo la web.
"""

from __future__ import annotations

import os
import threading


def _run_bot() -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        print("[run_web] sin TELEGRAM_BOT_TOKEN: el bot no arranca (solo web).")
        return
    # El bot consulta la web local y guarda alertas en el volumen.
    os.environ.setdefault("REDAYUDA_API", "http://127.0.0.1:8000")
    os.environ.setdefault("ALERTAS_DB", "/data/alertas.json")
    os.environ["BOT_EMBEDDED"] = "1"  # no levantar servidor de salud propio
    try:
        from integraciones.telegram_buscador.bot import main as bot_main
        print("[run_web] arrancando bot de Telegram (embebido)...")
        bot_main()
    except Exception as exc:  # noqa: BLE001 - el bot no debe tumbar la web
        print("[run_web] el bot terminó:", repr(exc))


def main() -> None:
    # El bot en un hilo demonio; la web en el hilo principal.
    threading.Thread(target=_run_bot, daemon=True).start()
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))


if __name__ == "__main__":
    main()
