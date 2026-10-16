import json
from pathlib import Path

import pytest

from job_radar import almacen, puestos
from job_radar.puestos import clave_empresa, palabras_titulo, titulos_compatibles

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "puestos_malaga.json").read_text())


def ids_de(**filtro):
    return {o["id"] for o in FIXTURE if all(v in (o[k] or "") for k, v in filtro.items())}


@pytest.fixture(scope="module")
def grupo_de():
    grupos = puestos.agrupar([dict(o) for o in FIXTURE])
    return {i: frozenset(g) for g in grupos for i in g}


@pytest.mark.parametrize("a,b", [
    ("Technical Lead / SR Python", "Senior Python Developer / Technical Lead – IA & Agents | Híbrido Málaga"),
    ("Java Full Stack Developer, Hibrido", "DESARROLLADOR/A FULL STACK JAVA + REACT | SPRING BOOT | MÁLAGA"),
    ("Backend .NET Software Engineer – Campaigns & Rewards", "Senior Backend .NET Software Engineer"),
])
def test_titulos_compatibles(a, b):
    assert titulos_compatibles(palabras_titulo(a), palabras_titulo(b))


@pytest.mark.parametrize("a,b", [
    ("Senior AI Engineer", "Senior Backend Engineer (Python)"),
    ("Senior AI Engineer | T&T AI", "Senior AI Platform Engineer – LLM Gateway"),
    ("Backend Engineer", "Frontend Engineer"),
    ("Senior Data Engineer", "Senior AI Engineer"),
])
def test_titulos_incompatibles(a, b):
    assert not titulos_compatibles(palabras_titulo(a), palabras_titulo(b))


def test_clave_empresa():
    assert clave_empresa("ARELANCE S.L.") == clave_empresa("Arelance") == "arelance"
    assert clave_empresa("Camlin Group Ltd") == clave_empresa("Camlin")


def test_caso_real_technical_lead_por_varias_consultoras(grupo_de):
    """La misma vacante en Málaga, publicada por cuatro consultoras en tres fuentes."""
    lead = ids_de(titulo="Technical Lead") & ids_de(titulo="Python")
    assert len(lead) >= 7
    [grupo] = {grupo_de[i] for i in lead}
    empresas = {o["empresa"] for o in FIXTURE if o["id"] in grupo}
    assert {"Grupo Hasten", "Grupo Digital", "addSolutions", "Tecdata Engineering"} <= empresas
    # Otro puesto del mismo cliente (arquitecto de IA) sigue aparte.
    [arquitecto] = ids_de(titulo="AI Architect", empresa="addSolutions")
    assert arquitecto not in grupo


def test_misma_oferta_en_varias_fuentes(grupo_de):
    camlin = ids_de(titulo="Full Stack Engineer", empresa="Camlin")
    assert len(camlin) == 2 and len({grupo_de[i] for i in camlin}) == 1


def test_no_une_puestos_distintos(grupo_de):
    [ai] = ids_de(titulo="Senior AI Engineer", empresa="Parser")
    [backend] = ids_de(titulo="Senior Backend Engineer", empresa="Parser")
    [deloitte] = ids_de(titulo="Senior AI Engineer | T&T AI")
    [gateway] = ids_de(titulo="LLM Gateway")
    assert grupo_de[ai] != grupo_de[backend] and grupo_de[deloitte] != grupo_de[gateway]
    assert max(map(len, grupo_de.values())) < 25  # nada de grupos gigantes por transitividad


def oferta(fuente, id_externo, **campos):
    return {"fuente_id": fuente, "id_externo": id_externo, "titulo": "AI Engineer", "empresa": "Acme",
            "ciudad": "Málaga", "descripcion": "Python, LLM y agentes en producción."} | campos


@pytest.fixture
def db(tmp_path):
    d = almacen.abrir(tmp_path / "x.db")
    for f in ("infojobs", "linkedin", "indeed"):
        almacen.registrar_fuente(d, f, "portal", f"{f}/1")
    return d


def guardar(db, o):
    e = almacen.iniciar_ejecucion(db, o["fuente_id"], "x/1")
    b, _ = almacen.guardar_bruto(db, e, o["fuente_id"], o["id_externo"], o)
    return almacen.guardar_oferta(db, o, b, "x/1")[0]


def test_fusion_con_procedencia_y_prioridad_de_salario(db):
    guardar(db, oferta("indeed", "1", salario_min=30000, salario_max=40000, salario_moneda="EUR"))
    ij = guardar(db, oferta("infojobs", "2", salario_min=45000, salario_max=None, salario_moneda="EUR",
                            salario_periodo="ano", modalidad="hibrido"))
    assert puestos.actualizar(db) == {"creados": 1}
    [p] = db["puesto"].rows
    fusion = json.loads(p["fusion"])
    assert fusion["salario"]["oferta_id"] == ij and fusion["salario"]["valor"]["salario_min"] == 45000
    assert fusion["salario"]["valor"]["salario_max"] is None  # en bloque: no mezcla el máximo de otra oferta
    assert fusion["modalidad"] == {"valor": "hibrido", "oferta_id": ij, "fuente": "infojobs"}
    assert len(fusion["vias"]["valor"]) == 2


def test_ids_estables_y_fusion_de_puestos(db):
    a = guardar(db, oferta("linkedin", "1"))
    puestos.actualizar(db)
    p1 = db["oferta"].get(a)["puesto_id"]
    b = guardar(db, oferta("indeed", "9", titulo="Data Engineer", descripcion="Spark y Airflow."))
    puestos.actualizar(db)
    assert db["oferta"].get(a)["puesto_id"] == p1 != db["oferta"].get(b)["puesto_id"]
    assert puestos.actualizar(db) == {}  # sin cambios, no toca nada
    # La misma vacante llega por otra fuente: se une al puesto que ya existía.
    c = guardar(db, oferta("infojobs", "5", titulo="AI Engineer (Híbrido)"))
    puestos.actualizar(db)
    assert db["oferta"].get(c)["puesto_id"] == p1
