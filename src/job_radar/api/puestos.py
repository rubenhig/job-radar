"""Puestos: lista con filtros, ficha y etiqueta (top / no top)."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from job_radar import almacen
from job_radar.api.base import bd
from job_radar.api.esquemas import (CampoFusionado, Criterio, EstadoLista, Etiqueta, EtiquetaEntrada, Evaluacion,
                                    Guardado, GuardadoEntrada, Oferta, PaginaPuestos, PuestoDetalle, PuestoResumen,
                                    RequisitoEvaluado, Salario, Valoracion, Via)
from job_radar.puntuacion import RUBRICA

router = APIRouter(prefix="/puestos", tags=["puestos"])

SEP = "\x1f"


def _salario(d: dict | None) -> Salario | None:
    return Salario(**d) if d and (d.get("salario_min") or d.get("salario_max")) else None


def _resumen(fila: dict) -> dict:
    fusion = json.loads(fila["fusion"] or "{}")
    vias = sorted({tuple(v.split(SEP, 1)) for v in (fila["vias"] or "").split("\x1e") if v})
    etiqueta = (Etiqueta(valor=fila["etiqueta"], motivo=fila["motivo"], actualizada_en=fila["etiquetada_en"])
                if fila["etiqueta"] else None)
    valoracion = (Valoracion(nota=fila["nota"], vetado=bool(fila["vetado"]), motivo_veto=fila["motivo_veto"],
                             marcas=json.loads(fila["marcas"]) if fila["marcas"] else [],
                             resumen=fila["ev_resumen"], rol_ia=fila["ev_rol"])
                  if fila["nota"] is not None else None)
    guardado = (Guardado(estado=fila["g_estado"], prioridad=fila["g_prioridad"], notas=fila["g_notas"],
                         etiquetas=json.loads(fila["g_etiquetas"] or "[]"),
                         historial=json.loads(fila["g_historial"] or "[]"),
                         creado_en=fila["g_creado_en"], actualizado_en=fila["g_actualizado_en"])
                if fila["g_estado"] else None)
    return dict(
        valoracion=valoracion, guardado=guardado, estado=fila["estado"],
        id=fila["id"], titulo=fila["titulo"], empresa=(fusion.get("empresa") or {}).get("valor"),
        ciudad=fila["ciudad"], pais=fila["pais"], modalidad=fila["modalidad"],
        salario=_salario((fusion.get("salario") or {}).get("valor")),
        publicada_en=(fusion.get("publicada_en") or {}).get("valor"),
        vista_primera=fila["vista_primera"], vista_ultima=fila["vista_ultima"],
        vias=[Via(fuente=f, empresa=e or None) for f, e in vias], ofertas=fila["ofertas"], etiqueta=etiqueta,
        descarte=fila["descarte"])


CONSULTA = """
    SELECT p.id, p.titulo, p.ciudad, p.pais, p.modalidad, p.fusion, p.estado, p.descarte,
           MIN(o.vista_primera) AS vista_primera, MAX(o.vista_ultima) AS vista_ultima, COUNT(o.id) AS ofertas,
           GROUP_CONCAT(o.fuente_id || char(31) || COALESCE(o.empresa, ''), char(30)) AS vias,
           e.valor AS etiqueta, e.motivo, e.actualizada_en AS etiquetada_en,
           ev.id AS evaluacion_id, ev.nota, ev.vetado, ev.motivo_veto, ev.marcas,
           json_extract(ev.resultado, '$.veredictos.resumen') AS ev_resumen,
           json_extract(ev.resultado, '$.veredictos.rol_ia.valor') AS ev_rol,
           g.estado AS g_estado, g.prioridad AS g_prioridad, g.notas AS g_notas, g.etiquetas AS g_etiquetas,
           g.historial AS g_historial, g.creado_en AS g_creado_en, g.actualizado_en AS g_actualizado_en
    FROM puesto p JOIN oferta o ON o.puesto_id = p.id LEFT JOIN etiqueta e ON e.puesto_id = p.id
    LEFT JOIN guardado g ON g.puesto_id = p.id
    LEFT JOIN evaluacion ev ON ev.id = (SELECT MAX(x.id) FROM evaluacion x
                                        WHERE x.puesto_id = p.id AND x.rubrica = '""" + RUBRICA + """')
