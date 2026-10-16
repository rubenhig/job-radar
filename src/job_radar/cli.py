"""job-radar: la línea de órdenes del sistema.

    uv run job-radar ingesta            # lanza las búsquedas que tocan según su frecuencia
    uv run job-radar ingesta --todas    # todas, toque o no (cuidado con InfoJobs y la cuota de LinkedIn)
    uv run job-radar ingesta --fuente freehire
    uv run job-radar resumen            # ofertas y puestos por fuente, exclusividad y salud
    uv run job-radar salud              # solo las alertas; sale con 1 si hay alguna
"""

import argparse
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from job_radar import almacen, ingesta, puestos, salud
from job_radar.fuentes import conector
from job_radar.fuentes import registro as reg
from job_radar.fuentes.base import Busqueda, cargar_env
from job_radar.preferencias import cargar as cargar_preferencias

RUTA_PREFERENCIAS = almacen.RAIZ / "data" / "perfil" / "preferencias.yaml"
RUTA_LOG = almacen.RAIZ / "data" / "logs" / "ingesta.log"
HOLGURA_H = 2  # una ejecución diaria a hora fija no debe saltarse un día por unos minutos

log = logging.getLogger("job_radar")


def tocan(db, lista: list[Busqueda], ahora: datetime) -> list[Busqueda]:
    """Las búsquedas cuya última ejecución es más antigua que su frecuencia."""
    salida = []
    for b in lista:
        ultima = db.execute("SELECT MAX(inicio) FROM ejecucion WHERE busqueda_id = ?", [b.id]).fetchone()[0]
        if ultima is None or ahora - datetime.fromisoformat(ultima) >= timedelta(hours=b.frecuencia_h - HOLGURA_H):
            salida.append(b)
    return salida


def cmd_ingesta(args) -> int:
    db = almacen.abrir(args.db)
    registro = reg.cargar()
    activas = registro.activas()
    if args.fuente:
        activas = {k: v for k, v in activas.items() if k in args.fuente}
    conectores = {k: conector(f.conector) for k, f in activas.items()}
    lista = reg.busquedas(cargar_preferencias(args.preferencias), reg.Registro(fuentes=activas), conectores)
    reg.sincronizar(db, registro, lista)

    pendientes = lista if args.todas else tocan(db, lista, datetime.now(UTC))
    log.info("ingesta: %d de %d búsquedas tocan", len(pendientes), len(lista))
    for b in pendientes:  # una fuente caída no tumba las demás: `ejecutar` no lanza
        e = db["ejecucion"].get(ingesta.ejecutar(db, conectores[b.fuente], b))
        log.info("%-22s %-7s recibidas %3d · nuevas %3d · errores %d%s", b.id, e["estado"], e["recibidos"],
                 e["nuevos"], e["errores_norm"], f" · {e['error'][:120]}" if e["error"] else "")
    log.info("puestos: %s", puestos.actualizar(db) or "sin cambios")

    alertas = salud.comprobar(db, registro)
    for a in alertas:
        log.warning("salud: %s", a)
    _avisar_healthchecks(alertas)
    return 0


def _avisar_healthchecks(alertas) -> None:
    """Ping a Healthchecks (si HEALTHCHECKS_URL está en .env): avisa si la ingesta deja de correr."""
    url = os.environ.get("HEALTHCHECKS_URL")
    if not url:
        return
    try:
        httpx.post(url + ("/fail" if alertas else ""), content="\n".join(map(str, alertas))[:10000], timeout=10)
    except httpx.HTTPError as e:
        log.warning("healthchecks: %s", e)


def cmd_resumen(args) -> int:
    db = almacen.abrir(args.db)
    desde = (datetime.now(UTC) - timedelta(days=args.dias)).isoformat(timespec="seconds")
    print(f"Últimos {args.dias} días\n")
    print(f"{'fuente':10} {'ejecuc.':>7} {'errores':>7} {'ofertas':>8} {'nuevas':>7} {'puestos':>8}")
    for f in db.query("""
        SELECT f.id,
               (SELECT COUNT(*) FROM ejecucion e WHERE e.fuente_id = f.id AND e.inicio >= :d) AS ejecuciones,
               (SELECT COUNT(*) FROM ejecucion e WHERE e.fuente_id = f.id AND e.inicio >= :d
                  AND e.estado = 'error') AS errores,
               (SELECT COUNT(*) FROM oferta o WHERE o.fuente_id = f.id AND o.vista_ultima >= :d) AS ofertas,
               (SELECT COUNT(*) FROM oferta o WHERE o.fuente_id = f.id AND o.vista_primera >= :d) AS nuevas,
               (SELECT COUNT(DISTINCT puesto_id) FROM oferta o WHERE o.fuente_id = f.id AND o.vista_ultima >= :d)
                  AS puestos
        FROM fuente f WHERE f.activa ORDER BY f.id""", {"d": desde}):
        print(f"{f['id']:10} {f['ejecuciones']:7} {f['errores']:7} {f['ofertas']:8} {f['nuevas']:7} {f['puestos']:8}")
    total = db.execute("SELECT COUNT(*), COUNT(DISTINCT puesto_id) FROM oferta WHERE vista_ultima >= ?",
                       [desde]).fetchone()
    varias = db.execute("""SELECT COUNT(*) FROM (SELECT puesto_id FROM oferta WHERE vista_ultima >= ?
                           GROUP BY puesto_id HAVING COUNT(DISTINCT fuente_id) > 1)""", [desde]).fetchone()[0]
    print(f"\n{total[0]} ofertas → {total[1]} puestos ({varias} llegan por más de una fuente)")
    print("\nExclusividad (puestos que solo trae cada fuente):")
    for fuente, s in sorted(salud.exclusividad(db, args.dias).items()):
        print(f"  {fuente:10} {s['exclusivos']:4} de {s['puestos']:4} ({s['pct_exclusivos']} %)")
    alertas = salud.comprobar(db, reg.cargar())
    print("\nSalud:\n  " + ("\n  ".join(map(str, alertas)) or "todas las fuentes, bien"))
    return 0


def cmd_salud(args) -> int:
    alertas = salud.comprobar(almacen.abrir(args.db), reg.cargar())
    print("\n".join(map(str, alertas)) or "Todas las fuentes, bien.")
    return 1 if alertas else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="job-radar", description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=almacen.RUTA_DB)
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("ingesta", help="lanza las búsquedas que tocan")
    p.add_argument("--todas", action="store_true", help="todas, toque o no")
    p.add_argument("--fuente", action="append", help="solo esta fuente (se puede repetir)")
    p.add_argument("--preferencias", type=Path, default=RUTA_PREFERENCIAS)
    p.set_defaults(func=cmd_ingesta)
    p = sub.add_parser("resumen", help="ofertas y puestos por fuente, exclusividad y salud")
    p.add_argument("--dias", type=int, default=7)
    p.set_defaults(func=cmd_resumen)
    sub.add_parser("salud", help="alertas de las fuentes").set_defaults(func=cmd_salud)
    args = ap.parse_args(argv)

    cargar_env()
    RUTA_LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(RUTA_LOG, encoding="utf-8")])
    for ruidoso in ("httpx", "httpcore", "JobSpy"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
