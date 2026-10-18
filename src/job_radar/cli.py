"""job-radar: la línea de órdenes del sistema.

    uv run job-radar ingesta            # lanza las búsquedas que tocan según su frecuencia
    uv run job-radar ingesta --todas    # todas, toque o no (cuidado con InfoJobs y la cuota de LinkedIn)
    uv run job-radar ingesta --fuente freehire
    uv run job-radar ingesta --puntuar  # y después puntúa los puestos nuevos que pasan la criba (--limite-puntuar N)
    uv run job-radar resumen            # ofertas y puestos por fuente, exclusividad y salud
    uv run job-radar salud              # solo las alertas; sale con 1 si hay alguna
    uv run job-radar copia              # copia de seguridad de la base (también al empezar cada ingesta)
    uv run job-radar renormalizar       # reinterpreta lo guardado con la versión actual de los conectores
    uv run job-radar cribar             # recalcula los descartes (tras cambiar las preferencias)
    uv run job-radar puntuar            # puntúa los puestos nuevos que pasan la criba
                                        #   (--etiquetados, --rehacer, --modelo, --paralelo, --limite)
    uv run job-radar recalcular         # rehace la nota sin llamar al modelo (p. ej. tras cambiar el salario)
    uv run job-radar medir              # acuerdo de la puntuación con las etiquetas (--rubrica)
"""

import argparse
import contextlib
import dataclasses
import fcntl
import logging
import logging.handlers
import math
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from job_radar import almacen, criba, empresas, ingesta, puestos, salud
from job_radar.fuentes import conector
from job_radar.fuentes import registro as reg
from job_radar.fuentes.base import Busqueda, cargar_env
from job_radar.preferencias import cargar as cargar_preferencias

RUTA_PREFERENCIAS = almacen.DATOS / "perfil" / "preferencias.yaml"
RUTA_LOG = almacen.DATOS / "logs" / "ingesta.log"
HOLGURA_H = 2  # una ejecución diaria a hora fija no debe saltarse un día por unos minutos
VENTANA_MAX_H = 30 * 24  # tras un parón largo no se pide más de un mes
COLGADA_H = 6  # una ejecución «en curso» desde hace más es que se interrumpió

log = logging.getLogger("job_radar")


def ultima_buena(db, busqueda_id: str) -> datetime | None:
    """Inicio de la última ejecución que trajo datos (ok o parcial). Un error no cuenta como hecha."""
    ultima = db.execute("SELECT MAX(inicio) FROM ejecucion WHERE busqueda_id = ? AND estado IN ('ok', 'parcial')",
                        [busqueda_id]).fetchone()[0]
    return datetime.fromisoformat(ultima) if ultima else None


def tocan(db, lista: list[Busqueda], ahora: datetime) -> list[Busqueda]:
    """Las búsquedas que tocan, cada una con su ventana: desde su última ejecución buena (no se pierden
    huecos si un día no corre o falla), como mínimo su frecuencia y como mucho VENTANA_MAX_H."""
    salida = []
    for b in lista:
        ultima = ultima_buena(db, b.id)
        if ultima is None:
            salida.append(b)
        elif ahora - ultima >= timedelta(hours=b.frecuencia_h - HOLGURA_H):
            hueco = math.ceil((ahora - ultima).total_seconds() / 3600)
            salida.append(dataclasses.replace(b, ventana_h=min(max(hueco, b.frecuencia_h), VENTANA_MAX_H)))
    return salida


def _lanzar_busquedas(db, lista: list[Busqueda], conectores: dict, tarea_id: int | None = None) -> None:
    for b in lista:  # una fuente caída no tumba las demás: `ejecutar` no lanza
        e = db["ejecucion"].get(ingesta.ejecutar(db, conectores[b.fuente], b, tarea_id))
        log.info("%-22s %-7s %4dh · recibidas %3d · nuevas %3d · errores %d%s", b.id, e["estado"], b.horas,
                 e["recibidos"], e["nuevos"], e["errores_norm"], f" · {e['error'][:120]}" if e["error"] else "")


