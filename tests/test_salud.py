import json
from datetime import UTC, datetime, timedelta

import pytest

from job_radar import almacen, salud
from job_radar.fuentes import registro as reg

AHORA = datetime(2026, 10, 20, 9, tzinfo=UTC)
REGISTRO = reg.Registro.model_validate({"fuentes": {"f": {
    "tipo": "portal", "conector": "f/1", "acceso": "-", "coste": "-", "terminos": "-",
    "frecuencia_h": 24, "plan_b": ["otra"]}}})
NORMAL = {"titulo": 100, "descripcion": 95, "salario_min": 40}


@pytest.fixture
def db(tmp_path):
    d = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(d, "f", "portal", "f/1")
    almacen.guardar_busqueda(d, "f:malaga", "f", {}, 24)
    return d


def ejecucion(db, dias_atras, recibidos=50, completitud=NORMAL, **campos):
    inicio = (AHORA - timedelta(days=dias_atras)).isoformat()
    db["ejecucion"].insert({"fuente_id": "f", "busqueda_id": "f:malaga", "conector": "f/1", "inicio": inicio,
                            "fin": inicio, "estado": "ok", "recibidos": recibidos, "nuevos": 5,
                            "completitud": json.dumps(completitud)} | campos)


def historia(db, **ultima):
    for d in range(7, 0, -1):
        ejecucion(db, d)
    ejecucion(db, 0.1, **ultima)


def senales(db):
    return {a.senal for a in salud.comprobar(db, REGISTRO, AHORA)}


def test_todo_bien(db):
    historia(db)
    almacen.guardar_bruto(db, 1, "f", "1", {})
    db["oferta"].insert({"fuente_id": "f", "id_externo": "1", "bruto_id": 1, "conector": "f/1", "titulo": "x",
                         "publicada_en": AHORA.isoformat(), "vista_primera": "x", "vista_ultima": "x"})
    assert salud.comprobar(db, REGISTRO, AHORA) == []


def test_no_ha_corrido(db):
    ejecucion(db, 3)
    assert "no ha corrido" in senales(db)


def test_volumen_caido(db):
    historia(db, recibidos=4)
    assert "volumen" in senales(db)


def test_cambio_de_formato_silencioso(db):
    historia(db, completitud={**NORMAL, "descripcion": 0})
    [a] = [a for a in salud.comprobar(db, REGISTRO, AHORA) if a.senal == "completitud"]
    assert "descripcion" in a.mensaje


def test_errores_de_normalizacion_y_error(db):
    historia(db, errores_norm=10)
    assert "errores de normalización" in senales(db)
    ejecucion(db, 0.05, estado="error", error="captcha", recibidos=0)
    assert {"error"} <= senales(db)


def test_cuota_baja(db):
    cuota = {"x-ratelimit-jobs-limit": "250", "x-ratelimit-jobs-remaining": "20",
             "x-ratelimit-requests-limit": "25", "x-ratelimit-requests-remaining": "20"}
    historia(db, cuota=json.dumps(cuota))
    [a] = [a for a in salud.comprobar(db, REGISTRO, AHORA) if a.senal == "cuota"]
    assert "jobs" in a.mensaje


def test_frescura(db):
    historia(db)
    almacen.guardar_bruto(db, 1, "f", "1", {})
    db["oferta"].insert({"fuente_id": "f", "id_externo": "1", "bruto_id": 1, "conector": "f/1", "titulo": "x",
                         "publicada_en": (AHORA - timedelta(days=5)).isoformat(), "vista_primera": "x",
                         "vista_ultima": "x"})
    assert "frescura" in senales(db)
