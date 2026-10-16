"""¿Piensa la puntuación como Rubén? Acuerdo con sus etiquetas top / no top.

Con pocas etiquetas es fácil engañarse: el umbral de "top" se elige con
validación dejando uno fuera (cada puesto se predice con un umbral elegido sin
él), y esa es la cifra honesta. Se informa también del κ de Cohen, que descuenta
el acuerdo que saldría por azar.
"""

import json
from dataclasses import dataclass

from job_radar.puntuacion import RUBRICA

UMBRALES = range(0, 101)


@dataclass
class Caso:
    puesto_id: int
    titulo: str
    etiqueta: bool          # top según Rubén
    motivo: str | None
    nota: int
    vetado: bool
    resumen: str
    explicacion: str
    coste_usd: float | None


def casos(db, rubrica: str = RUBRICA) -> list[Caso]:
    """La última evaluación de cada puesto etiquetado, con esta rúbrica."""
    filas = db.query("""
        SELECT e.puesto_id, p.titulo, et.valor, et.motivo, e.nota, e.vetado, e.motivo_veto, e.resultado, e.coste_usd
        FROM evaluacion e JOIN etiqueta et ON et.puesto_id = e.puesto_id JOIN puesto p ON p.id = e.puesto_id
        WHERE e.rubrica = ? AND e.id = (SELECT MAX(id) FROM evaluacion x WHERE x.puesto_id = e.puesto_id
                                         AND x.rubrica = e.rubrica)""", [rubrica])
    salida = []
    for f in filas:
        r = json.loads(f["resultado"])
        v = r["veredictos"]
        explicacion = f["motivo_veto"] or (f"rol {v['rol_ia']['valor']}, función {v['funcion']['valor']}, "
                                           f"requisitos {r['parciales']['requisitos']:.0%}, "
                                           f"seniority {v['seniority']['valor']}, fuente {v['fuente']['valor']}")
        salida.append(Caso(f["puesto_id"], f["titulo"], f["valor"] == "top", f["motivo"], f["nota"], bool(f["vetado"]),
                           v["resumen"], explicacion, f["coste_usd"]))
    return salida


def acierto(cs: list[Caso], umbral: int) -> float:
    return sum((c.nota >= umbral) == c.etiqueta for c in cs) / len(cs)


def mejor_umbral(cs: list[Caso]) -> int:
    """El que más acierta; a igualdad, el del centro del tramo empatado (más robusto)."""
    puntos = [acierto(cs, u) for u in UMBRALES]
    maximo = max(puntos)
    empatados = [u for u, a in zip(UMBRALES, puntos) if a == maximo]
    return empatados[len(empatados) // 2]


def kappa(cs: list[Caso], umbral: int) -> float:
    n = len(cs)
    po = acierto(cs, umbral)
    p_top_r = sum(c.etiqueta for c in cs) / n
    p_top_c = sum(c.nota >= umbral for c in cs) / n
    pe = p_top_r * p_top_c + (1 - p_top_r) * (1 - p_top_c)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def dejando_uno_fuera(cs: list[Caso]) -> float:
    return sum((c.nota >= mejor_umbral(cs[:i] + cs[i + 1:])) == c.etiqueta for i, c in enumerate(cs)) / len(cs)


def informe(db, rubrica: str = RUBRICA) -> str:
    cs = casos(db, rubrica)
    if len(cs) < 5:
        return f"Solo hay {len(cs)} puestos etiquetados y evaluados con {rubrica}: hacen falta al menos 5."
    u = mejor_umbral(cs)
    vp = sum(c.etiqueta and c.nota >= u for c in cs)
    fn = sum(c.etiqueta and c.nota < u for c in cs)
    fp = sum(not c.etiqueta and c.nota >= u for c in cs)
    vn = sum(not c.etiqueta and c.nota < u for c in cs)
    coste = sum(c.coste_usd or 0 for c in cs)
    lineas = [
        f"{rubrica} · {len(cs)} puestos ({vp + fn} top y {fp + vn} no top según Rubén)",
        f"Umbral de top: {u} · acuerdo {acierto(cs, u):.0%} · κ {kappa(cs, u):.2f}",
        f"Acuerdo dejando uno fuera (la cifra honesta): {dejando_uno_fuera(cs):.0%}",
        "",
        "                    Claude top   Claude no top",
        f"  Rubén top         {vp:10}   {fn:13}",
        f"  Rubén no top      {fp:10}   {vn:13}",
        "",
        f"Coste (equivalente en API): {coste:.2f} $ · {coste / len(cs):.3f} $ por puesto",
        "",
        "Desacuerdos:",
    ]
    for c in sorted(cs, key=lambda c: -c.nota):
        if (c.nota >= u) != c.etiqueta:
            quien = "Rubén top, Claude no" if c.etiqueta else "Claude top, Rubén no"
            lineas.append(f"  [{quien}] {c.nota:3} · {c.titulo[:60]}")
            lineas.append(f"      Claude: {c.explicacion}")
            if c.motivo:
                lineas.append(f"      Rubén: {c.motivo.strip()}")
    lineas += ["", "Todas las notas:"]
    lineas += [f"  {'✓' if (c.nota >= u) == c.etiqueta else '✗'} {c.nota:3} {'top' if c.etiqueta else 'no ':3}"
               f"  {c.titulo[:70]}" for c in sorted(cs, key=lambda c: -c.nota)]
    return "\n".join(lineas)