def _despues(db, prefs) -> None:
    """Tras traer ofertas: agruparlas en puestos, cerrar lo caducado, enlazar empresas y pasar la criba."""
    log.info("puestos: %s", puestos.actualizar(db) or "sin cambios")
    log.info("cierre: %s", puestos.cerrar(db) or "nada que cerrar")
    log.info("empresas: %s", empresas.actualizar(db) or "sin cambios")
    log.info("criba: %s", dict(criba.aplicar(db, prefs)))


def cmd_tarea(args) -> int:
    """Una búsqueda a demanda lanzada desde la web (job_radar.tareas). Comparte cerrojo con la ingesta."""
    from job_radar import tareas

    db = almacen.abrir(args.db)
    t = db["tarea"].get(args.id)
    with cerrojo(args.db.parent / ".ingesta.lock") as libre:
        if not libre:
            tareas.guardar_resumen(db, args.id, "error", "ya había una búsqueda en marcha (la diaria u otra)")
            return 1
        db["tarea"].update(args.id, {"estado": "en_curso", "inicio": almacen.ahora(), "pid": os.getpid()})
        db.conn.commit()
        try:
            pedido = tareas.Pedido.model_validate_json(t["parametros"])
            registro = reg.cargar()
            conectores = {k: conector(f.conector) for k, f in registro.activas().items() if k in pedido.fuentes}
            prefs = cargar_preferencias(RUTA_PREFERENCIAS)
            lista = tareas.busquedas(pedido, args.id, prefs, registro, conectores)
            log.info("tarea %d (%s): %d búsquedas", args.id, pedido.modo, len(lista))
            _lanzar_busquedas(db, lista, conectores, args.id)
            _despues(db, prefs)
            codigo = 0
            if pedido.puntuar:
                codigo = cmd_puntuar(argparse.Namespace(db=args.db, etiquetados=False, rehacer=False,
                                                        modelo="sonnet", paralelo=3, limite=100))
            tareas.guardar_resumen(db, args.id, "ok", None if codigo == 0 else "la puntuación falló en parte")
            return codigo
        except Exception as e:
            tareas.guardar_resumen(db, args.id, "error", str(e)[:500])
            raise


def cerrar_colgadas(db, ahora: datetime) -> int:
    """Las ejecuciones que se quedaron «en curso» (Ctrl-C, proceso matado) pasan a error."""
    limite = (ahora - timedelta(hours=COLGADA_H)).isoformat(timespec="seconds")
    n = db.execute("""UPDATE ejecucion SET estado = 'error', fin = ?, error = 'interrumpida (quedó en curso)'
                      WHERE estado = 'en_curso' AND inicio < ?""", [ahora.isoformat(timespec="seconds"),
                                                                    limite]).rowcount
    db.conn.commit()
    return n


