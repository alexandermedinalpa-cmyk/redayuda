"""Cliente de Evolution API para ENVIAR mensajes de WhatsApp.

POST {EVOLUTION_API_URL}/message/sendText/{instance}
  headers: apikey
  body: {number, text, options:{delay, presence}}

`post` es inyectable para testear sin red. El envío incluye un pequeño delay y
presencia "composing" (ritmo humano), parte de la disciplina anti-baneo.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable

# post(url, headers, body_dict) -> (status, texto)
Post = Callable[[str, dict, dict], tuple]


def _http_post(url: str, headers: dict, body: dict) -> tuple:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={**headers, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", "replace")


class Evolution:
    def __init__(self, base: str | None = None, api_key: str | None = None,
                 instance: str | None = None, post: Post | None = None):
        self.base = (base or os.environ.get("EVOLUTION_API_URL", "http://localhost:8080")).rstrip("/")
        self.api_key = api_key or os.environ.get("EVOLUTION_API_KEY", "")
        self.instance = instance or os.environ.get("EVOLUTION_INSTANCE", "red-rescate")
        self._post = post or _http_post

    def enviar_texto(self, numero: str, texto: str, *, delay_ms: int = 1200) -> tuple:
        """Envía un texto. `numero` en E.164 sin '+'."""
        url = "%s/message/sendText/%s" % (self.base, self.instance)
        body = {
            "number": numero,
            "text": texto,
            "options": {"delay": delay_ms, "presence": "composing"},
        }
        return self._post(url, {"apikey": self.api_key}, body)
