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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import alertas, cliente, formato

API = "https://api.telegram.org/bot%s/%s"
INTERVALO_FEED = 60  # segundos entre revisiones del feed para alertas

AYUDA = (
    "🇻🇪 *Red Rescate Venezuela* — búsqueda de personas tras los terremotos.\n\n"
    "🆘 *EMERGENCIA — persona con vida atrapada:*\n"
    "• `/urgente [dirección] · [cuántas personas] · [teléfono]`\n"
    "  luego 📎 comparte tu *ubicación GPS* y 📷 envía *fotos del lugar*.\n"
    "  → alerta inmediata a los rescatistas (con fecha y hora).\n\n"
    "🔎 *Buscar y avisos:*\n"
    "• `/buscar Nombre Apellido` — busca en todas las fuentes\n"
    "• `/alerta Nombre Apellido` — te aviso si aparece (viva, herida, en necesidad o fallecida)\n"
    "• `/misalertas` — tus alertas activas\n"
    "• `/quitar Nombre Apellido` — eliminar una alerta\n\n"
    "_Gratuita y sin fines de lucro. La información puede contener errores; verifica siempre "
    "con el hospital, la fuente o emergencias._"
)


def _api(token: str, method: str, params: dict, timeout: int = 35) -> dict:
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(API % (token, method), data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _leer_cuerpo(e) -> str:
    try:
        return e.read().decode("utf-8", "replace")
    except Exception:
        return ""


def enviar(token: str, chat_id, texto: str) -> bool:
    """Envía un mensaje. Devuelve True si se entregó; loggea TODOS los fallos
    (antes se tragaban en silencio y podíamos perder alertas sin enterarnos)."""
    def _send(markdown: bool):
        params = {"chat_id": chat_id, "text": texto, "disable_web_page_preview": "true"}
        if markdown:
            params["parse_mode"] = "Markdown"
        _api(token, "sendMessage", params)

    try:
        _send(True)
        return True
    except urllib.error.HTTPError as e:
        cuerpo = _leer_cuerpo(e)
        # Solo reintenta en texto plano si el fallo es de PARSEO de Markdown.
        if e.code == 400 and "parse" in cuerpo.lower():
            try:
                _send(False)
                return True
            except Exception as e2:
                print("[bot] envío falló (plano) chat=%s: %r" % (chat_id, e2), flush=True)
                return False
        print("[bot] envío falló chat=%s HTTP %s %s" % (chat_id, e.code, cuerpo[:120]), flush=True)
        return False
    except Exception as e:
        print("[bot] envío falló chat=%s: %r" % (chat_id, e), flush=True)
        return False


def enviar_foto(token: str, chat_id, file_id: str, caption: str = "") -> bool:
    """Reenvía una foto (por file_id) a un chat/canal. Devuelve True si se entregó."""
    try:
        _api(token, "sendPhoto", {"chat_id": chat_id, "photo": file_id, "caption": caption[:1000]})
        return True
    except Exception as e:
        print("[bot] envío de foto falló chat=%s: %r" % (chat_id, e), flush=True)
        return False


# --- Utilidades para el reporte de urgencia (anti-abuso / anti-inyección) ---
_URGENTE_HIST: dict = {}
_URGENTE_SESION: dict = {}  # chat_id -> timestamp: ventana para adjuntar foto/ubicación tras /urgente
_MD_CHARS = re.compile(r"[*_`\[\]()~>#+=|{}]")


def _ahora_ve() -> str:
    """Fecha y hora en horario de Venezuela (UTC-4)."""
    return (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")


def _foto_id(msg: dict):
    """file_id de la foto de mayor resolución del mensaje, si hay."""
    fotos = msg.get("photo") or []
    return fotos[-1]["file_id"] if fotos else None


def _rate_urgente_ok(chat_id, ahora: float, ventana: float = 600, tope: int = 3) -> bool:
    h = [t for t in _URGENTE_HIST.get(chat_id, []) if ahora - t < ventana]
    if len(h) >= tope:
        _URGENTE_HIST[chat_id] = h
        return False
    h.append(ahora)
    _URGENTE_HIST[chat_id] = h
    return True


def _sanit(s, limite: int) -> str:
    return _MD_CHARS.sub(" ", str(s or "")).strip()[:limite]


def _coord_valida(v, rango: float):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if -rango <= f <= rango else None


def _arg(texto: str, comando: str) -> str:
    return texto[len(comando):].strip()


def manejar_update(token, base, estado, ruta_estado, update) -> None:
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    texto = (msg.get("text") or "").strip()
    caption = (msg.get("caption") or "").strip()

    # /urgente puede venir como texto, o como pie de foto (foto + descripción juntas).
    if texto.startswith("/urgente") or caption.startswith("/urgente"):
        _reportar_urgencia(token, chat_id, msg)
        return
    # Foto o ubicación tras un /urgente reciente: se adjuntan a ese reporte.
    if (msg.get("photo") or msg.get("location")) and _sesion_urgente_activa(chat_id):
        _adjuntar_urgencia(token, chat_id, msg)
        return

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


def _sesion_urgente_activa(chat_id, ventana: float = 900) -> bool:
    """True si el usuario hizo /urgente en los últimos ~15 min (para adjuntar foto/ubicación)."""
    ts = _URGENTE_SESION.get(chat_id)
    return ts is not None and (time.time() - ts) < ventana


def _reportar_urgencia(token, chat_id, msg) -> None:
    """🆘 Reporte de persona con vida atrapada -> alerta inmediata al canal de rescate.

    Captura lo que piden los rescatistas: ubicación (GPS o escrita), foto del lugar,
    contacto, y fecha/hora (automática). Foto/ubicación extra se adjuntan después
    (ventana de sesión). Texto sanitizado + plano (anti-inyección).
    """
    canal = os.environ.get("RESCATE_CANAL", "")
    fuente_texto = (msg.get("text") or "") or (msg.get("caption") or "")
    desc = _sanit(_arg(fuente_texto, "/urgente"), 500)
    loc = msg.get("location") or {}
    la = _coord_valida(loc.get("latitude"), 90)
    lo = _coord_valida(loc.get("longitude"), 180)
    foto = _foto_id(msg)

    if not canal:
        enviar(token, chat_id, "El canal de rescate aún no está configurado. Avisa al equipo.")
        return
    if not desc and la is None and not foto:
        enviar(token, chat_id,
               "🆘 *Reportar persona con vida atrapada*\n\n"
               "Envía en un mensaje:\n"
               "`/urgente [dirección exacta] · [cuántas personas] · [teléfono de contacto]`\n\n"
               "Y luego, para el rescate:\n"
               "• 📎 comparte la *ubicación GPS* (clip → Ubicación)\n"
               "• 📷 envía *fotos del lugar*\n"
               "_(La fecha y hora se añaden solas.)_")
        return
    if not _rate_urgente_ok(chat_id, time.time()):
        enviar(token, chat_id,
               "Ya enviaste varios reportes; los equipos de rescate los están viendo. "
               "Si es una emergencia distinta, espera unos minutos.")
        return

    quien = _sanit((msg.get("from") or {}).get("first_name"), 40) or "anónimo"
    partes = [
        "🆘 URGENTE — Posible persona con vida atrapada",
        "🕐 %s (hora Venezuela)" % _ahora_ve(),
    ]
    if desc:
        partes.append(desc)
    if la is not None and lo is not None:
        partes.append("📍 GPS: https://www.google.com/maps/search/?api=1&query=%.6f,%.6f" % (la, lo))
    partes.append("Reportado por %s vía @red_ayuda_bot. Verifiquen y actúen de inmediato." % quien)
    mensaje = "\n\n".join(partes)

    try:
        if foto:
            _api(token, "sendPhoto", {"chat_id": canal, "photo": foto, "caption": mensaje[:1000]})
        else:
            _api(token, "sendMessage", {
                "chat_id": canal, "text": mensaje, "disable_web_page_preview": "true"})
        _URGENTE_SESION[chat_id] = time.time()  # abre ventana para adjuntar foto/ubicación
        enviar(token, chat_id,
               "✅ Tu reporte urgente fue enviado a los equipos de rescate.\n"
               "Para ayudarlos, ahora puedes 📎 compartir tu *ubicación GPS* y 📷 enviar *fotos del lugar*.")
    except urllib.error.HTTPError as e:
        print("[urgente] fallo publicar en canal '%s': HTTP %s %s"
              % (canal, e.code, _leer_cuerpo(e)[:150]), flush=True)
        enviar(token, chat_id,
               "⚠️ No pude enviar el reporte al canal de rescate ahora. "
               "Por favor llama también a emergencias.")
    except Exception as e:
        print("[urgente] fallo publicar en canal '%s': %r" % (canal, e), flush=True)
        enviar(token, chat_id,
               "⚠️ No pude enviar el reporte al canal de rescate ahora. "
               "Por favor llama también a emergencias.")


def _adjuntar_urgencia(token, chat_id, msg) -> None:
    """Adjunta una foto o ubicación al reporte /urgente reciente (la relaya al canal)."""
    canal = os.environ.get("RESCATE_CANAL", "")
    if not canal:
        return
    quien = _sanit((msg.get("from") or {}).get("first_name"), 40) or "anónimo"
    foto = _foto_id(msg)
    loc = msg.get("location") or {}
    la = _coord_valida(loc.get("latitude"), 90)
    lo = _coord_valida(loc.get("longitude"), 180)
    ok = False
    if foto:
        ok = enviar_foto(token, canal, foto,
                         "📷 Foto del reporte urgente de %s — %s (hora VE)" % (quien, _ahora_ve()))
    elif la is not None and lo is not None:
        txt = ("📍 GPS del reporte urgente de %s — %s (hora VE)\n"
               "https://www.google.com/maps/search/?api=1&query=%.6f,%.6f" % (quien, _ahora_ve(), la, lo))
        try:
            _api(token, "sendMessage", {"chat_id": canal, "text": txt, "disable_web_page_preview": "true"})
            ok = True
        except Exception as e:
            print("[urgente] fallo adjuntar ubicación: %r" % e, flush=True)
    if ok:
        _URGENTE_SESION[chat_id] = time.time()  # refresca la ventana
        enviar(token, chat_id, "✅ Añadido a tu reporte de rescate. Gracias.")
    else:
        enviar(token, chat_id, "⚠️ No pude adjuntarlo al canal ahora. Intenta de nuevo.")


def revisar_alertas(token, base, estado, ruta_estado) -> dict:
    # DRENA el feed hasta agotarlo: si entran >200 registros en un intervalo, un
    # solo lote los perdería (has_more). Tope de páginas por seguridad.
    for _ in range(50):
        try:
            payload = cliente.feed(base, estado.get("cursor", 0))
        except Exception as e:
            print("[alertas] feed falló: %r" % e, flush=True)
            return estado
        avisos, estado = alertas.revisar(estado, payload)
        for chat_id, rec in avisos:
            try:
                entregado = enviar(token, chat_id, formato.formato_alerta(rec))
            except Exception as e:  # formato_alerta u otro fallo inesperado
                entregado = False
                print("[alertas] error preparando aviso chat=%s: %r" % (chat_id, e), flush=True)
            if not entregado:
                print("[alertas] aviso NO entregado chat=%s record=%s"
                      % (chat_id, rec.get("id")), flush=True)
        alertas.guardar(ruta_estado, estado)
        if not payload.get("has_more"):
            return estado
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
    # Descartar el backlog al arrancar: responder solo a mensajes NUEVOS, no a los
    # pendientes de antes (evita responder de nuevo tras cada reinicio/despliegue).
    try:
        prev = _api(token, "getUpdates", {"offset": -1, "timeout": 0}).get("result", [])
        if prev:
            offset = prev[-1]["update_id"] + 1
    except Exception:
        pass
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
