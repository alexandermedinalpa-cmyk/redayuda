"""Parseo del webhook entrante de Evolution API (evento messages.upsert).

Incorpora los filtros críticos aprendidos de un proyecto WhatsApp real para no
responder donde no se debe (grupos, difusión, estado) ni entrar en bucles.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass
class Entrante:
    numero: str   # E.164 SIN '+', p. ej. "584120000000"
    texto: str
    nombre: str | None = None


def _reparar_mojibake(texto: str) -> str:
    """Repara latin1→utf8 y normaliza (mismo criterio que el proyecto real)."""
    if not texto:
        return ""
    try:
        # Marcadores típicos de mojibake (Ã, Â seguidos de bytes altos).
        if any(m in texto for m in ("Ã", "Â")):
            reparado = texto.encode("latin1", "ignore").decode("utf8", "ignore")
            if "�" not in reparado:
                texto = reparado
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    try:
        texto = unicodedata.normalize("NFC", texto)
    except (TypeError, ValueError):
        pass
    return texto


def parse_incoming(payload: dict) -> Entrante | None:
    """Devuelve un Entrante para mensajes de texto 1-a-1, o None si hay que ignorar.

    Ignora: eventos que no son messages.upsert, mensajes propios (fromMe),
    grupos (@g.us), difusión/estado (@broadcast), canales (@newsletter), jids no
    individuales y mensajes sin texto.
    """
    if not isinstance(payload, dict):
        return None
    evento = (payload.get("event") or "").lower().replace("_", ".")
    if evento != "messages.upsert":
        return None

    data = payload.get("data") or {}
    key = data.get("key") or {}

    if key.get("fromMe") is True:
        return None

    jid = key.get("remoteJid")
    if not jid or not isinstance(jid, str):
        return None
    if jid.endswith(("@broadcast", "@g.us", "@newsletter")):
        return None
    if not jid.endswith("@s.whatsapp.net"):
        return None

    numero = jid.split("@", 1)[0]
    if not numero.isdigit():
        return None

    message = data.get("message") or {}
    texto = ""
    if message.get("conversation"):
        texto = message["conversation"]
    elif isinstance(message.get("extendedTextMessage"), dict):
        texto = message["extendedTextMessage"].get("text") or ""
    texto = _reparar_mojibake(texto).strip()
    if not texto:
        return None

    nombre = data.get("pushName") or None
    return Entrante(numero=numero, texto=texto, nombre=nombre)
