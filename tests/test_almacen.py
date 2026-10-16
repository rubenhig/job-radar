import sqlite3

import pytest

from job_radar import almacen


@pytest.fixture
def db(tmp_path):
    d = almacen.abrir(tmp_path / "prueba.db")
    almacen.registrar_fuente(d, "infojobs", "portal", "infojobs-ats-scrapers/1")
    return d


def oferta(**cambios):
    return {"fuente_id": "infojobs", "id_externo": "abc", "titulo": "AI Engineer",
            "empresa": "Acme", "ciudad": "Málaga", "skills": ["Python", "RAG"]} | cambios


def test_migraciones_idempotentes(tmp_path):
    ruta = tmp_path / "x.db"
    almacen.abrir(ruta)
    db = almacen.abrir(ruta)  # segunda vez: no reaplica nada
    assert almacen.version(db) == len(almacen.MIGRACIONES)
    assert {"fuente", "busqueda", "ejecucion", "bruto", "oferta", "puesto", "empresa"} <= set(db.table_names())


def test_bruto_mismo_contenido_no_se_duplica(db):
    e = almacen.iniciar_ejecucion(db, "infojobs", "infojobs-ats-scrapers/1")
    b1, nuevo1 = almacen.guardar_bruto(db, e, "infojobs", "abc", {"title": "AI Engineer", "a": 1})
    b2, nuevo2 = almacen.guardar_bruto(db, e, "infojobs", "abc", {"a": 1, "title": "AI Engineer"})  # mismo, otro orden
    b3, nuevo3 = almacen.guardar_bruto(db, e, "infojobs", "abc", {"title": "AI Engineer (Sr)", "a": 1})
    assert (b1, nuevo1) == (b2, True) and not nuevo2
    assert b3 != b1 and nuevo3


def test_bruto_anota_campos_personales_eliminados(db):
    e = almacen.iniciar_ejecucion(db, "infojobs", "infojobs-ats-scrapers/1")
    b, _ = almacen.guardar_bruto(db, e, "infojobs", "abc", {"title": "x"}, eliminados=["emails"])
    assert db["bruto"].get(b)["eliminados"] == '["emails"]'


def test_oferta_nueva_y_actualizada(db):
    e = almacen.iniciar_ejecucion(db, "infojobs", "infojobs-ats-scrapers/1")
    b, _ = almacen.guardar_bruto(db, e, "infojobs", "abc", {"title": "AI Engineer"})
    o1, nueva = almacen.guardar_oferta(db, oferta(), b, "infojobs-ats-scrapers/1")
    primera = db["oferta"].get(o1)["vista_primera"]
    o2, nueva2 = almacen.guardar_oferta(db, oferta(titulo="AI Engineer Sr"), b, "infojobs-ats-scrapers/1")
    fila = db["oferta"].get(o2)
    assert nueva and not nueva2 and o1 == o2
    assert fila["titulo"] == "AI Engineer Sr" and fila["vista_primera"] == primera
    assert fila["skills"] == '["Python", "RAG"]'


def test_trazabilidad_oferta_bruto_ejecucion(db):
    e = almacen.iniciar_ejecucion(db, "infojobs", "infojobs-ats-scrapers/1")
    b, _ = almacen.guardar_bruto(db, e, "infojobs", "abc", {"title": "AI Engineer"})
    o, _ = almacen.guardar_oferta(db, oferta(), b, "infojobs-ats-scrapers/1")
    fila = db.execute("""SELECT x.conector FROM oferta o JOIN bruto b ON b.id = o.bruto_id
                         JOIN ejecucion x ON x.id = b.ejecucion_id WHERE o.id = ?""", [o]).fetchone()
    assert fila == ("infojobs-ats-scrapers/1",)


def test_claves_foraneas_activas(db):
    with pytest.raises(sqlite3.IntegrityError):
        almacen.iniciar_ejecucion(db, "fuente-que-no-existe", "x/1")


def test_cerrar_ejecucion_con_metricas(db):
    e = almacen.iniciar_ejecucion(db, "infojobs", "infojobs-ats-scrapers/1")
    almacen.cerrar_ejecucion(db, e, "ok", recibidos=20, nuevos=5, cuota={"restantes": 22})
    fila = db["ejecucion"].get(e)
    assert fila["estado"] == "ok" and fila["nuevos"] == 5 and fila["fin"] and fila["cuota"] == '{"restantes": 22}'
