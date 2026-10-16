"""API de servicios: todas las acciones del sistema, para la web, Telegram y la terminal.

    uv run uvicorn job_radar.api:crear --factory --reload      # desarrollo: http://127.0.0.1:8000/api/docs

Sirve también la web compilada (`web/dist`) en la misma dirección, así que no
hace falta CORS. Diseño en docs/arquitectura.md#cómo-se-interactúa.
"""

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

from job_radar import almacen
from job_radar.api import puestos, sistema

WEB = Path(os.environ.get("JOB_RADAR_WEB", almacen.RAIZ / "web" / "dist"))


def _nombre(ruta: APIRoute) -> str:
    """Nombres limpios en el cliente generado: `puestos-listar` y no `listar_api_puestos_get`."""
    return f"{ruta.tags[0]}-{ruta.name}" if ruta.tags else ruta.name


def crear(ruta_db: Path = almacen.RUTA_DB, datos: Path = almacen.DATOS, web: Path = WEB) -> FastAPI:
    almacen.abrir(ruta_db)  # crea o migra el esquema una vez, al arrancar
    app = FastAPI(title="job-radar", version="0.1.0", generate_unique_id_function=_nombre,
                  docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.state.ruta_db, app.state.datos = str(ruta_db), datos

    api = APIRouter(prefix="/api")
    api.include_router(puestos.router)
    api.include_router(sistema.router)
    app.include_router(api)

    if web.exists():  # la app compilada; cualquier ruta que no sea de la API la resuelve la propia app
        app.mount("/assets", StaticFiles(directory=web / "assets"), name="assets")

        @app.get("/{ruta:path}", include_in_schema=False)
        def app_web(ruta: str):
            fichero = (web / ruta).resolve()
            if ruta and fichero.is_file() and web.resolve() in fichero.parents:
                return FileResponse(fichero)
            return FileResponse(web / "index.html")

    return app
