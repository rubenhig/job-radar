import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from job_radar import almacen, puestos
from job_radar.api import crear

RAIZ = Path(__file__).resolve().parents[1]


def oferta(fuente, id_externo, **campos):
    return {"fuente_id": fuente, "id_externo": id_externo, "titulo": "AI Engineer", "empresa": "Acme",
            "ciudad": "Málaga", "pais": "ES", "modalidad": "hibrido", "descripcion": "LLM y agentes."} | campos


@pytest.fixture
def cliente(tmp_path):
    datos = tmp_path / "data"
    (datos / "perfil").mkdir(parents=True)
    shutil.copy(RAIZ / "config" / "preferencias.ejemplo.yaml", datos / "perfil" / "preferencias.yaml")
    (datos / "perfil" / "perfil_cv.yaml").write_text("meta: {aprobado: true}\nperfil: {nombre: Ana}\n")
    db = almacen.abrir(datos / "job_radar.db")
    for f in ("infojobs", "linkedin"):
        almacen.registrar_fuente(db, f, "portal", f"{f}/1")
    for o in [oferta("infojobs", "1", salario_min=40000, salario_moneda="EUR", salario_periodo="ano"),
              oferta("linkedin", "2", empresa="Acme S.L.", skills=["Python"]),
              oferta("linkedin", "3", titulo="Data Engineer", empresa="Beta", modalidad="remoto", ciudad=None)]:
        e = almacen.iniciar_ejecucion(db, o["fuente_id"], "x/1")
        b, _ = almacen.guardar_bruto(db, e, o["fuente_id"], o["id_externo"], o)
        almacen.guardar_oferta(db, o, b, "x/1")
        almacen.cerrar_ejecucion(db, e, "ok", recibidos=1, nuevos=1)
    puestos.actualizar(db)
    return TestClient(crear(datos / "job_radar.db", datos, web=tmp_path / "sin-web"))


def test_lista_de_puestos_agrupa_y_filtra(cliente):
    r = cliente.get("/api/puestos").json()
    assert r["total"] == 2
    ai = next(p for p in r["items"] if p["titulo"] == "AI Engineer")
    assert ai["ofertas"] == 2 and {v["fuente"] for v in ai["vias"]} == {"infojobs", "linkedin"}
    assert ai["salario"]["salario_min"] == 40000
    assert cliente.get("/api/puestos", params={"modalidad": "remoto"}).json()["total"] == 1
    assert cliente.get("/api/puestos", params={"q": "Data"}).json()["items"][0]["titulo"] == "Data Engineer"
    assert cliente.get("/api/puestos", params={"fuente": "infojobs"}).json()["total"] == 1


def test_ficha_con_ofertas_y_procedencia(cliente):
    pid = cliente.get("/api/puestos", params={"q": "AI"}).json()["items"][0]["id"]
    f = cliente.get(f"/api/puestos/{pid}").json()
    assert len(f["lista_ofertas"]) == 2 and f["fusion"]["salario"]["fuente"] == "infojobs"
    assert any(o["skills"] == ["Python"] for o in f["lista_ofertas"])
    assert cliente.get("/api/puestos/9999").status_code == 404


def test_etiquetar_y_filtrar_por_etiqueta(cliente):
    pid = cliente.get("/api/puestos").json()["items"][0]["id"]
    r = cliente.put(f"/api/puestos/{pid}/etiqueta", json={"valor": "top", "motivo": "IA en Málaga"})
    assert r.status_code == 200 and r.json()["valor"] == "top"
    cliente.put(f"/api/puestos/{pid}/etiqueta", json={"valor": "no_top"})  # cambiar de opinión
    assert cliente.get("/api/puestos", params={"etiqueta": "no_top"}).json()["total"] == 1
    assert cliente.get("/api/puestos", params={"etiqueta": "sin"}).json()["total"] == 1
    assert cliente.put(f"/api/puestos/{pid}/etiqueta", json={"valor": "quizá"}).status_code == 422
    assert cliente.get("/api/resumen").json()["etiquetados"] == 1
    assert cliente.delete(f"/api/puestos/{pid}/etiqueta").status_code == 204


def test_resumen_y_fuentes(cliente):
    r = cliente.get("/api/resumen").json()
    assert r["puestos"] == 2 and r["ofertas"] == 3 and r["varias_vias"] == 1
    f = cliente.get("/api/fuentes").json()
    assert {x["id"] for x in f["fuentes"]} == {"infojobs", "linkedin"}


def test_perfil_y_preferencias(cliente, tmp_path):
    assert cliente.get("/api/perfil").json()["perfil"]["nombre"] == "Ana"
    prefs = cliente.get("/api/preferencias").json()
    prefs["ubicaciones"][0]["ciudad"] = "Sevilla"
    assert cliente.put("/api/preferencias", json=prefs).status_code == 200
    guardado = yaml.safe_load((tmp_path / "data" / "perfil" / "preferencias.yaml").read_text())
    assert guardado["ubicaciones"][0]["ciudad"] == "Sevilla"
    assert (tmp_path / "data" / "perfil" / "preferencias.anterior.yaml").exists()
    prefs["clave_inventada"] = 1
    assert cliente.put("/api/preferencias", json=prefs).status_code == 422


def test_nombres_limpios_en_openapi(cliente):
    ops = {op["operationId"] for ruta in cliente.get("/api/openapi.json").json()["paths"].values()
           for op in ruta.values()}
    assert {"puestos-listar", "puestos-ficha", "puestos-etiquetar", "sistema-resumen",
            "perfil-leer_preferencias"} <= ops


def test_sirve_la_web_y_resuelve_rutas_de_la_app(tmp_path, cliente):
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>app</html>")
    (web / "assets" / "app.js").write_text("js")
    c = TestClient(crear(cliente.app.state.ruta_db, tmp_path / "data", web=web))
    assert c.get("/").text == "<html>app</html>"
    assert c.get("/puestos/12").text == "<html>app</html>"  # recargar dentro de la app
    assert c.get("/assets/app.js").text == "js"
    assert c.get("/../pyproject.toml").text == "<html>app</html>"
    assert c.get("/api/resumen").status_code == 200


def test_valoracion_en_lista_ficha_y_acuerdo(cliente):
    from tests.test_puntuacion import OFERTA, veredictos
    from job_radar import puntuacion
    from job_radar.llm import Uso
    import sqlite3
    import sqlite_utils

    db = sqlite_utils.Database(sqlite3.connect(cliente.app.state.ruta_db))
    pid = cliente.get("/api/puestos", params={"q": "AI"}).json()["items"][0]["id"]
    puntuacion.guardar(db, pid, puntuacion.calcular(veredictos(), OFERTA), Uso(motor="m", modelo="sonnet"), "p")
    db.conn.commit()
    lista = cliente.get("/api/puestos", params={"orden": "nota"}).json()["items"]
    assert lista[0]["id"] == pid and lista[0]["valoracion"]["nota"] == 90
    assert cliente.get("/api/puestos", params={"puntuado": "false"}).json()["total"] == 1
    ev = cliente.get(f"/api/puestos/{pid}").json()["evaluacion"]
    assert ev["dimensiones"]["rol_ia"]["valor"] == "ia_principal" and ev["compuertas"]["idioma"]["valor"] == "marca"
    a = cliente.get("/api/acuerdo").json()
    assert a["casos"] == [] and a["acuerdo"] is None  # sin etiquetas aún
