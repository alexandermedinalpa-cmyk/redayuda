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
    "• `/urgente [dirección] · [personas] · [teléfono]` + 📎 ubicación + 📷 fotos\n"
    "  → alerta inmediata a los rescatistas.\n\n"
    "📦 *PEDIR AYUDA / INSUMOS (desde el terreno):*\n"
    "• `/necesito [qué: palas, guantes, maquinaria, agua…] · [dónde] · [nombre y teléfono]`\n"
    "  luego 📎 ubicación GPS y 📷 fotos → va al canal de logística/donantes.\n\n"
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


# --- Utilidades para reportes de terreno (urgencia/necesidad): anti-abuso/inyección ---
_URGENTE_HIST: dict = {}
_REPORTE_SESION: dict = {}  # chat_id -> {ts, canal, etiqueta}: ventana para adjuntar foto/ubicación
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

    # Reportes de terreno: como texto o como pie de foto (foto + descripción juntas).
    if texto.startswith("/urgente") or caption.startswith("/urgente"):
        _reportar_urgencia(token, chat_id, msg)
        return
    if texto.startswith("/necesito") or caption.startswith("/necesito"):
        _reportar_necesidad(token, chat_id, msg)
        return
    # Foto o ubicación tras un reporte reciente: se adjuntan a ese reporte (su canal).
    if msg.get("photo") or msg.get("location"):
        sesion = _sesion_reporte_activa(chat_id)
        if sesion:
            _adjuntar_reporte(token, chat_id, msg, sesion)
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


def _sesion_reporte_activa(chat_id, ventana: float = 900):
    """Devuelve la sesión de reporte (canal/etiqueta) si el usuario hizo /urgente o
    /necesito en los últimos ~15 min (para adjuntar foto/ubicación), o None."""
    s = _REPORTE_SESION.get(chat_id)
    if s and (time.time() - s["ts"]) < ventana:
        return s
    return None


def _publicar_reporte(token, chat_id, msg, *, comando, canal, encabezado,
                      instrucciones, etiqueta) -> None:
    """Publica un reporte de terreno (urgencia o necesidad) en su canal, BIEN PUESTO:
    descripción sanitizada, foto, GPS y contacto, con fecha/hora automática. Deja una
    ventana para adjuntar foto/ubicación después. Texto plano (anti-inyección)."""
    fuente_texto = (msg.get("text") or "") or (msg.get("caption") or "")
    desc = _sanit(_arg(fuente_texto, comando), 600)
    loc = msg.get("location") or {}
    la = _coord_valida(loc.get("latitude"), 90)
    lo = _coord_valida(loc.get("longitude"), 180)
    foto = _foto_id(msg)

    if not canal:
        enviar(token, chat_id, "Ese canal aún no está configurado. Avisa al equipo.")
        return
    if not desc and la is None and not foto:
        enviar(token, chat_id, instrucciones)
        return
    if not _rate_urgente_ok(chat_id, time.time()):
        enviar(token, chat_id,
               "Ya enviaste varios reportes; los equipos los están viendo. "
               "Si es algo distinto, espera unos minutos.")
        return

    quien = _sanit((msg.get("from") or {}).get("first_name"), 40) or "anónimo"
    partes = [encabezado, "🕐 %s (hora Venezuela)" % _ahora_ve()]
    if desc:
        partes.append(desc)
    if la is not None and lo is not None:
        partes.append("📍 GPS: https://www.google.com/maps/search/?api=1&query=%.6f,%.6f" % (la, lo))
    partes.append("Reportado por %s vía @red_ayuda_bot." % quien)
    mensaje = "\n\n".join(partes)

    try:
        if foto:
            _api(token, "sendPhoto", {"chat_id": canal, "photo": foto, "caption": mensaje[:1000]})
        else:
            _api(token, "sendMessage", {
                "chat_id": canal, "text": mensaje, "disable_web_page_preview": "true"})
        _REPORTE_SESION[chat_id] = {"ts": time.time(), "canal": canal, "etiqueta": etiqueta}
        enviar(token, chat_id,
               "✅ Enviado (%s). Ahora puedes 📎 compartir tu *ubicación GPS* y 📷 enviar "
               "*fotos* para completarlo." % etiqueta)
    except urllib.error.HTTPError as e:
        print("[reporte] fallo publicar en '%s': HTTP %s %s"
              % (canal, e.code, _leer_cuerpo(e)[:150]), flush=True)
        enviar(token, chat_id, "⚠️ No pude enviarlo ahora. Intenta de nuevo o usa otro medio.")
    except Exception as e:
        print("[reporte] fallo publicar en '%s': %r" % (canal, e), flush=True)
        enviar(token, chat_id, "⚠️ No pude enviarlo ahora. Intenta de nuevo o usa otro medio.")


