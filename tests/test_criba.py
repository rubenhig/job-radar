from pathlib import Path

import pytest

from job_radar import almacen, criba
from job_radar.preferencias import cargar

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture
def prefs():
    return cargar(RAIZ / "config" / "preferencias.ejemplo.yaml")


@pytest.mark.parametrize("titulo, pais, motivo", [
    ("Senior AI Engineer", "ES", None),
    ("AI Engineer", None, None),                                   # sin país: lo decide la puntuación
    ("Desarrollador/a Python | Inteligencia Artificial", "ES", None),
    ("AI Research Engineer (Pre-training - LLM)", None, None),     # «pre-training» no es «ai training»
    ("Técnico/a informático/a", "ES", None),
    ("Junior AI Engineer (m/w/d)", "DE", "fuera de tus países (DE)"),          # presencial (sin modalidad)
    ("Full Stack Developer (AI Training)", None, "título excluido: «ai training»"),
    ("Seasonal Sales Assistant", "ES", "título excluido: «sales»"),
    ("Limpiador/a", "ES", "título no técnico"),
    ("Lisbon | Home Health Aide", None, "título no técnico"),      # «aide» no es «ai»
])
def test_motivo(prefs, titulo, pais, motivo):
    assert criba.Criba(prefs).motivo({"titulo": titulo, "pais": pais}) == motivo


def test_sin_terminos_tecnicos_no_filtra_por_titulo(prefs):
    prefs.roles.terminos.tecnicos = []
    assert criba.Criba(prefs).motivo({"titulo": "Limpiador/a", "pais": "ES"}) is None


def test_aplicar_respeta_los_top_de_ruben(tmp_path, prefs):
    db = almacen.abrir(tmp_path / "db.sqlite")
    ahora = almacen.ahora()
    for titulo in ("AI Engineer", "Electricista", "Sales Manager"):
        db["puesto"].insert({"titulo": titulo, "pais": "ES", "estado": "abierto", "creado_en": ahora,
                             "actualizado_en": ahora})
    db["etiqueta"].insert({"puesto_id": 3, "valor": "top", "creada_en": ahora, "actualizada_en": ahora})
    cuenta = criba.aplicar(db, prefs)
    assert cuenta == {"pasan": 2, "título no técnico": 1}
    assert [p["descarte"] for p in db["puesto"].rows] == [None, "título no técnico", None]


def test_los_remotos_no_se_descartan_por_pais(prefs):
    c = criba.Criba(prefs)
    assert c.motivo({"titulo": "AI Engineer", "pais": "DE", "modalidad": "remoto"}) is None  # lo decide la puntuación
    assert c.motivo({"titulo": "AI Engineer", "pais": "AE", "modalidad": "presencial"}) == "fuera de tus países (AE)"
