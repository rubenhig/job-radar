"""Salud de las fuentes: enterarse el mismo día si una cae, cambia de formato o se queda sin cuota.

Las reglas son las de docs/modelo.md#monitorización y solo leen el almacén:
cada ejecución ya deja sus métricas. Que la ingesta haya corrido lo vigila
Healthchecks desde fuera, si HEALTHCHECKS_URL está en .env (#39); aquí se
comprueba que cada fuente activa ha corrido según su frecuencia y que la
puntuación no se ha atascado (puestos sin nota tras ATASCO_H).

Uso:
    uv run python -m job_radar.salud
"""

import argparse
import json
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from job_radar import almacen
from job_radar.fuentes import registro as reg

VOLUMEN_MIN = 0.3        # recibidos frente a la mediana de 7 días
ERRORES_MAX = 0.05       # brutos sin normalizar
FRESCURA_DIAS = 3        # la oferta más reciente
CUOTA_MIN = 0.2          # cuota restante
COMPLETITUD_CAIDA = 0.5  # un campo por debajo de la mitad de su línea base…
COMPLETITUD_BASE = 20    # …si la línea base es de al menos un 20 %
RETRASO = 1.5            # una fuente "no ha corrido" si pasa 1,5 veces su frecuencia
ATASCO_H = 36            # un puesto que pasa la criba y sigue sin nota tras esto: la puntuación no va


@dataclass
class Alerta:
    fuente: str
    senal: str
    mensaje: str

    def __str__(self) -> str:
        return f"[{self.fuente}] {self.senal}: {self.mensaje}"


def _fecha(texto: str) -> datetime:
    f = datetime.fromisoformat(texto)
    return f if f.tzinfo else f.replace(tzinfo=UTC)


def cuota_restante(cuota: dict) -> dict[str, float]:
    """Cabeceras `x-ratelimit-<cosa>-remaining` y `-limit` → fracción restante por cosa."""
    salida = {}
    for clave, valor in cuota.items():
        if clave.endswith("-remaining"):
            base = clave.removesuffix("-remaining")
            limite = cuota.get(f"{base}-limit")
            try:
                salida[base.removeprefix("x-ratelimit-")] = float(valor) / float(limite)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
    return salida


def comprobar(db, registro: reg.Registro, ahora: datetime | None = None) -> list[Alerta]:
    ahora = ahora or datetime.now(UTC)
    alertas = []
    for fuente_id, fuente in registro.activas().items():
        ejecuciones = [dict(r) for r in db.query(
            # las búsquedas puntuales (tareas desde la web) no cuentan para la salud de la fuente
            """SELECT * FROM ejecucion WHERE fuente_id = ? AND fin IS NOT NULL
               AND (tarea_id IS NULL OR busqueda_id NOT GLOB '*:t[0-9]*') ORDER BY inicio DESC""", [fuente_id])]
        if not ejecuciones:
            alertas.append(Alerta(fuente_id, "no ha corrido", "ninguna ejecución registrada"))
            continue
        ultima = ejecuciones[0]
        if ahora - _fecha(ultima["inicio"]) > timedelta(hours=fuente.frecuencia_h * RETRASO):
            alertas.append(Alerta(fuente_id, "no ha corrido", f"la última fue el {ultima['inicio'][:16]}"))

        # La última tanda: la ejecución más reciente de cada búsqueda, si es de su último periodo.
        # Cada búsqueda con su frecuencia: la semanal de remoto no se cae de la tanda a las 36 h.
        frecuencia = dict(db.execute("SELECT id, frecuencia_h FROM busqueda WHERE fuente_id = ?", [fuente_id]))
        tanda = {}
        for e in ejecuciones:
            horas = frecuencia.get(e["busqueda_id"]) or fuente.frecuencia_h
            if e["busqueda_id"] not in tanda and ahora - _fecha(e["inicio"]) <= timedelta(hours=horas * RETRASO):
                tanda[e["busqueda_id"]] = e
        for e in tanda.values():
            if e["estado"] == "error":
                alertas.append(Alerta(fuente_id, "error", f"{e['busqueda_id']}: {(e['error'] or '')[:200]}"))
            if e["recibidos"] and e["errores_norm"] / e["recibidos"] > ERRORES_MAX:
                alertas.append(Alerta(fuente_id, "errores de normalización",
                                      f"{e['busqueda_id']}: {e['errores_norm']} de {e['recibidos']}"))

        # Volumen y completitud, por búsqueda, frente a las ejecuciones de los 7 días anteriores.
        hace_7 = ahora - timedelta(days=7)
        for busqueda_id, e in tanda.items():
            previas = [x for x in ejecuciones if x["busqueda_id"] == busqueda_id and x["id"] != e["id"]
                       and _fecha(x["inicio"]) >= hace_7 and x["estado"] != "error"]
            if not previas or e["estado"] == "error":
                continue
            mediana = statistics.median(x["recibidos"] for x in previas)
            if mediana and e["recibidos"] < VOLUMEN_MIN * mediana:
                alertas.append(Alerta(fuente_id, "volumen",
                                      f"{busqueda_id}: {e['recibidos']} recibidas (mediana de 7 días: {mediana:g})"))
            actual = json.loads(e["completitud"] or "{}")
            bases = [json.loads(x["completitud"]) for x in previas if x["completitud"]]
            for campo, pct in actual.items():
                base = statistics.median(b.get(campo, 0) for b in bases) if bases else 0
                if base >= COMPLETITUD_BASE and pct < COMPLETITUD_CAIDA * base:
                    alertas.append(Alerta(fuente_id, "completitud",
                                          f"{busqueda_id}: «{campo}» en el {pct} % (lo normal, {base:g} %)"))

        reciente = db.execute("SELECT MAX(publicada_en) FROM oferta WHERE fuente_id = ?", [fuente_id]).fetchone()[0]
        if reciente and ahora - _fecha(reciente) > timedelta(days=FRESCURA_DIAS):
            alertas.append(Alerta(fuente_id, "frescura", f"la oferta más reciente es del {reciente[:10]}"))

        if ultima["cuota"]:
            for cosa, fraccion in cuota_restante(json.loads(ultima["cuota"])).items():
                if fraccion < CUOTA_MIN:
                    alertas.append(Alerta(fuente_id, "cuota", f"queda el {fraccion:.0%} de «{cosa}»"))
    return alertas + puntuacion_atascada(db, ahora)


