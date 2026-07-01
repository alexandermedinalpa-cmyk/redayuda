"""Tests de las utilidades del reporte de urgencia (anti-inyección / anti-abuso)."""

from integraciones.telegram_buscador import bot


def test_sanit_quita_markdown_y_trunca():
    s = bot._sanit("hola *negrita* [link](http://x) `code`", 100)
    assert "*" not in s and "[" not in s and "`" not in s and "(" not in s
    assert "hola" in s and "negrita" in s
    assert len(bot._sanit("a" * 500, 40)) == 40


def test_coord_valida_rango():
    assert bot._coord_valida("10.5", 90) == 10.5
    assert bot._coord_valida(-66.9, 180) == -66.9
    assert bot._coord_valida("999", 90) is None   # fuera de rango
    assert bot._coord_valida("no-es-num", 90) is None
    assert bot._coord_valida(None, 90) is None


def test_rate_limit_urgente():
    bot._URGENTE_HIST.clear()
    ahora = 1000.0
    assert bot._rate_urgente_ok("u1", ahora) is True    # 1
    assert bot._rate_urgente_ok("u1", ahora) is True    # 2
    assert bot._rate_urgente_ok("u1", ahora) is True    # 3
    assert bot._rate_urgente_ok("u1", ahora) is False   # 4 -> bloqueado
    # otro usuario no se ve afectado
    assert bot._rate_urgente_ok("u2", ahora) is True
    # pasada la ventana, se libera
    assert bot._rate_urgente_ok("u1", ahora + 601) is True


def test_ahora_ve_formato():
    s = bot._ahora_ve()
    assert len(s) == 16 and s[4] == "-" and s[13] == ":"  # YYYY-MM-DD HH:MM


def test_foto_id_toma_la_mayor_resolucion():
    msg = {"photo": [{"file_id": "chica"}, {"file_id": "grande"}]}
    assert bot._foto_id(msg) == "grande"
    assert bot._foto_id({}) is None
