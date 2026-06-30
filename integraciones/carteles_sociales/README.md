# Carteles para redes sociales ("SE BUSCA")

Aporte **aditivo** a redayuda. Convierte un registro de persona desaparecida en una **imagen SVG
1080×1080** lista para compartir en Instagram, WhatsApp o TikTok — donde la gente en Venezuela
realmente difunde información. Sin dependencias externas.

## Por qué

La información real circula sobre todo por redes sociales. Esto convierte un registro del índice en
un cartel visual compartible, multiplicando el alcance de la búsqueda en el canal donde la gente ya
está.

## Uso

```bash
python -m integraciones.carteles_sociales.cli --api https://nodo-redayuda --salida carteles/
python -m integraciones.carteles_sociales.cli --entrada registros.json --salida carteles/
```

Genera un `.svg` por persona (conviértelo a PNG con cualquier visor/navegador para subirlo).

## Nota ética sobre menores

Por defecto se **omiten los menores de edad** (difundir masivamente la cara de un niño tiene
riesgos: trata, secuestro). Usa `--incluir-menores` **solo** en coordinación con la familia o una
autoridad/organización responsable. Ver `../../ETICA` del proyecto.

## Tests

```bash
python -m pytest integraciones/carteles_sociales/tests -q
```
