# job-radar: la web compilada y la API de servicios en una sola imagen.
# La misma imagen sirve para el Mac y para la Raspberry Pi (arm64).

# 1 · La web: Node la compila a ficheros estáticos.
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# 2 · Python con uv: el sistema y la API, que sirve también la web.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH JOB_RADAR_DATOS=/app/data PYTHONUNBUFFERED=1
WORKDIR /app
# Primero las dependencias (capa que casi nunca cambia), después el código.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
COPY config/ config/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist web/dist

# Los datos (SQLite, perfil, logs) van en un volumen; las claves, en .env.
VOLUME /app/data
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/resumen')"
CMD ["uvicorn", "job_radar.api:crear", "--factory", "--host", "0.0.0.0", "--port", "8000"]
