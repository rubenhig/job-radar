"""Portada, fuentes y perfil: lo que no es un puesto."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Depends, HTTPException

from job_radar import criba, salud
from job_radar.api.base import bd, datos
from job_radar.api.esquemas import Acuerdo, Alerta, CasoAcuerdo, EstadoFuente, Fuentes, Resumen
from job_radar.fuentes import registro as reg
from job_radar.preferencias import Preferencias

router = APIRouter()


def _hace(**delta) -> str:
    return (datetime.now(UTC) - timedelta(**delta)).isoformat(timespec="seconds")


@router.get("/resumen", response_model=Resumen, tags=["sistema"])
def resumen(db: Annotated[Any, Depends(bd)]):
    uno = lambda sql, *a: db.execute(sql, a).fetchone()[0]  # noqa: E731
    primera = "SELECT puesto_id FROM oferta GROUP BY puesto_id HAVING MIN(vista_primera) >= ?"
    return Resumen(
        puestos=uno("SELECT COUNT(*) FROM puesto WHERE estado = 'abierto' AND descarte IS NULL"),
        descartados=uno("SELECT COUNT(*) FROM puesto WHERE estado = 'abierto' AND descarte IS NOT NULL"),
        puestos_nuevos_24h=uno(f"SELECT COUNT(*) FROM ({primera})", _hace(days=1)),
        puestos_nuevos_7d=uno(f"SELECT COUNT(*) FROM ({primera})", _hace(days=7)),
        ofertas=uno("SELECT COUNT(*) FROM oferta"),
        varias_vias=uno("""SELECT COUNT(*) FROM (SELECT puesto_id FROM oferta WHERE puesto_id IS NOT NULL
                           GROUP BY puesto_id HAVING COUNT(*) > 1)"""),
        etiquetados=uno("SELECT COUNT(*) FROM etiqueta"),
        etiquetados_top=uno("SELECT COUNT(*) FROM etiqueta WHERE valor = 'top'"),
        por_fuente=dict(db.execute("SELECT fuente_id, COUNT(*) FROM oferta GROUP BY 1").fetchall()),
        alertas=len(salud.comprobar(db, reg.cargar())),
    )


@router.get("/fuentes", response_model=Fuentes, tags=["sistema"])
def fuentes(db: Annotated[Any, Depends(bd)]):
    hace_7, inicio_mes = _hace(days=7), datetime.now(UTC).strftime("%Y-%m-01")
    salida = []
    for f in db.query("SELECT * FROM fuente ORDER BY id"):
        ultima = next(iter(db.query("SELECT * FROM ejecucion WHERE fuente_id = ? ORDER BY inicio DESC LIMIT 1",
                                    [f["id"]])), None)
        suma = db.execute("""SELECT COALESCE(SUM(recibidos), 0), COALESCE(SUM(nuevos), 0) FROM ejecucion
                             WHERE fuente_id = ? AND inicio >= ?""", [f["id"], hace_7]).fetchone()
        salida.append(EstadoFuente(
            id=f["id"], tipo=f["tipo"], conector=f["conector"], activa=bool(f["activa"]),
            ultima_ejecucion=ultima and ultima["inicio"], ultimo_estado=ultima and ultima["estado"],
            recibidas_7d=suma[0], nuevas_7d=suma[1],
            oferta_mas_reciente=db.execute("SELECT MAX(publicada_en) FROM oferta WHERE fuente_id = ?",
                                           [f["id"]]).fetchone()[0],
            cuota=json.loads(ultima["cuota"]) if ultima and ultima["cuota"] else None,
            coste_mes_usd=db.execute("SELECT SUM(coste_usd) FROM ejecucion WHERE fuente_id = ? AND inicio >= ?",
                                     [f["id"], inicio_mes]).fetchone()[0]))
    alertas = [Alerta(fuente=a.fuente, senal=a.senal, mensaje=a.mensaje) for a in salud.comprobar(db, reg.cargar())]
    return Fuentes(fuentes=salida, alertas=alertas)


def _yaml(ruta: Path) -> dict:
    if not ruta.exists():
        raise HTTPException(404, f"No existe {ruta.name}")
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


@router.get("/perfil", tags=["perfil"])
def perfil(carpeta: Annotated[Path, Depends(datos)]) -> dict[str, Any]:
    """El perfil extraído del CV (`perfil_cv.yaml`): meta y competencias con sus citas."""
    return _yaml(carpeta / "perfil" / "perfil_cv.yaml")


@router.get("/preferencias", response_model=Preferencias, tags=["perfil"])
def leer_preferencias(carpeta: Annotated[Path, Depends(datos)]):
    return Preferencias.model_validate(_yaml(carpeta / "perfil" / "preferencias.yaml"))


@router.put("/preferencias", response_model=Preferencias, tags=["perfil"])
def guardar_preferencias(nuevas: Preferencias, carpeta: Annotated[Path, Depends(datos)],
                         db: Annotated[Any, Depends(bd)]):
    """Guarda las preferencias (ya validadas) y rehace la criba con ellas.
    La versión anterior queda en `preferencias.anterior.yaml`."""
    ruta = carpeta / "perfil" / "preferencias.yaml"
    if ruta.exists():
        ruta.with_name("preferencias.anterior.yaml").write_text(ruta.read_text(encoding="utf-8"), encoding="utf-8")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(yaml.safe_dump(nuevas.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
                    encoding="utf-8")
    criba.aplicar(db, nuevas)
    return nuevas


@router.get("/acuerdo", response_model=Acuerdo, tags=["puntuacion"])
def acuerdo(db: Annotated[Any, Depends(bd)]):
    """La puntuación frente a las etiquetas de Rubén (ver job_radar.medir)."""
    from job_radar import medir
    from job_radar.puntuacion import RUBRICA

    cs = medir.casos(db, RUBRICA)
    salida = Acuerdo(rubrica=RUBRICA, casos=[], coste_usd=round(sum(c.coste_usd or 0 for c in cs), 4))
    if len(cs) >= 5:
        u = medir.mejor_umbral(cs)
        salida.umbral, salida.acuerdo = u, medir.acierto(cs, u)
        salida.kappa, salida.dejando_uno_fuera = round(medir.kappa(cs, u), 3), medir.dejando_uno_fuera(cs)
    u = salida.umbral or 50
    salida.casos = [CasoAcuerdo(puesto_id=c.puesto_id, titulo=c.titulo, etiqueta="top" if c.etiqueta else "no_top",
                                nota=c.nota, vetado=c.vetado, acierto=(c.nota >= u) == c.etiqueta,
                                explicacion=c.explicacion, motivo=c.motivo)
                    for c in sorted(cs, key=lambda c: -c.nota)]
    return salida
