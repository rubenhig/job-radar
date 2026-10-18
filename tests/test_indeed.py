import json
import math
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from job_radar.fuentes import CONECTORES, Busqueda, Intencion
from job_radar.fuentes import registro as reg
from job_radar.fuentes.indeed import Indeed
from job_radar.preferencias import Modalidad

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "indeed.json").read_text())
C = Indeed()


def test_parametros():
    [local] = C.parametros(Intencion("malaga-es", ("AI", "machine learning"), "ES", (), ciudad="Málaga"))
    assert local == {"search_term": 'AI OR "machine learning"', "location": "Málaga, España", "country_indeed": "spain"}
    [remoto] = C.parametros(Intencion("remoto-es", ("LLM",), "ES", (Modalidad.REMOTO,)))
    assert remoto["search_term"] == "(LLM) (remoto OR teletrabajo OR remote)"


def test_normaliza_ubicacion_salario_y_contrato():
    o = C.normalizar(next(j for j in FIXTURE if j.get("min_amount") and j.get("job_type")))
    assert (o.ciudad, o.region, o.pais) == ("Málaga", "AN", "ES")
    assert o.salario_periodo == "ano" and o.salario_min > 0 and o.contrato == "tiempo_completo"


def test_remoto_y_sin_modalidad():
    assert C.normalizar(next(j for j in FIXTURE if j["is_remote"])).modalidad == Modalidad.REMOTO
    assert C.normalizar(next(j for j in FIXTURE if not j["is_remote"])).modalidad is None


@pytest.mark.parametrize("j", FIXTURE, ids=lambda j: j["id"])
def test_todas_las_fixtures_normalizan(j):
    o = C.normalizar(j)
    assert o.id_externo == j["id"] and o.url and o.descripcion and o.publicada_en
    assert "emails" not in j


def test_traer_convierte_el_dataframe_y_quita_emails():
    pedido = {}

    def buscar(**kw):
        pedido.update(kw)
        return pd.DataFrame([{"id": "in-1", "title": "AI Engineer", "emails": "ana@x.com", "min_amount": math.nan,
                              "date_posted": date(2026, 10, 16), "company_rating": 4.1}])

    [b] = list(Indeed(buscar).traer(Busqueda("indeed:x", "indeed", {"search_term": "AI"}, 72)))
    assert pedido["hours_old"] == 84 and pedido["search_term"] == "AI"
    assert b.payload == {"id": "in-1", "title": "AI Engineer", "min_amount": None, "date_posted": "2026-10-16"}
    assert b.eliminados == ["emails"]


def test_cada_fuente_del_registro_tiene_su_conector():
    r = reg.cargar()
    assert {f.conector for f in r.fuentes.values()} <= set(CONECTORES)


def test_remoto_y_codigos_de_region_no_son_ciudades():
    from job_radar.fuentes.indeed import Indeed
    from job_radar.preferencias import Modalidad

    base = {"id": "x", "title": "AI Engineer", "company": "Acme", "job_url": "https://x", "description": "d"}
    o = Indeed().normalizar(base | {"location": "En remoto, ES"})
    assert o.ciudad is None and o.modalidad == Modalidad.REMOTO
    assert Indeed().normalizar(base | {"location": "AN, ES"}).ciudad is None
    o = Indeed().normalizar(base | {"location": "Málaga, AN, ES", "title": "Python Developer | Híbrido Málaga"})
    assert o.ciudad == "Málaga" and o.modalidad == Modalidad.HIBRIDO
