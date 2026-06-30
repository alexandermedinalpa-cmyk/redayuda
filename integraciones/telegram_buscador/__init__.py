"""Bot de Telegram para buscar personas y recibir alertas sobre el índice de redayuda.

Aporte ADITIVO: se apoya en la API pública de redayuda (/api/records/search y
/api/records/feed). No modifica nada del núcleo. Sin dependencias externas
(solo biblioteca estándar) para que funcione en entornos de bajo ancho de banda.

Motivación (situación real): dentro de Venezuela hay apagón/restricción de
internet. La web de redayuda puede ser inalcanzable, pero las apps de mensajería
suelen sobrevivir al estrangulamiento de datos y consumen kilobytes. Este bot
lleva la búsqueda y las alertas a ese canal.
"""

__version__ = "0.1.0"
