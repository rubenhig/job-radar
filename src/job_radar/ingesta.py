"""Ingesta: lanza una búsqueda de una fuente y lo deja todo trazado en el almacén.

Por cada búsqueda: una Ejecución; por cada respuesta, su Bruto (inmutable) y,
si se entiende, su Oferta. Un bruto que no se puede normalizar no para la
ejecución: se cuenta como error de normalización y se reprocesa más adelante.
"""

import json
import logging
import traceback
from collections import Counter

from job_radar import almacen
from job_radar.fuentes.base import Busqueda, Conector, Oferta

# Campos cuya completitud se vigila (los que no son de identificación).
VIGILADOS = [c for c in Oferta.model_fields if c not in ("fuente_id", "id_externo", "derivados")]

log = logging.getLogger(__name__)


def ejecutar(db, conector: Conector, busqueda: Busqueda, tarea_id: int | None = None) -> int:
    """Devuelve el id de la Ejecución. No lanza: un fallo de la fuente queda registrado en ella."""
    # Se guarda la búsqueda tal como se lanza: la ejecución apunta a sus parámetros exactos.
    almacen.guardar_busqueda(db, busqueda.id, busqueda.fuente, busqueda.parametros, busqueda.frecuencia_h)
    ejecucion = almacen.iniciar_ejecucion(db, conector.fuente, conector.version, busqueda.id, busqueda.horas,
                                          tarea_id)
    m = {"recibidos": 0, "nuevos": 0, "actualizados": 0, "errores_norm": 0}
    rellenos = Counter()
    estado, error = "ok", None
    try:
        for bruto in conector.traer(busqueda):
            m["recibidos"] += 1
            bruto_id, _ = almacen.guardar_bruto(db, ejecucion, conector.fuente, bruto.id_externo,
                                                bruto.payload, bruto.eliminados)
            try:
                oferta = conector.normalizar(bruto.payload)
            except Exception as e:  # noqa: BLE001 — el bruto queda guardado para reprocesar
                m["errores_norm"] += 1
                log.warning("%s: no se pudo normalizar %s: %s", conector.fuente, bruto.id_externo, e)
                continue
            rellenos.update(c for c in VIGILADOS if getattr(oferta, c) not in (None, "", []))
            oferta_id, nueva = almacen.guardar_oferta(db, oferta.fila(), bruto_id, conector.version)
            db.execute("INSERT OR IGNORE INTO vista VALUES (?, ?)", [ejecucion, oferta_id])
            m["nuevos" if nueva else "actualizados"] += 1
    except Exception as e:  # noqa: BLE001
        estado = "parcial" if m["recibidos"] else "error"
        error = "".join(traceback.format_exception_only(e)).strip()[:2000]
        log.error("%s: %s", busqueda.id, error)
    if estado == "ok" and m["errores_norm"]:
        estado = "parcial"
    normalizadas = m["nuevos"] + m["actualizados"]
    completitud = {c: round(100 * rellenos[c] / normalizadas) for c in VIGILADOS} if normalizadas else None
    almacen.cerrar_ejecucion(db, ejecucion, estado, error=error, cuota=conector.cuota, completitud=completitud,
                             coste_usd=getattr(conector, "coste_usd", None), **m)
    return ejecucion


def renormalizar(db, conector: Conector) -> Counter:
    """Vuelve a interpretar las ofertas guardadas de la fuente desde su bruto, con la versión actual del
    conector, sin pedir nada a la fuente. Conserva cuándo se vieron y a qué puesto pertenecen."""
    cuenta = Counter()
    for o in db.query("""SELECT o.id, b.payload FROM oferta o JOIN bruto b ON b.id = o.bruto_id
                         WHERE o.fuente_id = ?""", [conector.fuente]):
        try:
            nueva = conector.normalizar(json.loads(o["payload"])).fila()
        except Exception as e:  # noqa: BLE001
            log.warning("%s: no se pudo renormalizar la oferta %s: %s", conector.fuente, o["id"], e)
            cuenta["errores"] += 1
            continue
        cuenta["cambiadas" if almacen.reescribir_oferta(db, o["id"], nueva, conector.version) else "iguales"] += 1
    db.conn.commit()
    return cuenta
