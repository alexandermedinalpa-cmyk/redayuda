# Bot de Telegram — búsqueda y alertas sobre el índice de redayuda

Aporte **aditivo** a [redayuda](../../README.md): lleva la búsqueda de personas y las alertas a
Telegram. No modifica el núcleo; se apoya en la API pública (`/api/records/search` y
`/api/records/feed`). **Sin dependencias externas** (solo la biblioteca estándar de Python).

## Por qué (situación real)

Tras los terremotos de junio de 2026 hay **apagón y restricción de internet dentro de Venezuela**
(la ONU lo llamó "cuestión de vida o muerte"). La web puede ser inalcanzable, pero las apps de
mensajería suelen sobrevivir al estrangulamiento de datos y consumen kilobytes. Este bot permite:

- **Buscar** a una persona en las 22+ fuentes federadas escribiendo su nombre en un chat.
- **Suscribirse a una alerta**: el bot avisa cuando esa persona aparece **de cualquier forma**
  — viva, herida, en necesidad o fallecida — para sacar a las familias del limbo de no saber.

## Trato ético (no negociable)

- **No expone datos sensibles** (cédula, contacto) en los mensajes.
- **Coincidencias delicadas (fallecimiento): no se afirman.** El bot envía un mensaje compasivo
  que **redirige a la fuente/autoridad** para confirmación humana, nunca declara una muerte de
  forma automática (riesgo de homónimos + dignidad).
- **Siempre pide verificar** con el hospital o la fuente; puede haber personas con el mismo nombre.
- Telegram no permite que un bot escriba primero a un desconocido: la persona inicia el chat una
  vez (`/start` o `/alerta`), y a partir de ahí el bot puede avisarle.

## Uso

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."   # token de @BotFather
export REDAYUDA_API="https://tu-nodo-redayuda"  # def: http://127.0.0.1:8000
export ALERTAS_DB="alertas.json"            # dónde guardar las suscripciones

python -m integraciones.telegram_buscador.bot
```

### Comandos
- `/buscar Nombre Apellido` — busca en todas las fuentes
- `/alerta Nombre Apellido` — avisa cuando la persona aparezca
- `/misalertas` — lista tus alertas
- `/quitar Nombre Apellido` — elimina una alerta

## Tests

```bash
python -m pytest integraciones/telegram_buscador/tests -q
```

Corren sin red ni token (el cliente HTTP usa un `fetch` inyectable).
