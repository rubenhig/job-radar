from datetime import UTC, datetime, timedelta

from job_radar import almacen
from job_radar.cli import tocan
from job_radar.fuentes import Busqueda


def test_tocan_segun_frecuencia_con_holgura(tmp_path):
    db = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(db, "f", "portal", "f/1")
    ahora = datetime(2026, 10, 20, 8, 30, tzinfo=UTC)
    diaria, semanal, nueva = (Busqueda("f:a", "f", {}, 24), Busqueda("f:b", "f", {}, 168), Busqueda("f:c", "f", {}, 24))
    for b, hace in ((diaria, timedelta(hours=23, minutes=50)), (semanal, timedelta(days=2))):
        almacen.guardar_busqueda(db, b.id, "f", {}, b.frecuencia_h)
        db["ejecucion"].insert({"fuente_id": "f", "busqueda_id": b.id, "conector": "f/1",
                                "inicio": (ahora - hace).isoformat(), "estado": "ok"})
    assert [(b.id, b.horas) for b in tocan(db, [diaria, semanal, nueva], ahora)] == [("f:a", 24), ("f:c", 24)]


def test_tocan_recupera_huecos_y_no_da_por_hecho_un_error(tmp_path):
    db = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(db, "f", "portal", "f/1")
    ahora = datetime(2026, 10, 20, 8, 30, tzinfo=UTC)
    b = Busqueda("f:a", "f", {}, 24)
    almacen.guardar_busqueda(db, b.id, "f", {}, 24)
    for hace, estado in ((timedelta(days=3), "ok"), (timedelta(hours=2), "error")):
        db["ejecucion"].insert({"fuente_id": "f", "busqueda_id": b.id, "conector": "f/1",
                                "inicio": (ahora - hace).isoformat(), "estado": estado})
    [toca] = tocan(db, [b], ahora)  # el error de hace 2 h no cuenta: se reintenta
    assert toca.horas == 72         # y pide los 3 días desde la última buena, no solo 24 h


def test_ingesta_no_se_solapa(tmp_path):
    from job_radar.cli import cerrojo

    with cerrojo(tmp_path / ".ingesta.lock") as primera:
        with cerrojo(tmp_path / ".ingesta.lock") as segunda:
            assert primera and not segunda