def puntuacion_atascada(db, ahora: datetime) -> list[Alerta]:
    """Puestos visibles sin ninguna nota desde hace más de ATASCO_H: `claude` sin sesión, sin cuota…"""
    if "evaluacion" not in db.table_names():
        return []
    limite = (ahora - timedelta(hours=ATASCO_H)).isoformat(timespec="seconds")
    n = db.execute("""SELECT COUNT(*) FROM puesto p WHERE p.estado = 'abierto' AND p.descarte IS NULL
                      AND p.id NOT IN (SELECT puesto_id FROM evaluacion)
                      AND (SELECT MIN(vista_primera) FROM oferta o WHERE o.puesto_id = p.id) < ?""",
                   [limite]).fetchone()[0]
    return [Alerta("puntuacion", "atascada", f"{n} puestos llevan más de {ATASCO_H} h sin nota")] if n else []


def exclusividad(db, dias: int = 30) -> dict[str, dict[str, float]]:
    """Por fuente: puestos que trae y cuántos solo trae ella. Decide si sigue mereciendo la pena."""
    desde = (datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="seconds")
    filas = db.execute("""
        SELECT o.fuente_id, o.puesto_id, (SELECT COUNT(DISTINCT x.fuente_id) FROM oferta x
                                          WHERE x.puesto_id = o.puesto_id) AS fuentes
        FROM oferta o WHERE o.puesto_id IS NOT NULL AND o.vista_ultima >= ?
        GROUP BY o.fuente_id, o.puesto_id""", [desde]).fetchall()
    salida = {}
    for fuente, _, fuentes in filas:
        s = salida.setdefault(fuente, {"puestos": 0, "exclusivos": 0})
        s["puestos"] += 1
        s["exclusivos"] += fuentes == 1
    for s in salida.values():
        s["pct_exclusivos"] = round(100 * s["exclusivos"] / s["puestos"])
    return salida


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=almacen.RUTA_DB)
    args = ap.parse_args()
    db = almacen.abrir(args.db)
    alertas = comprobar(db, reg.cargar())
    print("\n".join(map(str, alertas)) or "Todas las fuentes, bien.")
    print("\nExclusividad (30 días):")
    for fuente, s in sorted(exclusividad(db).items()):
        print(f"  {fuente:10} {s['puestos']:5} puestos · {s['pct_exclusivos']:3} % solo aquí")
    raise SystemExit(1 if alertas else 0)


if __name__ == "__main__":
    main()