@contextlib.contextmanager
def cerrojo(ruta: Path):
    """Una sola ingesta a la vez (launchd, la mano y, en la Pi, el worker). Si ya hay una, se sale."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def cmd_ingesta(args) -> int:
    with cerrojo(args.db.parent / ".ingesta.lock") as libre:
        if not libre:
            log.warning("ingesta: ya hay otra en marcha; no se lanza")
            return 0
        _avisar_healthchecks("/start")
        try:
            codigo, alertas = _ingesta(args)
        except Exception as e:
            _avisar_healthchecks("/fail", f"la ingesta se cayó: {e}")
            raise
        # Al final, después de puntuar: un «ok» de Healthchecks quiere decir que todo el día fue bien.
        _avisar_healthchecks("/fail" if alertas or codigo else "", "\n".join(map(str, alertas)))
        return codigo


def _ingesta(args) -> int:
    db = almacen.abrir(args.db)
    if n := cerrar_colgadas(db, datetime.now(UTC)):
        log.warning("ingesta: %d ejecuciones colgadas pasan a error", n)
    log.info("copia: %s", almacen.copiar(db, args.db.parent / "copias").name)  # antes de cambiar nada
    registro = reg.cargar()
    activas = registro.activas()
    if args.fuente:
        activas = {k: v for k, v in activas.items() if k in args.fuente}
    conectores = {k: conector(f.conector) for k, f in activas.items()}
    prefs = cargar_preferencias(args.preferencias)
    lista = reg.busquedas(prefs, reg.Registro(fuentes=activas), conectores)
    reg.sincronizar(db, registro, lista)

    pendientes = lista if args.todas else tocan(db, lista, datetime.now(UTC))
    log.info("ingesta: %d de %d búsquedas tocan", len(pendientes), len(lista))
    _lanzar_busquedas(db, pendientes, conectores)
    _despues(db, prefs)
    codigo = 0
    if args.puntuar:
        codigo = cmd_puntuar(argparse.Namespace(db=args.db, etiquetados=False, rehacer=False, modelo="sonnet",
                                                paralelo=3, limite=args.limite_puntuar))
    alertas = salud.comprobar(db, registro)
    for a in alertas:
        log.warning("salud: %s", a)
    return codigo, alertas


def _avisar_healthchecks(sufijo: str = "", texto: str = "") -> None:
    """Ping a Healthchecks (si HEALTHCHECKS_URL está en .env). Sin Telegram, es el aviso de que algo falla:
    «/start» al empezar (detecta las que se cuelgan), y al final «ok» o «/fail» con las alertas."""
    url = os.environ.get("HEALTHCHECKS_URL")
    if not url:
        return
    try:
        httpx.post(url + sufijo, content=texto[:10000], timeout=10)
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


def cmd_puntuar(args) -> int:
    from job_radar import puntuacion
    from job_radar.llm import ClaudeCLI

    db = almacen.abrir(args.db)
    perfil_cv, prefs = puntuacion.cargar_perfil()
    if args.rehacer:
        filtro = "p.id IN (SELECT puesto_id FROM etiqueta)" if args.etiquetados else "p.descarte IS NULL"
        ids = [r[0] for r in db.execute(f"SELECT p.id FROM puesto p WHERE p.estado = 'abierto' AND {filtro}")]
    else:
        ids = puntuacion.pendientes(db, perfil_cv, prefs, args.etiquetados)
    if args.limite:
        ids = ids[: args.limite]
    log.info("puntuar: %d puestos con %s (%s)", len(ids), puntuacion.RUBRICA, args.modelo)

    def informar(pid, ev, error):
        if error:
            log.warning("puesto %s: %s", pid, error)
        else:
            e = db["evaluacion"].get(ev)
            log.info("puesto %-5s nota %3d%s", pid, e["nota"], f" · vetado: {e['motivo_veto']}" if e["vetado"] else "")

    motor = ClaudeCLI(modelo=args.modelo, timeout_s=300)
    hechos = puntuacion.evaluar_varios(db, ids, motor, perfil_cv, prefs, paralelo=args.paralelo,
                                       al_terminar=informar)
    if ids and len(hechos) < len(ids) / 2:  # p. ej. `claude` sin sesión o sin cuota: que se note
        log.error("puntuar: fallaron %d de %d puestos", len(ids) - len(hechos), len(ids))
        return 1
    return 0


def cmd_medir(args) -> int:
    from job_radar import medir

    from job_radar.puntuacion import RUBRICA

    print(medir.informe(almacen.abrir(args.db), args.rubrica or RUBRICA))
    return 0


def cmd_renormalizar(args) -> int:
    db = almacen.abrir(args.db)
    registro = reg.cargar()
    for fuente_id, f in registro.activas().items():
        if args.fuente and fuente_id not in args.fuente:
            continue
        print(f"{fuente_id:10} {dict(ingesta.renormalizar(db, conector(f.conector)))}")
    print("puestos:", puestos.actualizar(db) or "sin cambios")
    print("cierre:", puestos.cerrar(db) or "nada que cerrar")
    print("empresas:", empresas.actualizar(db) or "sin cambios")
    print("criba:", dict(criba.aplicar(db, cargar_preferencias(RUTA_PREFERENCIAS))))
    return 0


def cmd_copia(args) -> int:
    print(almacen.copiar(almacen.abrir(args.db), args.db.parent / "copias"))
    return 0


def cmd_cribar(args) -> int:
    cuenta = criba.aplicar(almacen.abrir(args.db), cargar_preferencias(args.preferencias))
    print("\n".join(f"{n:5} {motivo}" for motivo, n in cuenta.most_common()))
    return 0


def cmd_recalcular(args) -> int:
    from job_radar import puntuacion

    n = puntuacion.recalcular(almacen.abrir(args.db), cargar_preferencias(args.preferencias))
    print(f"{n} evaluaciones cambian")
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
    p.add_argument("--puntuar", action="store_true", help="después, puntúa los puestos nuevos")
    p.add_argument("--limite-puntuar", type=int, default=150, help="tope de puestos a puntuar por ejecución")
    p.set_defaults(func=cmd_ingesta)
    p = sub.add_parser("resumen", help="ofertas y puestos por fuente, exclusividad y salud")
    p.add_argument("--dias", type=int, default=7)
    p.set_defaults(func=cmd_resumen)
    sub.add_parser("salud", help="alertas de las fuentes").set_defaults(func=cmd_salud)
    sub.add_parser("copia", help="copia de seguridad de la base").set_defaults(func=cmd_copia)
    p = sub.add_parser("tarea", help="ejecuta una búsqueda a demanda creada desde la web")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_tarea)
    p = sub.add_parser("renormalizar", help="reinterpreta las ofertas guardadas con los conectores actuales")
    p.add_argument("--fuente", action="append", help="solo esta fuente (se puede repetir)")
    p.set_defaults(func=cmd_renormalizar)
    p = sub.add_parser("cribar", help="recalcula qué puestos se descartan sin puntuar")
    p.add_argument("--preferencias", type=Path, default=RUTA_PREFERENCIAS)
    p.set_defaults(func=cmd_cribar)
    p = sub.add_parser("recalcular", help="rehace la nota sin llamar al modelo (salario)")
    p.add_argument("--preferencias", type=Path, default=RUTA_PREFERENCIAS)
    p.set_defaults(func=cmd_recalcular)
    p = sub.add_parser("puntuar", help="evalúa puestos contra el perfil (Fase 4)")
    p.add_argument("--etiquetados", action="store_true", help="solo los que Rubén ha etiquetado")
    p.add_argument("--rehacer", action="store_true", help="también los ya evaluados con esta rúbrica")
    p.add_argument("--modelo", default="sonnet")
    p.add_argument("--paralelo", type=int, default=3)
    p.add_argument("--limite", type=int)
    p.set_defaults(func=cmd_puntuar)
    p = sub.add_parser("medir", help="acuerdo de la puntuación con las etiquetas")
    p.add_argument("--rubrica", help="por defecto, la vigente")
    p.set_defaults(func=cmd_medir)
    args = ap.parse_args(argv)

    cargar_env()
    RUTA_LOG.parent.mkdir(parents=True, exist_ok=True)
    # Un fichero por día, 30 días: en la Pi los logs no pueden crecer sin control.
    rotado = logging.handlers.TimedRotatingFileHandler(RUTA_LOG, when="midnight", backupCount=30, encoding="utf-8")
    # Por pantalla solo si hay alguien mirando: con launchd o Docker, el log ya está en el fichero.
    pantalla = [logging.StreamHandler()] if sys.stderr.isatty() else []
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[*pantalla, rotado])
    for ruidoso in ("httpx", "httpcore", "JobSpy"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
