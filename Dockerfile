# job-radar: la web compilada y la API de servicios en una sola imagen.
# La misma imagen sirve para el Mac y para la Raspberry Pi (arm64). Necesita BuildKit
# (el de Docker Desktop y `docker buildx`): uv se monta solo para instalar, no queda en la imagen.

# 1 · La web: Node la compila a ficheros estáticos.
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2 · Python con uv: el sistema y la API, que sirve también la web.
FROM python:3.12-slim
# tzdata: los logs y la programación diaria van en hora de Madrid (TZ en compose.yaml).
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 1000 --create-home app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH JOB_RADAR_DATOS=/app/data PYTHONUNBUFFERED=1 TZ=Europe/Madrid
WORKDIR /app
# Primero las dependencias (capa que casi nunca cambia), después el código. Misma versión de uv que en local.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=from=ghcr.io/astral-sh/uv:0.12,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY config/ config/
RUN --mount=from=ghcr.io/astral-sh/uv:0.12,source=/uv,target=/bin/uv \
    uv sync --frozen --no-dev
COPY --from=web /web/dist web/dist

# Sin root: lo que se crea en ./data del anfitrión queda con el usuario normal (uid 1000).
RUN mkdir -p /app/data && chown app:app /app/data
USER app

# Los datos (SQLite, perfil, logs, copias) van en un volumen; las claves, en .env.
VOLUME /app/data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/vivo')"
CMD ["uvicorn", "job_radar.api:crear", "--factory", "--host", "0.0.0.0", "--port", "8000"]
