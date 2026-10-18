import re
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from job_radar import almacen
from job_radar.fuentes import Bruto, Oferta
from job_radar.fuentes import registro as reg
from job_radar.preferencias import Modalidad, Preferencias, cargar

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "tests" / "fixtures"


@pytest.fixture
def prefs():
    return cargar(RAIZ / "config" / "preferencias.ejemplo.yaml")


class ConectorFalso:
    fuente, version, personales, cuota = "falsa", "falsa/1", ("email",), None

    def parametros(self, i):
        return [{"q": " OR ".join(i.terminos), "donde": i.ciudad or f"remoto {i.pais}"}]


def test_bruto_quita_datos_personales_antes_de_guardar():
    b = Bruto.de(123, {"title": "x", "email": "ana@empresa.com", "manager": None}, ("email", "manager", "phone"))
    assert b.id_externo == "123" and b.payload == {"title": "x"}
    assert b.eliminados == ["email"]  # solo se anotan los que traían valor


def test_oferta_valida_vocabularios():
    Oferta(fuente_id="f", id_externo="1", titulo="AI Engineer", pais="ES", modalidad="hibrido",
           salario_moneda="EUR", salario_periodo="ano", contrato="tiempo_completo")
    with pytest.raises(ValidationError):
        Oferta(fuente_id="f", id_externo="1", titulo="x", pais="Spain")
    with pytest.raises(ValidationError):
        Oferta(fuente_id="f", id_externo="1", titulo="x", modalidad="Hybrid")
    with pytest.raises(ValidationError):
        Oferta(fuente_id="f", id_externo="1", titulo="x", campo_inventado=1)


def test_oferta_se_guarda_en_el_almacen(tmp_path):
    db = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(db, "f", "portal", "f/1")
    e = almacen.iniciar_ejecucion(db, "f", "f/1")
    b, _ = almacen.guardar_bruto(db, e, "f", "1", {"t": 1})
    o = Oferta(fuente_id="f", id_externo="1", titulo="AI Engineer", modalidad=Modalidad.REMOTO,
               publicada_en="2026-10-14T08:27:26Z", skills=["Python"])
    oid, _ = almacen.guardar_oferta(db, o.fila(), b, "f/1")
    fila = db["oferta"].get(oid)
    assert fila["modalidad"] == "remoto" and fila["publicada_en"].startswith("2026-10-14T08:27:26")


def test_intenciones_desde_preferencias(prefs):
    malaga, remoto = reg.intenciones(prefs)
    assert malaga.id == "malaga-es" and malaga.ciudad == "Málaga" and not malaga.remota
    assert set(prefs.roles.terminos.amplios) <= set(malaga.terminos)
    assert remoto.id == "remoto-es" and remoto.remota and remoto.modalidades == (Modalidad.REMOTO,)
    assert remoto.terminos == tuple(prefs.roles.terminos.principales)  # en remoto, solo lo principal


def test_sin_terminos_se_usan_los_roles():
    p = Preferencias.model_validate({"ubicaciones": [{"ciudad": "Sevilla", "pais": "ES"}],
                                     "roles": {"principales": ["Data Engineer"], "secundarios": ["Backend"]}})
    [sevilla] = reg.intenciones(p)
    assert sevilla.terminos == ("Data Engineer", "Backend")


def test_registro_real_es_valido():
    r = reg.cargar()
    assert {"freehire", "infojobs", "linkedin", "indeed"} <= set(r.fuentes)
    assert all(f.plan_b and "/" in f.conector for f in r.fuentes.values())


def test_busquedas_y_sincronizacion(prefs, tmp_path):
    r = reg.Registro.model_validate({"fuentes": {"falsa": {
        "tipo": "portal", "conector": "falsa/1", "acceso": "-", "coste": "-", "terminos": "-",
        "frecuencia_h": 24, "plan_b": ["otra"]}}})
    lista = reg.busquedas(prefs, r, {"falsa": ConectorFalso()})
    assert [b.id for b in lista] == ["falsa:malaga-es", "falsa:remoto-es"]
    db = almacen.abrir(tmp_path / "x.db")
    reg.sincronizar(db, r, lista)
    reg.sincronizar(db, r, lista)  # idempotente
    assert db["busqueda"].count == 2
    assert json.loads(db["busqueda"].get("falsa:malaga-es")["parametros"])["donde"] == "Málaga"


@pytest.mark.parametrize("fuente,personales", [
    ("linkedin", ["ai_hiring_manager_name", "ai_hiring_manager_email_address"]),
    ("freehire", []), ("infojobs", []),
])
def test_fixtures_reales_sin_datos_personales(fuente, personales):
    items = json.loads((FIXTURES / f"{fuente}.json").read_text())
    assert len(items) >= 3
    assert not any(c in i for i in items for c in personales)


class ConectorDePrueba(ConectorFalso):
    def __init__(self, items, fallar_en=None):
        self.items, self.fallar_en = items, fallar_en

    def traer(self, busqueda):
        for n, item in enumerate(self.items):
            if n == self.fallar_en:
                raise ConnectionError("se cayó la fuente")
            yield Bruto.de(item["id"], item, self.personales)

    def normalizar(self, p):
        return Oferta(fuente_id="falsa", id_externo=str(p["id"]), titulo=p["title"])


