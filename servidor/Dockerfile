# Imagen del servidor del grupo (canvas CD-002, sección S).
# Etapas: base → pruebas (pytest) | servidor (la final, la que levanta el compose).

FROM python:3.12-slim AS base
# Sin búfer, para que `docker compose logs` muestre cada línea al momento.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
# Usuario sin privilegios, dueño de /datos para que el volumen nazca con ese dueño.
RUN useradd --system --uid 10001 --no-create-home chat \
    && mkdir /datos && chown chat /datos

FROM base AS pruebas
COPY requirements-pruebas.txt pyproject.toml ./
RUN pip install -r requirements-pruebas.txt
COPY chat ./chat
COPY pruebas ./pruebas
USER chat
CMD ["python", "-m", "pytest"]

FROM base AS servidor
COPY chat ./chat
USER chat
EXPOSE 8000
# La imagen slim no trae curl: el healthcheck usa Python contra /fed/health.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + (os.environ.get('PUERTO') or '8000') + '/fed/health', timeout=2)"]
# Forma exec: python es el PID 1 y recibe SIGTERM directamente.
CMD ["python", "-m", "chat"]
