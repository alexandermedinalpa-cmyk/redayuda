# Verificación ciudadana

Aporte **aditivo y autocontenido** a redayuda. Permite que la gente **confirme, desmienta o marque
como sospechoso/duplicado** un registro, y calcula una **etiqueta de confianza comunitaria** que se
superpone a los registros **sin modificar el núcleo** de redayuda. Sin dependencias externas.

## Por qué

Ya circula desinformación verificada (fotos falsas, reportes reciclados de otros terremotos). Una
señal de confianza colaborativa ayuda a las familias a saber cuánto fiarse de un registro.

## Modelo

Cada persona emite un voto por registro: `confirma`, `desmiente`, `sospecha` (posible
desinformación) o `duplicado`. Un autor cuenta una sola vez por registro (anti-abuso). La etiqueta
resultante:

| Etiqueta | Significado |
|---|---|
| `verificado_comunidad` | ≥2 confirmaciones, sin votos negativos |
| `confirmacion_parcial` | 1 confirmación, sin negativos |
| `posible_desinformacion` | ≥2 sospechas de falsedad |
| `en_disputa` | votos negativos significativos |
| `posible_duplicado` | ≥2 marcas de duplicado |
| `sin_verificar` | sin votos |

## Uso (como librería)

```python
from integraciones.verificacion_ciudadana import logica
e = logica.cargar("votos.json")
logica.registrar(e, record_id="hospitales:abc", tipo="confirma", autor="usuario123")
logica.guardar("votos.json", e)

# Superponer la confianza a resultados de búsqueda (no muta el índice):
registros_con_confianza = logica.aplicar_overlay(e, registros)
```

Se integra fácil con el bot de Telegram (un comando `/confirmo` o `/sospecha`) o con el frontend.

## Tests

```bash
python -m pytest integraciones/verificacion_ciudadana/tests -q
```
