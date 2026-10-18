import json

import pytest

from job_radar import almacen, puestos, puntuacion
from job_radar.llm import Uso
from job_radar.preferencias import Preferencias
from job_radar.puntuacion import Requisito, Veredictos, calcular, cobertura

OFERTA = """Título: Senior AI Engineer
Descripción:
Buscamos un AI Engineer para llevar agentes LLM a producción.
Requisitos: 5 años con Python. Experiencia con RAG. Inglés C1.
Trabajo 100% remoto desde España."""


def veredictos(**cambios):
    base = {
        "resumen": "Ingeniero de IA para agentes en producción",
        "requisitos": [
            {"requisito": "5 años con Python", "importancia": "critico", "origen": "dicho",
             "competencia": "Python", "cobertura": "parcial"},
            {"requisito": "Experiencia con RAG", "importancia": "alto", "origen": "dicho",
             "competencia": "RAG", "cobertura": "fuerte"},
        ],
        "modalidad": {"veredicto": "pasa", "cita": "Trabajo 100% remoto desde España", "motivo": "remoto en ES"},
        "elegibilidad": {"veredicto": "sin_datos", "cita": None, "motivo": "no lo dice"},
        "idioma": {"veredicto": "marca", "cita": "Inglés C1", "motivo": "pide C1"},
        "funcion": {"valor": "ingenieria", "cita": "llevar agentes LLM a producción", "motivo": "construye"},
        "rol_ia": {"valor": "ia_principal", "cita": "Buscamos un AI Engineer", "motivo": "puesto de IA"},
        "seniority": {"valor": "encaja", "cita": "5 años con Python", "motivo": "senior"},
        "fuente": {"valor": "directa", "cita": None, "motivo": "empresa"},
    }
    for k, v in cambios.items():
        base[k] = base[k] | v if isinstance(v, dict) else v
    return Veredictos.model_validate(base)


def test_nota_con_pesos_fijos_y_marca_de_idioma():
    r = calcular(veredictos(), OFERTA)
    # cobertura: (2·0,5 + 1·1) / 3 = 0,667 → 0,40 + 0,30·0,667 + 0,10 + 0,10 + 0,10 = 0,90
    assert r.nota == 90 and not r.vetado and r.citas_falsas == []
    assert r.marcas == ["idioma: pide C1"]


def test_no_construir_software_anula_la_nota():
    r = calcular(veredictos(funcion={"valor": "no_construye_software", "motivo": "es docencia"}), OFERTA)
    assert r.vetado and r.nota == 0 and "docencia" in r.motivo_veto


def test_compuerta_que_no_pasa_veta_solo_con_cita_comprobada():
    con = calcular(veredictos(modalidad={"veredicto": "no_pasa", "cita": "Trabajo 100% remoto desde España",
                                         "motivo": "x"}), OFERTA)
    assert con.vetado
    inventada = calcular(veredictos(modalidad={"veredicto": "no_pasa", "cita": "Solo residentes en EE. UU.",
                                               "motivo": "solo EE. UU."}), OFERTA)
    assert not inventada.vetado and "modalidad" in inventada.citas_falsas
    assert "modalidad: solo EE. UU." in inventada.marcas


def test_requisito_con_cita_inventada_no_cuenta():
    v = veredictos(requisitos=[{"requisito": "10 años de Kubernetes", "importancia": "critico", "origen": "dicho",
                                "competencia": None, "cobertura": "falta"}])
    r = calcular(v, OFERTA)
    assert r.veredictos.requisitos == [] and r.parciales["requisitos"] == 0.5


def test_lo_inferido_nunca_es_critico():
    reqs = [Requisito(requisito="x", importancia="critico", origen="inferido", competencia=None, cobertura="falta"),
            Requisito(requisito="y", importancia="alto", origen="dicho", competencia="Python", cobertura="fuerte")]
    assert cobertura(reqs) == 1.0


class MotorFalso:
    nombre = "falso"

    def extraer(self, prompt, esquema, *, sistema=None):
        assert "# Oferta" in prompt and "Competencias" in prompt and sistema == puntuacion.SISTEMA
        return veredictos(), Uso(motor="falso", modelo="x", coste_usd=0.01)


def test_evaluar_guarda_la_evaluacion(tmp_path):
    db = almacen.abrir(tmp_path / "x.db")
    almacen.registrar_fuente(db, "f", "portal", "f/1")
    o = {"fuente_id": "f", "id_externo": "1", "titulo": "Senior AI Engineer", "empresa": "Acme",
         "descripcion": OFERTA.split("Descripción:\n")[1], "modalidad": "remoto", "pais": "ES"}
    e = almacen.iniciar_ejecucion(db, "f", "f/1")
    b, _ = almacen.guardar_bruto(db, e, "f", "1", o)
    almacen.guardar_oferta(db, o, b, "f/1")
    puestos.actualizar(db)
    perfil_cv = {"meta": {"cv_sha256": "abc"}, "perfil": {
        "titular": "AI Engineer", "resumen": "r", "competencias": [{"nombre": "Python", "nivel": "experto", "anos": 4}],
        "experiencias": [], "idiomas": [{"idioma": "inglés", "nivel": "B2"}]}}
    prefs = Preferencias.model_validate({"ubicaciones": [{"ciudad": "Málaga", "pais": "ES"}],
                                         "roles": {"principales": ["AI Engineer"]}})
    ev = db["evaluacion"].get(puntuacion.evaluar(db, 1, MotorFalso(), perfil_cv, prefs))
    assert ev["nota"] == 90 and ev["rubrica"] == "rubrica/1" and ev["coste_usd"] == 0.01
    assert json.loads(ev["resultado"])["veredictos"]["rol_ia"]["valor"] == "ia_principal"


def test_la_huella_ignora_lo_que_no_ve_el_modelo():
    from pathlib import Path

    from job_radar.preferencias import cargar

    prefs = cargar(Path(__file__).resolve().parents[1] / "config" / "preferencias.ejemplo.yaml")
    cv = {"meta": {"cv_sha256": "abc"},
          "perfil": {"titular": "AI Engineer", "resumen": "", "competencias": [], "experiencias": []}}
    antes = puntuacion.huella_perfil(cv, prefs)
    prefs.roles.excluir.append("cocinero")
    prefs.roles.terminos.amplios.append("rust")
    assert puntuacion.huella_perfil(cv, prefs) == antes
    prefs.roles.principales.append("MLOps Engineer")
    assert puntuacion.huella_perfil(cv, prefs) != antes
