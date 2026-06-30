"""Tests del parser del webhook (los filtros anti-baneo) y del cliente Evolution."""

from integraciones.whatsapp_buscador import webhook
from integraciones.whatsapp_buscador.evolution import Evolution


def _upsert(jid, texto, from_me=False, tipo="conversation"):
    msg = {"conversation": texto} if tipo == "conversation" else {"extendedTextMessage": {"text": texto}}
    return {"event": "messages.upsert",
            "data": {"key": {"remoteJid": jid, "fromMe": from_me}, "message": msg, "pushName": "Juan"}}


def test_parsea_mensaje_individual():
    e = webhook.parse_incoming(_upsert("584120000000@s.whatsapp.net", "Hola"))
    assert e is not None
    assert e.numero == "584120000000"  # E.164 sin '+'
    assert e.texto == "Hola"
    assert e.nombre == "Juan"


def test_extended_text_tambien_funciona():
    e = webhook.parse_incoming(_upsert("584120000000@s.whatsapp.net", "Busco a José", tipo="ext"))
    assert e is not None and e.texto == "Busco a José"


def test_ignora_propios_grupos_difusion_y_canales():
    assert webhook.parse_incoming(_upsert("584120000000@s.whatsapp.net", "x", from_me=True)) is None
    assert webhook.parse_incoming(_upsert("123456@g.us", "x")) is None
    assert webhook.parse_incoming(_upsert("status@broadcast", "x")) is None
    assert webhook.parse_incoming(_upsert("123@newsletter", "x")) is None


def test_ignora_jid_no_individual_y_sin_texto():
    assert webhook.parse_incoming(_upsert("584120000000@lid", "x")) is None  # no @s.whatsapp.net
    assert webhook.parse_incoming(_upsert("584120000000@s.whatsapp.net", "")) is None


def test_ignora_eventos_que_no_son_mensajes():
    assert webhook.parse_incoming({"event": "connection.update", "data": {}}) is None
    assert webhook.parse_incoming({}) is None


def test_repara_mojibake():
    # "JosÃ©" (latin1 mal interpretado) -> "José"
    e = webhook.parse_incoming(_upsert("584120000000@s.whatsapp.net", "JosÃ©"))
    assert e is not None
    assert "é" in e.texto


def test_evolution_arma_la_peticion():
    capturado = {}
    def post(url, headers, body):
        capturado.update(url=url, headers=headers, body=body)
        return 200, "{}"
    evo = Evolution(base="http://x", api_key="K", instance="inst", post=post)
    evo.enviar_texto("584120000000", "Hola")
    assert capturado["url"] == "http://x/message/sendText/inst"
    assert capturado["headers"]["apikey"] == "K"
    assert capturado["body"]["number"] == "584120000000"
    assert capturado["body"]["text"] == "Hola"
    assert capturado["body"]["options"]["presence"] == "composing"
