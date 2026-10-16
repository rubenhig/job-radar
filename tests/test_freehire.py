import json
from pathlib import Path

import httpx
import pytest

from job_radar.fuentes import Busqueda, Intencion
from job_radar.fuentes.base import ErrorFuente
from job_radar.fuentes.freehire import Freehire, consultas
from job_radar.preferencias import Modalidad

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "freehire.json").read_text())


def por_titulo(texto):
    return next(j for j in FIXTURE if texto in j["title"])


def test_una_consulta_por_termino_porque_con_q_fields_solo_cuenta_la_primera_palabra():
    assert consultas(("AI", "LLM", "machine learning", "AI agents")) == ["AI", "LLM", '"machine learning"']


def test_parametros_local_y_remoto():
    c = Freehire()
    local = Intencion("malaga-es", ("AI", "python"), "ES", (Modalidad.HIBRIDO,), ciudad="Málaga")
    remoto = Intencion("remoto-es", ("AI",), "ES", (Modalidad.REMOTO,))
    assert c.parametros(local) == [{"cities": "Málaga", "is_tech": "tech"}]
    assert c.parametros(remoto)[0] == {"countries": "es", "regions": "eu", "work_mode": "remote",
                                             "q": "AI", "q_fields": "title"}


def test_normaliza_oferta_con_enriquecimiento():
    o = Freehire().normalizar(por_titulo("Senior Backend .NET"))
    assert o.titulo == "Senior Backend .NET Software Engineer" and o.modalidad == Modalidad.PRESENCIAL
    assert o.experiencia == "senior" and o.contrato == "tiempo_completo"
    assert set(o.derivados) >= {"experiencia", "contrato"}
    assert o.descripcion and len(o.descripcion) > 300


def test_normaliza_remoto_y_ubicacion():
    o = Freehire().normalizar(por_titulo("Application Support"))
    assert o.modalidad == Modalidad.REMOTO
    o = Freehire().normalizar(por_titulo("Python Developer – AI Agents"))
    assert o.ciudad == "Málaga" and o.pais == "ES" and o.modalidad is None  # no lo dice: vacío, no inventado


@pytest.mark.parametrize("j", FIXTURE, ids=lambda j: j["public_slug"][:30])
def test_todas_las_fixtures_normalizan(j):
    o = Freehire().normalizar(j)
    assert o.id_externo == j["public_slug"] and o.url and o.publicada_en


def respuesta(paginas, ignorados=None):
    llamadas = []

    def manejar(req):
        offset = int(req.url.params["offset"])
        llamadas.append(dict(req.url.params))
        datos = paginas[offset // 2] if offset // 2 < len(paginas) else []
        meta = {"total": sum(map(len, paginas)), **({"ignored_params": ignorados} if ignorados else {})}
        return httpx.Response(200, json={"data": datos, "meta": meta})

    return httpx.Client(transport=httpx.MockTransport(manejar)), llamadas


def test_traer_pagina_y_quita_volatiles(monkeypatch):
    monkeypatch.setattr("job_radar.fuentes.freehire.POR_PAGINA", 2)
    monkeypatch.setattr("job_radar.fuentes.freehire.PAUSA_S", 0)
    trabajos = [dict(j, view_count=7, reality={"class": "fresh", "age_days": 3}) for j in FIXTURE[:3]]
    cli, llamadas = respuesta([trabajos[:2], trabajos[2:]])
    brutos = list(Freehire(cli).traer(Busqueda("freehire:x", "freehire", {"cities": "Málaga"}, 24)))
    assert [b.id_externo for b in brutos] == [j["public_slug"] for j in FIXTURE[:3]]
    assert "view_count" not in brutos[0].payload and brutos[0].payload["reality"] == {"class": "fresh"}
    assert len(llamadas) == 2 and llamadas[0]["open_within_days"] == "2" and llamadas[0]["cities"] == "Málaga"


def test_traer_falla_si_la_fuente_ignora_un_filtro():
    cli, _ = respuesta([FIXTURE[:1]], ignorados=[{"param": "cities"}])
    with pytest.raises(ErrorFuente):
        list(Freehire(cli).traer(Busqueda("freehire:x", "freehire", {"cities": "Málaga"}, 24)))


def test_reintenta_errores_transitorios(monkeypatch):
    monkeypatch.setattr("job_radar.fuentes.freehire._pagina.retry.sleep", lambda s: None)
    intentos = []

    def manejar(req):
        intentos.append(1)
        if len(intentos) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"data": FIXTURE[:1], "meta": {"total": 1}})

    cli = httpx.Client(transport=httpx.MockTransport(manejar))
    assert len(list(Freehire(cli).traer(Busqueda("freehire:x", "freehire", {}, 24)))) == 1 and len(intentos) == 3


def test_no_reintenta_errores_4xx(monkeypatch):
    monkeypatch.setattr("job_radar.fuentes.freehire._pagina.retry.sleep", lambda s: None)
    intentos = []
    cli = httpx.Client(transport=httpx.MockTransport(lambda r: intentos.append(1) or httpx.Response(400)))
    with pytest.raises(httpx.HTTPStatusError):
        list(Freehire(cli).traer(Busqueda("freehire:x", "freehire", {}, 24)))
    assert len(intentos) == 1
