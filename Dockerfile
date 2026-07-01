FROM python:3.12-slim

# Evita .pyc y buffering en logs de contenedor
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias de runtime (mismas versiones que pyproject.toml).
# Se instalan aparte del codigo para aprovechar la cache de capas.
RUN pip install --no-cache-dir \
    "fastapi[standard]==0.138.1" \
    "httpx>=0.28,<1.0" \
    "python-dotenv>=1.0,<2.0"

# Codigo de la app, frontend estatico, integraciones (bot embebido) y entrypoint.
COPY app ./app
COPY static ./static
COPY integraciones ./integraciones
COPY run_web.py ./run_web.py

# El indice SQLite vive en un volumen persistente montado en /data.
ENV DATABASE_PATH=/data/index.db
RUN mkdir -p /data

# Usuario no-root; debe poder escribir el volumen /data.
RUN useradd --system --uid 10001 appuser \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

# Arranca la web de redayuda + el webhook del bot de Telegram (misma máquina).
CMD ["uvicorn", "run_web:app", "--host", "0.0.0.0", "--port", "8000"]
