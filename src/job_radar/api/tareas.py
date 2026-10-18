"""Búsquedas a demanda desde la web: lanzarlas y seguir su progreso (job_radar.tareas)."""

import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from job_radar import tareas
from job_radar.api.base import bd, datos
from job_radar.api.esquemas import EjecucionTarea, Tarea
from job_radar.fuentes import registro as reg

router = APIRouter(prefix="/tareas", tags=["tareas"])


def _tarea(db, fila) -> Tarea:
    ejecuciones = [EjecucionTarea(**{k: e[k] for k in EjecucionTarea.model_fields})
                   for e in db.query("SELECT * FROM ejecucion WHERE tarea_id = ? ORDER BY id", [fila["id"]])]
    return Tarea(**{k: fila[k] for k in ("id", "estado", "creada_en", "inicio", "fin", "error")},
                 parametros=json.loads(fila["parametros"]), resumen=json.loads(fila["resumen"] or "null"),
                 ejecuciones=ejecuciones)


@router.post("/busqueda", response_model=Tarea, status_code=201)
def buscar(pedido: tareas.Pedido, request: Request, db: Annotated[Any, Depends(bd)],
           carpeta: Annotated[Path, Depends(datos)]):
    """Lanza una búsqueda ya. Vuelve en el acto: el progreso se consulta con GET /tareas/{id}."""
    desconocidas = set(pedido.fuentes) - set(reg.cargar().activas())
    if desconocidas:
        raise HTTPException(422, f"Fuentes que no existen o no están activas: {', '.join(sorted(desconocidas))}")
    tareas.revisar(db)
    if db.execute("SELECT 1 FROM tarea WHERE estado IN ('en_cola', 'en_curso')").fetchone():
        raise HTTPException(409, "Ya hay una búsqueda en marcha: espera a que acabe")
    tarea_id = tareas.crear(db, pedido)
    pid = tareas.lanzar(Path(request.app.state.ruta_db), carpeta, tarea_id)
    db["tarea"].update(tarea_id, {"pid": pid})
    db.conn.commit()
    return _tarea(db, db["tarea"].get(tarea_id))


@router.get("", response_model=list[Tarea])
def listar(db: Annotated[Any, Depends(bd)]):
    """Las últimas búsquedas a demanda, la más reciente primero."""
    tareas.revisar(db)
    return [_tarea(db, f) for f in db.query("SELECT * FROM tarea ORDER BY id DESC LIMIT 20")]


@router.get("/{tarea_id}", response_model=Tarea)
def ficha(tarea_id: int, db: Annotated[Any, Depends(bd)]):
    tareas.revisar(db)
    fila = db.execute("SELECT * FROM tarea WHERE id = ?", [tarea_id]).fetchone()
    if fila is None:
        raise HTTPException(404, "No existe esa búsqueda")
    return _tarea(db, dict(db["tarea"].get(tarea_id)))
