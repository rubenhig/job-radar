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
    assert tocan(db, [diaria, semanal, nueva], ahora) == [diaria, nueva]