@pytest.fixture
def db_falsa(tmp_path):
    db = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(db, "falsa", "portal", "falsa/1")
    return db


def test_ingesta_registra_metricas_y_errores_de_normalizacion(db_falsa):
    from job_radar import ingesta
    busqueda = reg.Busqueda("falsa:x", "falsa", {}, 24)
    items = [{"id": 1, "title": "AI Engineer", "email": "x@y.z"}, {"id": 2, "title": ""}]
    e = ingesta.ejecutar(db_falsa, ConectorDePrueba(items), busqueda)
    x = db_falsa["ejecucion"].get(e)
    assert (x["estado"], x["recibidos"], x["nuevos"], x["errores_norm"]) == ("parcial", 2, 1, 1)
    assert db_falsa["bruto"].count == 2  # el que no se entiende también se guarda, para reprocesar
    assert "x@y.z" not in json.dumps([r["payload"] for r in db_falsa["bruto"].rows])
    e = ingesta.ejecutar(db_falsa, ConectorDePrueba(items[:1]), busqueda)
    assert db_falsa["ejecucion"].get(e)["actualizados"] == 1


def test_ingesta_sobrevive_a_una_fuente_caida(db_falsa):
    from job_radar import ingesta
    e = ingesta.ejecutar(db_falsa, ConectorDePrueba([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}], fallar_en=1),
                         reg.Busqueda("falsa:x", "falsa", {}, 24))
    x = db_falsa["ejecucion"].get(e)
    assert x["estado"] == "parcial" and x["nuevos"] == 1 and "se cayó" in x["error"]


def test_ingesta_registra_completitud_por_campo(db_falsa):
    from job_radar import ingesta
    e = ingesta.ejecutar(db_falsa, ConectorDePrueba([{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]),
                         reg.Busqueda("falsa:x", "falsa", {}, 24))
    c = json.loads(db_falsa["ejecucion"].get(e)["completitud"])
    assert c["titulo"] == 100 and c["descripcion"] == 0 and "fuente_id" not in c


def test_frecuencia_distinta_en_remoto(prefs):
    r = reg.Registro.model_validate({"fuentes": {"falsa": {
        "tipo": "portal", "conector": "falsa/1", "acceso": "-", "coste": "-", "terminos": "-",
        "frecuencia_h": 24, "frecuencia_remoto_h": 168, "plan_b": ["otra"]}}})
    assert [b.frecuencia_h for b in reg.busquedas(prefs, r, {"falsa": ConectorFalso()})] == [24, 168]


def test_mercados_solo_en_las_fuentes_que_los_aceptan(prefs):
    prefs.remoto.mercados = ["AE", "sa", "ES"]  # el país propio no es un mercado aparte
    golfo = [i for i in reg.intenciones(prefs) if i.mercado]
    assert [(i.id, i.pais, i.remota) for i in golfo] == [("remoto-ae", "AE", True), ("remoto-sa", "SA", True)]
    base = {"tipo": "portal", "conector": "falsa/1", "acceso": "-", "coste": "-", "terminos": "-",
            "frecuencia_h": 24, "plan_b": ["otra"]}
    r = reg.Registro.model_validate({"fuentes": {"gratis": base | {"mercados": True}, "de_pago": base}})
    ids = [b.id for b in reg.busquedas(prefs, r, {"gratis": ConectorFalso(), "de_pago": ConectorFalso()})]
    assert "gratis:remoto-ae" in ids and not any(i.startswith("de_pago:remoto-a") for i in ids)


def test_renormalizar_desde_el_bruto_sin_pedir_nada(db_falsa):
    from job_radar import ingesta

    conector = ConectorDePrueba([{"id": 1, "title": "AI Engineer"}, {"id": 2, "title": "LLM Engineer"}])
    ingesta.ejecutar(db_falsa, conector, reg.Busqueda("falsa:x", "falsa", {}, 24))
    antes = [dict(o) for o in db_falsa["oferta"].rows]
    conector.version = "falsa/2"
    conector.normalizar = lambda p: Oferta(fuente_id="falsa", id_externo=str(p["id"]), titulo=p["title"].upper())
    assert ingesta.renormalizar(db_falsa, conector)["cambiadas"] == 2
    despues = [dict(o) for o in db_falsa["oferta"].rows]
    assert all(d["titulo"] == a["titulo"].upper() and d["vista_primera"] == a["vista_primera"]
               and d["conector"] == "falsa/2" for a, d in zip(antes, despues))


@pytest.mark.parametrize("fichero", sorted(p.name for p in FIXTURES.glob("*.json")))
def test_fixtures_sin_emails_ni_telefonos_personales(fichero):
    """Las fixtures son anuncios reales: que no lleven el correo o el móvil de un reclutador."""
    texto = (FIXTURES / fichero).read_text()
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", texto))
    genericos = re.compile(r"^(empleo|jobs?|careers?|rrhh|talent|recruiting|info|hello|hola|privacy|correo|"
                           r"seleccion|cv|people|hr|contacto|noreply)[\w.-]*@|@ejemplo\.", re.I)
    assert {e for e in emails if not genericos.search(e)} == set()
    assert not re.search(r"(?<![\w/])(?:\+34[ .]?)?[67]\d{2}[ .]?\d{3}[ .]?\d{3}(?!\w)", texto)  # móviles de España
