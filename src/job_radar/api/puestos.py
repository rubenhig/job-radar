"""Puestos: lista con filtros, ficha y etiqueta (top / no top)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from job_radar import almacen
from job_radar.api.base import bd
from job_radar.api.esquemas import (CampoFusionado, Etiqueta, EtiquetaEntrada, Oferta, PaginaPuestos, PuestoDetalle,
                                    PuestoResumen, Salario, Via)

router = APIRouter(prefix="/puestos", tags=["puestos"])

SEP = "\x1f"


def _salario(d: dict | None) -> Salario | None:
    return Salario(**d) if d and (d.get("salario_min") or d.get("salario_max")) else None


def _resumen(fila: dict) -> dict:
    fusion = json.loads(fila["fusion"] or "{}")
    vias = sorted({tuple(v.split(SEP, 1)) for v in (fila["vias"] or "").split("\x1e") if v})
    etiqueta = (Etiqueta(valor=fila["etiqueta"], motivo=fila["motivo"], actualizada_en=fila["etiquetada_en"])
                if fila["etiqueta"] else None)
    return dict(
        id=fila["id"], titulo=fila["titulo"], empresa=(fusion.get("empresa") or {}).get("valor"),
        ciudad=fila["ciudad"], pais=fila["pais"], modalidad=fila["modalidad"],
        salario=_salario((fusion.get("salario") or {}).get("valor")),
        publicada_en=(fusion.get("publicada_en") or {}).get("valor"),
        vista_primera=fila["vista_primera"], vista_ultima=fila["vista_ultima"],
        vias=[Via(fuente=f, empresa=e or None) for f, e in vias], ofertas=fila["ofertas"], etiqueta=etiqueta)


CONSULTA = """
    SELECT p.id, p.titulo, p.ciudad, p.pais, p.modalidad, p.fusion, p.estado,
           MIN(o.vista_primera) AS vista_primera, MAX(o.vista_ultima) AS vista_ultima, COUNT(o.id) AS ofertas,
           GROUP_CONCAT(o.fuente_id || char(31) || COALESCE(o.empresa, ''), char(30)) AS vias,
           e.valor AS etiqueta, e.motivo, e.actualizada_en AS etiquetada_en
    FROM puesto p JOIN oferta o ON o.puesto_id = p.id LEFT JOIN etiqueta e ON e.puesto_id = p.id
"""

Orden = Literal["recientes", "publicadas", "vias"]
ORDEN_SQL = {"recientes": "vista_primera DESC", "vias": "ofertas DESC, vista_primera DESC",
             "publicadas": "json_extract(p.fusion, '$.publicada_en.valor') DESC"}


@router.get("", response_model=PaginaPuestos)
def listar(db: Annotated[object, Depends(bd)],
           q: str | None = None,
           fuente: Annotated[list[str] | None, Query()] = None,
           modalidad: Annotated[list[str] | None, Query()] = None,
           ciudad: str | None = None,
           etiqueta: Literal["top", "no_top", "sin"] | None = None,
           dias: Annotated[int | None, Query(gt=0)] = None,
           orden: Orden = "recientes",
           limite: Annotated[int, Query(gt=0, le=200)] = 50,
           desde: Annotated[int, Query(ge=0)] = 0):
    donde, args = ["p.estado = 'abierto'"], []
    if q:
        donde.append("p.id IN (SELECT puesto_id FROM oferta WHERE titulo LIKE ? OR empresa LIKE ? OR descripcion LIKE ?)")
        args += [f"%{q}%"] * 3
    if fuente:
        donde.append(f"p.id IN (SELECT puesto_id FROM oferta WHERE fuente_id IN ({','.join('?' * len(fuente))}))")
        args += fuente
    if modalidad:
        donde.append(f"p.modalidad IN ({','.join('?' * len(modalidad))})")
        args += modalidad
    if ciudad:
        donde.append("p.ciudad LIKE ?")
        args.append(f"%{ciudad}%")
    if etiqueta == "sin":
        donde.append("e.valor IS NULL")
    elif etiqueta:
        donde.append("e.valor = ?")
        args.append(etiqueta)
    having, hargs = "", []
    if dias:
        having = "HAVING MAX(o.vista_ultima) >= ?"
        hargs.append((datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="seconds"))
    base = f"{CONSULTA} WHERE {' AND '.join(donde)} GROUP BY p.id {having}"
    total = db.execute(f"SELECT COUNT(*) FROM ({base})", args + hargs).fetchone()[0]
    filas = db.query(f"{base} ORDER BY {ORDEN_SQL[orden]} LIMIT ? OFFSET ?", args + hargs + [limite, desde])
    return PaginaPuestos(total=total, items=[PuestoResumen(**_resumen(f)) for f in filas])


def _oferta(f: dict) -> Oferta:
    return Oferta(**{k: f[k] for k in Oferta.model_fields if k in f and k not in ("salario", "skills", "derivados",
                                                                                   "es_agencia")},
                  salario=_salario(f), skills=json.loads(f["skills"]) if f["skills"] else None,
                  derivados=json.loads(f["derivados"]) if f["derivados"] else None,
                  es_agencia=None if f["es_agencia"] is None else bool(f["es_agencia"]))


@router.get("/{puesto_id}", response_model=PuestoDetalle)
def ficha(puesto_id: int, db: Annotated[object, Depends(bd)]):
    fila = next(iter(db.query(f"{CONSULTA} WHERE p.id = ? GROUP BY p.id", [puesto_id])), None)
    if fila is None:
        raise HTTPException(404, "No existe ese puesto")
    ofertas = [_oferta(o) for o in db.query(
        "SELECT * FROM oferta WHERE puesto_id = ? ORDER BY vista_primera", [puesto_id])]
    fusion = {k: CampoFusionado(**v) for k, v in json.loads(fila["fusion"] or "{}").items()}
    return PuestoDetalle(**_resumen(fila), estado=fila["estado"], fusion=fusion, lista_ofertas=ofertas)


@router.put("/{puesto_id}/etiqueta", response_model=Etiqueta)
def etiquetar(puesto_id: int, entrada: EtiquetaEntrada, db: Annotated[object, Depends(bd)]):
    if not db.execute("SELECT 1 FROM puesto WHERE id = ?", [puesto_id]).fetchone():
        raise HTTPException(404, "No existe ese puesto")
    ahora = almacen.ahora()
    db.execute("""INSERT INTO etiqueta (puesto_id, valor, motivo, creada_en, actualizada_en) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT (puesto_id) DO UPDATE SET valor = excluded.valor, motivo = excluded.motivo,
                                                        actualizada_en = excluded.actualizada_en""",
               [puesto_id, entrada.valor, entrada.motivo, ahora, ahora])
    db.conn.commit()
    return Etiqueta(valor=entrada.valor, motivo=entrada.motivo, actualizada_en=ahora)


@router.delete("/{puesto_id}/etiqueta", status_code=204)
def quitar_etiqueta(puesto_id: int, db: Annotated[object, Depends(bd)]):
    db.execute("DELETE FROM etiqueta WHERE puesto_id = ?", [puesto_id])
    db.conn.commit()
