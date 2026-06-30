"""Bot de WhatsApp para buscar personas en el índice de redayuda.

Aporte ADITIVO. Reutiliza la lógica del bot de Telegram (búsqueda, alertas,
formato, normalización) y solo cambia el canal: recibe vía webhook de
Evolution API (WhatsApp-Baileys) y responde por la misma API.

DISEÑO ANTI-BANEO (lecciones de un proyecto WhatsApp real):
- El baneo de Meta es por ENVIAR mensajes en frío/proactivos, NO por recibir.
  Por eso este bot es REACTIVO: responde a quien le escribe primero (seguro).
- Filtra mensajes propios (fromMe), grupos (@g.us), difusión (@broadcast) y
  canales (@newsletter): nunca publica en el estado de nadie.
- Las alertas proactivas (envíos) son opt-in y con ritmo humano; el grueso de
  alertas masivas va por Telegram, que no tiene ese riesgo.
"""

__version__ = "0.1.0"
