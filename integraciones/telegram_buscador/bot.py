"""Bot de Telegram: búsqueda y alertas sobre el índice de redayuda.

Long-polling con la API de Telegram usando solo stdlib (urllib). Configuración
por variables de entorno:

  TELEGRAM_BOT_TOKEN   token del bot (obligatorio)
  REDAYUDA_API         base del índice (def: http://127.0.0.1:8000)
  ALERTAS_DB           ruta del JSON de suscripciones (def: alertas.json)

Comandos:
  /start, /ayuda            ayuda
  /buscar <nombre>          busca a una persona en todas las fuentes
  /alerta <nombre>          te avisa cuando aparezca (viva, herida, en necesidad o fallecida)
  /misalertas               lista tus alertas
  /quitar <nombre>          elimina una alerta

Nota de Telegram: el bot no puede escribir primero a un desconocido; la persona
debe iniciar el chat (/start) o crear una alerta una vez. A partir de ahí, el
bot ya puede avisarle.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

from . import alertas, cliente, formato

API = "https://api.telegram.org/bot%s/%s"
INTERVALO_FEED = 60  # segundos entre revisiones del feed para alertas

AYUDA = (
    "🇻🇪 *Red Rescate Venezuela* — búsqueda de personas tras los terremotos.\n\n"
    "Comandos:\n"
    "• `/buscar Nombre Apellido` — busca en todas las fuentes\n"
    "• `/alerta Nombre Apellido` — te aviso si aparece (viva, herida, en necesidad o fallecida)\n"
    "• `/misalertas` — tus alertas activas\n"
    "• `/quitar Nombre Apellido` — eliminar una alerta\n\n"
    "_Esta herramienta es gratuita y sin fines de lucro. La información puede contener "
    "errores; verifica siempre con el hospital o la fuente._"
)


def _api(token: str, method: str, params: dict, timeout: int = 35) -> dict:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(API % (token, method), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def enviar(token: str, chat_id, texto: str) -> None:
    try:
        _api(token, "sendMessage", {
            "chat_id": chat_id,
            "text": texto,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true",
        })
    except Exception:
        # Si el Markdown rompe el parseo (400), reintenta en texto plano.
        try:
            _api(token, "sendMessage", {
                "chat_id": chat_id,
                "text": texto,
                "disable_web_page_preview": "true",
            })
        except Exception:
            pass


def _arg(texto: str, comando: str) -> str:
    return texto[len(comando):].strip()


def manejar_update(token, base, estado, ruta_estado, update) -> None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    texto = (msg.get("text") or "").strip()

    if texto.startswith(("/start", "/ayuda", "/help")):
        enviar(token, chat_id, AYUDA)
    elif texto.startswith("/buscar"):
        q = _arg(texto, "/buscar")
        if not q:
            enviar(token, chat_id, "Escribe: `/buscar Nombre Apellido`")
            return
        try:
            res = cliente.buscar(base, q)
        except Exception:
            enviar(token, chat_id, "No pude consultar ahora. Intenta de nuevo en un momento.")
            return
        if not res:
            enviar(token, chat_id,
                   "No encontré coincidencias para “%s”. La información se actualiza; "
                   "puedes crear una alerta: `/alerta %s`" % (q, q))
            return
        cuerpo = "\n\n".join(formato.formato_resultado(r) for r in res[:5])
        enviar(token, chat_id,
               "Resultados para “%s”:\n\n%s\n\n⚠️ Verifica siempre con el hospital o la "
               "fuente antes de actuar." % (q, cuerpo))
    elif texto.startswith("/alerta"):
        q = _arg(texto, "/alerta")
        if not q:
            enviar(token, chat_id, "Escribe: `/alerta Nombre Apellido`")
            return
        alertas.suscribir(estado, chat_id, q)
        alertas.guardar(ruta_estado, estado)
        enviar(token, chat_id,
               "🔔 Listo. Te avisaré si aparece “%s” en cualquier fuente. "
               "Para quitarla: `/quitar %s`" % (q, q))
    elif texto.startswith("/misalertas"):
        ms = alertas.mias(estado, chat_id)
        if ms:
            enviar(token, chat_id, "Tus alertas:\n" + "\n".join("• " + m for m in ms))
        else:
            enviar(token, chat_id, "No tienes alertas. Crea una con `/alerta Nombre Apellido`.")
    elif texto.startswith("/quitar"):
        q = _arg(texto, "/quitar")
        alertas.quitar(estado, chat_id, q)
        alertas.guardar(ruta_estado, estado)
        enviar(token, chat_id, "Quité la alerta de “%s”." % q)
    else:
        enviar(token, chat_id, AYUDA)


def revisar_alertas(token, base, estado, ruta_estado) -> dict:
    try:
        payload = cliente.feed(base, estado.get("cursor", 0))
    except Exception:
        return estado
    avisos, estado = alertas.revisar(estado, payload)
    for chat_id, rec in avisos:
        try:
            enviar(token, chat_id, formato.formato_alerta(rec))
        except Exception:
            pass  # un envío fallido no debe frenar el resto
    alertas.guardar(ruta_estado, estado)
    return estado


def _servidor_salud(port: int) -> None:  # pragma: no cover - infra
    """Mini servidor HTTP para que el host (Fly) mantenga el worker siempre vivo."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *a):  # silencio
            pass

    srv = HTTPServer(("0.0.0.0", port), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main() -> None:  # pragma: no cover - bucle de red, se prueba por partes
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    base = os.environ.get("REDAYUDA_API", "http://127.0.0.1:8000")
    ruta_estado = os.environ.get("ALERTAS_DB", "alertas.json")
    # Si va embebido en la web (misma máquina), no levanta su propio servidor de salud.
    if not os.environ.get("BOT_EMBEDDED"):
        _servidor_salud(int(os.environ.get("PORT", "8080")))
    estado = alertas.cargar(ruta_estado)
    offset = 0
    ultimo_feed = 0.0
    print("Bot en marcha. Índice: %s" % base)
    while True:
        try:
            data = _api(token, "getUpdates", {"offset": offset, "timeout": 30})
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                manejar_update(token, base, estado, ruta_estado, upd)
            if time.time() - ultimo_feed > INTERVALO_FEED:
                estado = revisar_alertas(token, base, estado, ruta_estado)
                ultimo_feed = time.time()
        except Exception:
            time.sleep(5)


if __name__ == "__main__":  # pragma: no cover
    main()
