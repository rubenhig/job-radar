import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from job_radar.fuentes import Busqueda, Intencion
from job_radar.fuentes.base import ErrorFuente
from job_radar.fuentes.infojobs import InfoJobs, contrato, modalidad
from job_radar.preferencias import Modalidad

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "infojobs.json").read_text())


def test_parametros_por_provincia_y_categoria():
    c = InfoJobs()
    assert c.parametros(Intencion("malaga-es", ("AI",), "ES", (), ciudad="Málaga")) == [
        {"provinceIds": 34, "categoryIds": 150}]
    assert c.parametros(Intencion("remoto-es", ("AI",), "ES", (Modalidad.REMOTO,))) == [
        {"teleworkingIds": 2, "categoryIds": 150}]
    assert c.parametros(Intencion("remoto-pt", ("AI",), "PT", (Modalidad.REMOTO,))) == []
    with pytest.raises(ValueError):
        c.parametros(Intencion("x-es", ("AI",), "ES", (), ciudad="Atlántida"))


@pytest.mark.parametrize("texto,esperado", [
    ("Solo teletrabajo", Modalidad.REMOTO), ("Híbrido", Modalidad.HIBRIDO),
    ("Presencial", Modalidad.PRESENCIAL), (None, None)])
def test_modalidad(texto, esperado):
    assert modalidad(texto) == esperado


def test_contrato():
    assert contrato("Contrato indefinido", "Jornada completa") == "tiempo_completo"
    assert contrato("Contrato indefinido", "Jornada parcial - mañana") == "tiempo_parcial"
    assert contrato("Contrato de duración determinada", "Jornada completa") == "temporal"
    assert contrato("Otros contratos", None) is None


def test_normaliza_con_salario_y_modalidad():
    o = InfoJobs().normalizar(FIXTURE[0])
    assert o.titulo == "Full Stack Engineer" and o.ciudad == "Málaga" and o.pais == "ES"
    assert o.modalidad == Modalidad.HIBRIDO and o.contrato == "tiempo_completo"
    assert (o.salario_min, o.salario_max, o.salario_moneda, o.salario_periodo) == (33000, 45000, "EUR", "ano")
    assert o.url.startswith("https://www.infojobs.net/") and o.derivados is None


def test_normaliza_salario_abierto_y_entidades_html():
    o = InfoJobs().normalizar(FIXTURE[1] | {"title": "AI &amp; Platform Engineer"})
    assert o.titulo == "AI & Platform Engineer" and o.salario_min == 50000 and o.salario_max is None


@pytest.mark.parametrize("o", FIXTURE, ids=lambda o: o["code"][:10])
def test_todas_las_fixtures_normalizan(o):
    n = InfoJobs().normalizar(o)
    assert n.id_externo == o["code"] and n.descripcion and n.publicada_en


def paginas(*listas, total=None):
    llamadas = []

    def pedir(url, pagina):
        llamadas.append((url, pagina))
        ofertas = listas[pagina - 1] if pagina <= len(listas) else []
        return {"offers": ofertas, "overview": {"totalElements": total or 999}}

    return pedir, llamadas


def con_fecha(o, horas):
    return o | {"publishedAt": (datetime.now(UTC) - timedelta(hours=horas)).isoformat()}


def test_traer_para_en_la_pagina_que_llega_a_ofertas_viejas():
    a, b = FIXTURE[0], FIXTURE[1]
    pedir, llamadas = paginas([con_fecha(a, 1), con_fecha(b, 2)], [con_fecha(a, 3), con_fecha(b, 200)], [con_fecha(a, 2)])
    brutos = list(InfoJobs(pedir).traer(Busqueda("infojobs:x", "infojobs", {"provinceIds": 34}, 24)))
    assert len(llamadas) == 2 and len(brutos) == 4
    assert "provinceIds=34" in llamadas[0][0] and "sinceDate=_7_DAYS" in llamadas[0][0]
    assert "?" not in brutos[0].payload["link"]  # la página y el orden no son de la oferta
    assert "upsellings" not in brutos[0].payload


def test_traer_detecta_cambio_de_formato():
    with pytest.raises(ErrorFuente):
        list(InfoJobs(lambda url, p: {"html": "captcha"}).traer(Busqueda("infojobs:x", "infojobs", {}, 24)))
