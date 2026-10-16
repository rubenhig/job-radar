from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from job_radar.preferencias import Modalidad, Preferencias, cargar

EJEMPLO = Path(__file__).resolve().parent.parent / "config" / "preferencias.ejemplo.yaml"


def test_la_plantilla_es_valida():
    p = cargar(EJEMPLO)
    assert p.ubicaciones[0].ciudad == "Málaga"
    assert Modalidad.HIBRIDO in p.ubicaciones[0].modalidades
    assert p.remoto.desde_pais == "ES"
    assert p.idiomas["ingles"].nivel == "B2"


def test_una_clave_mal_escrita_es_un_error():
    datos = yaml.safe_load(EJEMPLO.read_text())
    datos["remoto"]["empresa_extrangera"] = True
    with pytest.raises(ValidationError, match="empresa_extrangera"):
        Preferencias.model_validate(datos)


def test_hace_falta_algun_sitio_donde_trabajar():
    with pytest.raises(ValidationError, match="al menos una ubicación"):
        Preferencias.model_validate({"roles": {"principales": ["AI Engineer"]}, "remoto": {"acepta": False, "desde_pais": "ES"}})


def test_el_salario_no_puede_filtrar_todavia():
    datos = yaml.safe_load(EJEMPLO.read_text())
    datos["salario"]["filtra"] = True
    with pytest.raises(ValidationError):
        Preferencias.model_validate(datos)
