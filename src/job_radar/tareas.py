"""Búsquedas a demanda: lo que Rubén lanza desde la web, sin esperar a la ingesta diaria.

Dos modos:
  - habitual: las búsquedas de siempre (las de las preferencias), ya, con las fuentes que elija.
  - puntual: sus términos y su lugar («LLM Engineer» en Barcelona, o remoto desde otro país), sin tocar las
    preferencias. Mira la última semana.

La API crea la Tarea y lanza `job-radar tarea N` como proceso aparte (`lanzar`): la petición vuelve en el
acto y la web consulta el progreso. El proceso respeta el cerrojo de la ingesta (no se solapa con la diaria).
En la Pi lo hará el worker (#41), con la misma Tarea. Cada ejecución apunta qué ofertas vio (tabla `vista`),
y así «lo que encontró esta búsqueda» incluye también lo que ya existía.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from job_radar import almacen
from job_radar.fuentes import registro as reg
from job_radar.fuentes.base import Busqueda, Intencion
from job_radar.preferencias import Modalidad, Preferencias

VENTANA_PUNTUAL_H = 7 * 24  # una búsqueda puntual mira la última semana
GRATIS = ["freehire", "indeed"]  # las de pago (LinkedIn) o delicadas (InfoJobs) se eligen a propósito


class Pedido(BaseModel):
    """Lo que se pide desde la web."""

    modo: Literal["habitual", "puntual"] = "habitual"
    fuentes: list[str] = Field(default_factory=lambda: list(GRATIS), min_length=1)
    terminos: list[str] = Field(default=[], max_length=10)
    ciudad: str | None = Field(None, max_length=80)
    remoto: bool = False
    pais: str = Field("ES", pattern=r"^[A-Z]{2}$")
    puntuar: bool = True

    @model_validator(mode="after")
    def completo(self):
        if self.modo == "puntual":
            self.terminos = [t.strip() for t in self.terminos if t.strip()]
            if not self.terminos:
                raise ValueError("una búsqueda puntual necesita al menos un término")
            if not self.remoto and not (self.ciudad or "").strip():
                raise ValueError("una búsqueda puntual necesita una ciudad o «remoto»")
        return self


def busquedas(pedido: Pedido, tarea_id: int, prefs: Preferencias, registro: reg.Registro,
              conectores: dict) -> list[Busqueda]:
    """Las búsquedas de la tarea, en el vocabulario de cada fuente elegida."""
    activas = {k: f for k, f in registro.activas().items() if k in pedido.fuentes}
    if pedido.modo == "habitual":
        return reg.busquedas(prefs, reg.Registro(fuentes=activas), conectores)
    intencion = Intencion(id=f"t{tarea_id}", terminos=tuple(pedido.terminos), pais=pedido.pais,
                          ciudad=None if pedido.remoto else pedido.ciudad.strip(),
                          modalidades=(Modalidad.REMOTO,) if pedido.remoto else
                          (Modalidad.PRESENCIAL, Modalidad.HIBRIDO), por_terminos=True)
    salida = []
    for fuente_id in activas:
        try:
            varias = conectores[fuente_id].parametros(intencion)
        except Exception:  # noqa: BLE001 — una fuente que no sabe buscar eso no tumba las demás
            continue
        for n, parametros in enumerate(varias, start=1):
            salida.append(Busqueda(id=f"{fuente_id}:t{tarea_id}" + (f"-{n}" if len(varias) > 1 else ""),
                                   fuente=fuente_id, parametros=parametros, frecuencia_h=VENTANA_PUNTUAL_H))
    return salida


def crear(db, pedido: Pedido) -> int:
    tarea_id = db["tarea"].insert({"tipo": "busqueda", "parametros": pedido.model_dump_json(),
                                   "creada_en": almacen.ahora()}).last_pk
    db.conn.commit()
    return tarea_id


def lanzar(ruta_db: Path, datos: Path, tarea_id: int) -> int:
    """`job-radar tarea N` como proceso aparte (sobrevive a la petición). Devuelve su pid."""
    entorno = os.environ | {"JOB_RADAR_DATOS": str(datos)}
    proceso = subprocess.Popen([sys.executable, "-m", "job_radar.cli", "--db", str(ruta_db), "tarea", str(tarea_id)],
                               env=entorno, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    return proceso.pid


def vivo(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def revisar(db) -> None:
    """Una tarea sin terminar cuyo proceso ya no existe (se cerró el Mac, se mató, falló al arrancar) pasa a error."""
    for t in db.query("SELECT id, pid FROM tarea WHERE estado IN ('en_cola', 'en_curso') AND pid IS NOT NULL"):
        if not vivo(t["pid"]):
            db["tarea"].update(t["id"], {"estado": "error", "fin": almacen.ahora(),
                                         "error": "el proceso terminó sin cerrar la tarea"})
    db.conn.commit()


def resumen(db, tarea_id: int) -> dict:
    fila = db.execute("""SELECT COUNT(*), COALESCE(SUM(recibidos), 0), COALESCE(SUM(nuevos), 0),
                                SUM(estado = 'error') FROM ejecucion WHERE tarea_id = ?""", [tarea_id]).fetchone()
    puestos = db.execute("""SELECT COUNT(DISTINCT o.puesto_id) FROM vista v JOIN ejecucion e ON e.id = v.ejecucion_id
                            JOIN oferta o ON o.id = v.oferta_id WHERE e.tarea_id = ?""", [tarea_id]).fetchone()[0]
    return {"busquedas": fila[0], "recibidas": fila[1], "nuevas": fila[2], "errores": fila[3] or 0,
            "puestos": puestos}


def guardar_resumen(db, tarea_id: int, estado: str, error: str | None = None, **extra) -> None:
    db["tarea"].update(tarea_id, {"estado": estado, "fin": almacen.ahora(), "error": error,
                                  "resumen": json.dumps(resumen(db, tarea_id) | extra)})
    db.conn.commit()
