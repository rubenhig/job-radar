"""Empresas: la lista (con su encaje calculado), la ficha y lo que decide Rubén de cada una."""

import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from job_radar import almacen, criba
from job_radar.api.base import bd, datos
from job_radar.api.esquemas import EmpresaEntrada, EmpresaResumen, EstadoEmpresa, PaginaEmpresas
from job_radar.preferencias import cargar as cargar_preferencias
from job_radar.puntuacion import RUBRICA

router = APIRouter(prefix="/empresas", tags=["empresas"])
TOP = 50  # el corte de la web (lib/puntuacion.ts) y de los techos de la nota

CONSULTA = """
    SELECT em.id, em.nombre, em.alias, em.es_agencia, em.estado, em.notas,
           COUNT(p.id) AS puestos_total,
           SUM(p.estado = 'abierto') AS puestos_abiertos,
           SUM(ev.nota >= """ + str(TOP) + """) AS puestos_buenos,
           SUM(json_extract(ev.resultado, '$.veredictos.rol_ia.valor')
               IN ('ia_principal', 'software_con_ia', 'ml_clasico')) AS puestos_ia,
           SUM(p.modalidad = 'remoto') AS puestos_remotos,
           SUM(json_extract(ev.resultado, '$.veredictos.fuente.valor') = 'intermediario') AS intermediario,
           COUNT(ev.id) AS evaluados,
           MAX(ev.nota) AS mejor_nota,
           GROUP_CONCAT(DISTINCT p.ciudad) AS ciudades,
           (SELECT MAX(o.vista_ultima) FROM oferta o WHERE o.empresa_id = em.id) AS vista_ultima
    FROM empresa em
    JOIN puesto p ON p.empresa_id = em.id AND p.estado IN ('abierto', 'cerrado')
    LEFT JOIN evaluacion ev ON ev.id = (SELECT MAX(x.id) FROM evaluacion x
                                        WHERE x.puesto_id = p.id AND x.rubrica = '""" + RUBRICA + """')
"""
ORDEN = {"nota": "COALESCE(mejor_nota, -1) DESC, puestos_buenos DESC",
         "puestos": "puestos_abiertos DESC, COALESCE(mejor_nota, -1) DESC",
         "recientes": "vista_ultima DESC", "nombre": "em.nombre COLLATE NOCASE"}


def _empresa(f) -> EmpresaResumen:
    consultora = bool(f["es_agencia"]) or (f["evaluados"] > 0 and f["intermediario"] * 2 > f["evaluados"])
    return EmpresaResumen(
        id=f["id"], nombre=f["nombre"], alias=json.loads(f["alias"] or "[]"), consultora=consultora,
        estado=f["estado"], notas=f["notas"], puestos_abiertos=f["puestos_abiertos"] or 0,
        puestos_total=f["puestos_total"], puestos_buenos=f["puestos_buenos"] or 0,
        puestos_ia=f["puestos_ia"] or 0, puestos_remotos=f["puestos_remotos"] or 0, mejor_nota=f["mejor_nota"],
        ciudades=sorted(c for c in (f["ciudades"] or "").split(",") if c)[:5], vista_ultima=f["vista_ultima"])


@router.get("", response_model=PaginaEmpresas)
def listar(db: Annotated[object, Depends(bd)],
           q: str | None = None,
           estado: Annotated[list[EstadoEmpresa | Literal["sin_revisar"]] | None, Query()] = None,
           consultoras: bool | None = None,
           solo_abiertas: bool = True,
           orden: Literal["nota", "puestos", "recientes", "nombre"] = "nota",
           limite: Annotated[int, Query(gt=0, le=200)] = 50,
           desde: Annotated[int, Query(ge=0)] = 0):
    """Las empresas con algún puesto. Por defecto, las que tienen alguno abierto, de mejor a peor nota."""
    donde, args, having = [], [], []
    if q:
        donde.append("(em.nombre LIKE ? OR em.alias LIKE ?)")
        args += [f"%{q}%"] * 2
    if estado:
        conocidos = [e for e in estado if e != "sin_revisar"]
        partes = ([f"em.estado IN ({','.join('?' * len(conocidos))})"] if conocidos else []) + (
            ["em.estado IS NULL"] if "sin_revisar" in estado else [])
        donde.append(f"({' OR '.join(partes)})")
        args += conocidos
    if solo_abiertas:
        having.append("SUM(p.estado = 'abierto') > 0")
    base = (f"{CONSULTA} {'WHERE ' + ' AND '.join(donde) if donde else ''} GROUP BY em.id "
            f"{'HAVING ' + ' AND '.join(having) if having else ''}")
    filas = [_empresa(f) for f in db.query(f"{base} ORDER BY {ORDEN[orden]}", args)]
    if consultoras is not None:  # se calcula en Python (mezcla la fuente y la puntuación)
        filas = [e for e in filas if e.consultora == consultoras]
    return PaginaEmpresas(total=len(filas), items=filas[desde:desde + limite])


@router.get("/{empresa_id}", response_model=EmpresaResumen)
def ficha(empresa_id: int, db: Annotated[object, Depends(bd)]):
    fila = next(iter(db.query(f"{CONSULTA} WHERE em.id = ? GROUP BY em.id", [empresa_id])), None)
    if fila is None:
        raise HTTPException(404, "No existe esa empresa")
    return _empresa(fila)


@router.put("/{empresa_id}", response_model=EmpresaResumen)
def decidir(empresa_id: int, entrada: EmpresaEntrada, db: Annotated[object, Depends(bd)],
            carpeta: Annotated[Path, Depends(datos)]):
    """Seguir, dejar pendiente o descartar (y notas). Descartar una empresa descarta sus puestos en la criba."""
    if not db.execute("SELECT 1 FROM empresa WHERE id = ?", [empresa_id]).fetchone():
        raise HTTPException(404, "No existe esa empresa")
    # Solo lo que viene en la petición: {"notas": …} no toca el estado, y {"estado": null} lo deja sin revisar.
    cambios = {k: getattr(entrada, k) for k in entrada.model_fields_set} | {"actualizada_en": almacen.ahora()}
    db["empresa"].update(empresa_id, cambios)
    db.conn.commit()
    criba.aplicar(db, cargar_preferencias(carpeta / "perfil" / "preferencias.yaml"))
    return ficha(empresa_id, db)