def _reportar_urgencia(token, chat_id, msg) -> None:
    """🆘 Persona con vida atrapada -> canal de rescate."""
    _publicar_reporte(
        token, chat_id, msg, comando="/urgente",
        canal=os.environ.get("RESCATE_CANAL", ""),
        encabezado="🆘 URGENTE — Posible persona con vida atrapada",
        instrucciones=("🆘 *Reportar persona con vida atrapada*\n\n"
                       "Envía: `/urgente [dirección exacta] · [cuántas personas] · [teléfono]`\n\n"
                       "Y luego 📎 comparte *ubicación GPS* y 📷 envía *fotos del lugar*."),
        etiqueta="reporte urgente")


def _reportar_necesidad(token, chat_id, msg) -> None:
    """📦 Solicitud de insumos/ayuda desde el terreno -> canal de necesidades."""
    _publicar_reporte(
        token, chat_id, msg, comando="/necesito",
        canal=os.environ.get("NECESIDADES_CANAL", ""),
        encabezado="📦 SOLICITUD DE AYUDA / INSUMOS",
        instrucciones=("📦 *Pedir ayuda o insumos desde el terreno*\n\n"
                       "Envía: `/necesito [qué necesitas: palas, guantes, maquinaria, agua…] · "
                       "[dónde] · [nombre y teléfono]`\n\n"
                       "Y luego 📎 comparte *ubicación GPS* y 📷 envía *fotos*."),
        etiqueta="solicitud de insumos")


def _adjuntar_reporte(token, chat_id, msg, sesion) -> None:
    """Adjunta foto/ubicación al reporte reciente (urgencia o necesidad), a su canal."""
    canal = sesion["canal"]
    etiqueta = sesion["etiqueta"]
    quien = _sanit((msg.get("from") or {}).get("first_name"), 40) or "anónimo"
    foto = _foto_id(msg)
    loc = msg.get("location") or {}
    la = _coord_valida(loc.get("latitude"), 90)
    lo = _coord_valida(loc.get("longitude"), 180)
    ok = False
    if foto:
        ok = enviar_foto(token, canal, foto,
                         "📷 Foto de la %s de %s — %s (hora VE)" % (etiqueta, quien, _ahora_ve()))
    elif la is not None and lo is not None:
        txt = ("📍 GPS de la %s de %s — %s (hora VE)\n"
               "https://www.google.com/maps/search/?api=1&query=%.6f,%.6f"
               % (etiqueta, quien, _ahora_ve(), la, lo))
        try:
            _api(token, "sendMessage", {"chat_id": canal, "text": txt, "disable_web_page_preview": "true"})
            ok = True
        except Exception as e:
            print("[reporte] fallo adjuntar ubicación: %r" % e, flush=True)
    if ok:
        _REPORTE_SESION[chat_id]["ts"] = time.time()  # refresca la ventana
        enviar(token, chat_id, "✅ Añadido a tu %s. Gracias." % etiqueta)
    else:
        enviar(token, chat_id, "⚠️ No pude adjuntarlo ahora. Intenta de nuevo.")


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
