# Exportación offline / listas imprimibles

Aporte **aditivo** a redayuda. Genera **HTML imprimible** (sin dependencias) con las personas
localizadas, agrupadas por hospital o ciudad, para **imprimir y pegar en paredes** o compartir por
Bluetooth/SD donde no hay internet — replicando lo que la gente ya hace ("listas en la pared").

## Por qué

Con el apagón de internet, muchas familias buscan en **listas físicas pegadas en hospitales y
plazas**. Esto convierte el índice digital en hojas listas para imprimir, cerrando la brecha entre
el dato online y la gente sin conexión.

## Uso

```bash
# Desde la API en vivo
python -m integraciones.exportacion_offline.cli --api https://nodo-redayuda --salida listas.html

# Desde un volcado JSON
python -m integraciones.exportacion_offline.cli --entrada registros.json --agrupar city --salida listas.html
```

Abre `listas.html` en cualquier navegador y usa *Imprimir* (cada hospital empieza en página nueva).

## Privacidad

Lista solo personas **localizadas** (lo que las familias quieren ver). **No** incluye cédula ni
contacto. Verifica siempre con el centro indicado.

## Tests

```bash
python -m pytest integraciones/exportacion_offline/tests -q
```