"""

Orden = Literal["recientes", "publicadas", "vias", "nota", "prioridad"]
ORDEN_SQL = {"recientes": "vista_primera DESC", "vias": "ofertas DESC, vista_primera DESC",
             "nota": "COALESCE(ev.nota, -1) DESC, vista_primera DESC",
             "publicadas": "json_extract(p.fusion, '$.publicada_en.valor') DESC",
             "prioridad": "COALESCE(g.prioridad, -1) DESC, g.actualizado_en DESC"}


@router.get("", response_model=PaginaPuestos)
def listar(db: Annotated[object, Depends(bd)],
           q: str | None = None,
           fuente: Annotated[list[str] | None, Query()] = None,
           modalidad: Annotated[list[str] | None, Query()] = None,
           ciudad: str | None = None,
           etiqueta: Literal["top", "no_top", "sin"] | None = None,
           dias: Annotated[int | None, Query(gt=0)] = None,
           nota_min: Annotated[int | None, Query(ge=0, le=100)] = None,
           puntuado: bool | None = None,
           descartados: bool = False,
           nuevos_desde: str | None = None,
           guardado: bool | None = None,
           estado_lista: Annotated[list[EstadoLista] | None, Query()] = None,
           mi_etiqueta: str | None = None,
           orden: Orden = "recientes",
           limite: Annotated[int, Query(gt=0, le=200)] = 50,
           desde: Annotated[int, Query(ge=0)] = 0):
    if guardado or estado_lista or mi_etiqueta:
        # Mi lista: lo guardado, aunque la oferta ya haya caducado (a un puesto cerrado puedes haber aplicado).
        donde, args = ["p.estado IN ('abierto', 'cerrado')", "g.puesto_id IS NOT NULL"], []
        if estado_lista:
            donde.append(f"g.estado IN ({','.join('?' * len(estado_lista))})")
            args += estado_lista
        if mi_etiqueta:
            donde.append("EXISTS (SELECT 1 FROM json_each(g.etiquetas) WHERE value = ?)")
            args.append(mi_etiqueta)
    else:
        # Por defecto, lo que pasa la criba; con `descartados`, solo lo descartado.
        donde = ["p.estado = 'abierto'", "p.descarte IS NOT NULL" if descartados else "p.descarte IS NULL"]
        args = []
        if guardado is False:
            donde.append("g.puesto_id IS NULL")
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
    if nota_min is not None:
        donde.append("ev.nota >= ?")
        args.append(nota_min)
    if puntuado is not None:
        donde.append("ev.id IS NOT NULL" if puntuado else "ev.id IS NULL")
    condiciones, hargs = [], []
    if dias:
        condiciones.append("MAX(o.vista_ultima) >= ?")
        hargs.append((datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="seconds"))
    if nuevos_desde:  # visto por primera vez después de esa fecha (la visita anterior)
        condiciones.append("MIN(o.vista_primera) > ?")
        hargs.append(nuevos_desde)
    having = f"HAVING {' AND '.join(condiciones)}" if condiciones else ""
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
    evaluacion = _evaluacion(db.execute("SELECT * FROM evaluacion WHERE id = ?", [fila["evaluacion_id"]]).fetchone()
                             if fila["evaluacion_id"] else None)
    return PuestoDetalle(**_resumen(fila), fusion=fusion, lista_ofertas=ofertas, evaluacion=evaluacion)


def _evaluacion(f) -> Evaluacion | None:
    if f is None:
        return None
    r = json.loads(f["resultado"])
    v = r["veredictos"]
    criterio = lambda c: Criterio(valor=c.get("valor") or c.get("veredicto"), cita=c.get("cita"),  # noqa: E731
                                  motivo=c["motivo"])
    return Evaluacion(
        nota=f["nota"], vetado=bool(f["vetado"]), motivo_veto=f["motivo_veto"],
        marcas=json.loads(f["marcas"]) if f["marcas"] else [], resumen=v["resumen"],
        compuertas={k: criterio(v[k]) for k in ("modalidad", "elegibilidad", "idioma")},
        dimensiones={k: criterio(v[k]) for k in ("rol_ia", "funcion", "seniority", "fuente")},
        requisitos=[RequisitoEvaluado(**q) for q in v["requisitos"]], parciales=r["parciales"],
        citas_falsas=r["citas_falsas"], rubrica=f["rubrica"], modelo=f["modelo"], coste_usd=f["coste_usd"],
        creada_en=f["creada_en"])


@router.put("/{puesto_id}/etiqueta", response_model=Etiqueta)
def etiquetar(puesto_id: int, entrada: EtiquetaEntrada, db: Annotated[object, Depends(bd)]):
    if not db.execute("SELECT 1 FROM puesto WHERE id = ?", [puesto_id]).fetchone():
        raise HTTPException(404, "No existe ese puesto")
    ahora = almacen.ahora()
    db.execute("""INSERT INTO etiqueta (puesto_id, valor, motivo, creada_en, actualizada_en) VALUES (?, ?, ?, ?, ?)
                  ON CONFLICT (puesto_id) DO UPDATE SET valor = excluded.valor, motivo = excluded.motivo,
                                                        actualizada_en = excluded.actualizada_en""",
               [puesto_id, entrada.valor, entrada.motivo, ahora, ahora])
    if entrada.valor == "top":  # lo que Rubén marca como top no lo descarta la criba (job_radar.criba)
        db.execute("UPDATE puesto SET descarte = NULL WHERE id = ?", [puesto_id])
    db.conn.commit()
    return Etiqueta(valor=entrada.valor, motivo=entrada.motivo, actualizada_en=ahora)


@router.delete("/{puesto_id}/etiqueta", status_code=204)
def quitar_etiqueta(puesto_id: int, db: Annotated[object, Depends(bd)]):
    db.execute("DELETE FROM etiqueta WHERE puesto_id = ?", [puesto_id])
    db.conn.commit()


# --- Mi lista ----------------------------------------------------------------------


@router.put("/{puesto_id}/guardado", response_model=Guardado)
def guardar(puesto_id: int, entrada: GuardadoEntrada, db: Annotated[object, Depends(bd)]):
    """Guarda el puesto en Mi lista o cambia lo que venga (estado, prioridad, notas, etiquetas).
    La primera vez cuenta además como «top» si aún no tenía etiqueta: guardar es la señal más clara de
    que algo gusta, y así la puntuación aprende de ello (y la criba no lo descarta)."""
    if not db.execute("SELECT 1 FROM puesto WHERE id = ?", [puesto_id]).fetchone():
        raise HTTPException(404, "No existe ese puesto")
    ahora = almacen.ahora()
    previo = db.execute("SELECT * FROM guardado WHERE puesto_id = ?", [puesto_id]).fetchone()
    previo = dict(previo) if previo else None
    estado = entrada.estado or (previo["estado"] if previo else "interesante")
    historial = json.loads(previo["historial"] or "[]") if previo else []
    if not historial or historial[-1]["estado"] != estado:
        historial.append({"estado": estado, "en": ahora})
    etiquetas = (sorted({t.strip() for t in entrada.etiquetas if t.strip()}) if entrada.etiquetas is not None
                 else json.loads(previo["etiquetas"] or "[]") if previo else [])
    fila = {"puesto_id": puesto_id, "estado": estado,
            "prioridad": entrada.prioridad if entrada.prioridad is not None else (previo or {}).get("prioridad", 0),
            "notas": entrada.notas if entrada.notas is not None else (previo or {}).get("notas"),
            "etiquetas": json.dumps(etiquetas, ensure_ascii=False), "historial": json.dumps(historial),
            "creado_en": (previo or {}).get("creado_en", ahora), "actualizado_en": ahora}
    db["guardado"].upsert(fila, pk="puesto_id")
    if previo is None:
        db.execute("""INSERT OR IGNORE INTO etiqueta (puesto_id, valor, motivo, creada_en, actualizada_en)
                      VALUES (?, 'top', 'Guardado en Mi lista', ?, ?)""", [puesto_id, ahora, ahora])
        db.execute("""UPDATE puesto SET descarte = NULL WHERE id = ?
                      AND (SELECT valor FROM etiqueta WHERE puesto_id = ?) = 'top'""", [puesto_id, puesto_id])
    db.conn.commit()
    return Guardado(**fila | {"etiquetas": etiquetas, "historial": historial})


@router.delete("/{puesto_id}/guardado", status_code=204)
def quitar_guardado(puesto_id: int, db: Annotated[object, Depends(bd)]):
    db.execute("DELETE FROM guardado WHERE puesto_id = ?", [puesto_id])
    db.conn.commit()


lista = APIRouter(prefix="/lista", tags=["lista"])


@lista.get("/etiquetas", response_model=dict[str, int])
def mis_etiquetas(db: Annotated[object, Depends(bd)]):
    """Las etiquetas propias que ya se usan, con cuántos puestos: para sugerirlas y filtrar."""
    return dict(db.execute("""SELECT j.value, COUNT(*) FROM guardado g, json_each(g.etiquetas) j
                              GROUP BY j.value ORDER BY COUNT(*) DESC, j.value""").fetchall())
