import json
from pathlib import Path

import httpx
import pytest

from job_radar.fuentes import Busqueda, Intencion
from job_radar.fuentes.base import ErrorFuente
from job_radar.fuentes.linkedin import LinkedInRapidAPI, expresion, ventana
from job_radar.preferencias import Modalidad

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "linkedin.json").read_text())
POR_ID = {j["id"]: j for j in FIXTURE}
C = LinkedInRapidAPI()


def test_ventana_y_expresion():
    assert [ventana(h) for h in (1, 24, 26, 72, 168, 500)] == ["1h", "24h", "24h", "7d", "7d", "6m"]
    assert expresion(("AI", "machine learning")) == 'AI OR "machine learning"'


def test_parametros():
    local = C.parametros(Intencion("malaga-es", ("AI", "python"), "ES", (), ciudad="Málaga"))
    assert local == [{"title": "AI OR python", "location": "Malaga OR Málaga"}]
    [remoto] = C.parametros(Intencion("remoto-es", ("LLM",), "ES", (Modalidad.REMOTO,)))
    assert remoto["location"] == "Spain" and remoto["organization_agency"] == "exclude"


def test_salario_original_manda_sobre_el_inferido():
    o = C.normalizar(POR_ID[2414250612])
    assert (o.salario_min, o.salario_max, o.salario_moneda, o.salario_periodo) == (50000, 74500, "EUR", "ano")
    assert "salario_min" not in (o.derivados or []) and o.modalidad == Modalidad.REMOTO


def test_salario_inferido_queda_marcado():
    o = C.normalizar(POR_ID[2415558172])
    assert (o.salario_min, o.salario_max, o.salario_periodo) == (47000, 47000, "ano")
    assert {"salario_min", "es_agencia", "modalidad"} <= set(o.derivados) and o.es_agencia is True


def test_ubicacion_y_contrato():
    o = C.normalizar(POR_ID[2417556206])
    assert (o.ciudad, o.region, o.pais) == ("Málaga", "Andalusia", "ES")
    assert o.modalidad == Modalidad.HIBRIDO and o.contrato == "tiempo_completo" and "contrato" not in o.derivados
    o = C.normalizar(POR_ID[2417578542])  # sin país en la dirección: sale del derivado
    assert o.pais == "ES" and o.contrato == "autonomo" and "contrato" in o.derivados


@pytest.mark.parametrize("j", FIXTURE, ids=lambda j: str(j["id"]))
def test_todas_las_fixtures_normalizan(j):
    o = C.normalizar(j)
    assert o.id_externo == str(j["id"]) and o.descripcion and o.publicada_en and o.url


def test_traer_registra_cuota_y_quita_datos_personales():
    def manejar(req):
        assert req.url.params["time_frame"] == "24h" and req.url.params["location"] == "Spain"
        cuerpo = [dict(FIXTURE[0], ai_hiring_manager_name="Ana Pérez", org_linkedin_followers=5)]
        return httpx.Response(200, json=cuerpo, headers={"x-ratelimit-requests-remaining": "20"})

    cli = httpx.Client(transport=httpx.MockTransport(manejar))
    c = LinkedInRapidAPI(cli)
    [b] = list(c.traer(Busqueda("linkedin:x", "linkedin", {"location": "Spain"}, 24)))
    assert b.eliminados == ["ai_hiring_manager_name"] and "Ana Pérez" not in json.dumps(b.payload)
    assert "org_linkedin_followers" not in b.payload
    assert c.cuota == {"x-ratelimit-requests-remaining": "20"}


def test_traer_error_http_conserva_la_cuota():
    cli = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(429, text="quota", headers={"x-ratelimit-requests-remaining": "0"})))
    c = LinkedInRapidAPI(cli)
    with pytest.raises(ErrorFuente):
        list(c.traer(Busqueda("linkedin:x", "linkedin", {}, 24)))
    assert c.cuota["x-ratelimit-requests-remaining"] == "0"


from job_radar.fuentes.linkedin import LinkedInApify  # noqa: E402


def apify(gastado=0.0, estado="SUCCEEDED", despues="SUCCEEDED"):
    pedidos = []

    def manejar(req):
        pedidos.append(req)
        if req.url.path.endswith("/users/me/limits"):
            return httpx.Response(200, json={"data": {"current": {"monthlyUsageUsd": gastado}}})
        if req.url.path.endswith("/runs"):
            return httpx.Response(201, json={"data": {"id": "r1", "status": estado, "defaultDatasetId": "d1"}})
        if req.url.path.endswith("/actor-runs/r1"):  # la consulta tras los 60 s de espera
            return httpx.Response(200, json={"data": {"id": "r1", "status": despues, "defaultDatasetId": "d1"}})
        trabajo = dict(FIXTURE[0], recruiter_name="Ana Pérez", recruiter_url="https://linkedin.com/in/ana")
        return httpx.Response(200, json=[trabajo, FIXTURE[1]])

    return httpx.Client(transport=httpx.MockTransport(manejar)), pedidos


def test_apify_parametros():
    c = LinkedInApify()
    [local] = c.parametros(Intencion("malaga-es", ("AI", "machine learning"), "ES", (), ciudad="Málaga"))
    assert local["titleSearch"] == ["AI", "machine learning"] and local["locationSearch"] == ["Malaga", "Málaga"]
    [remoto] = c.parametros(Intencion("remoto-es", ("LLM",), "ES", (Modalidad.REMOTO,)))
    assert remoto["locationSearch"] == ["Spain"] and remoto["removeAgency"] is True


def test_apify_traer_con_presupuesto_coste_y_sin_datos_del_reclutador():
    cli, pedidos = apify(gastado=1.0)
    c = LinkedInApify(cli)
    brutos = list(c.traer(Busqueda("linkedin:malaga-es", "linkedin", {"locationSearch": ["Málaga"]}, 24)))
    run = next(p for p in pedidos if p.url.path.endswith("/runs"))
    assert json.loads(run.content)["timeRange"] == "24h" and run.url.params["maxTotalChargeUsd"] == "1.0"
    assert "Ana Pérez" not in json.dumps([b.payload for b in brutos]) and "recruiter_name" in brutos[0].eliminados
    assert c.coste_usd == 0.02 and c.cuota == {"usd-limit": "4.8", "usd-remaining": "3.8"}
    assert c.normalizar(brutos[0].payload).titulo == FIXTURE[0]["title"]


def test_apify_no_gasta_sin_presupuesto():
    cli, pedidos = apify(gastado=4.79)
    with pytest.raises(ErrorFuente, match="presupuesto"):
        list(LinkedInApify(cli).traer(Busqueda("linkedin:x", "linkedin", {}, 24)))
    assert not any(p.url.path.endswith("/runs") for p in pedidos)


def test_apify_ejecucion_fallida():
    cli, _ = apify(estado="FAILED")
    with pytest.raises(ErrorFuente, match="FAILED"):
        list(LinkedInApify(cli).traer(Busqueda("linkedin:x", "linkedin", {}, 24)))


def test_apify_espera_a_una_ejecucion_larga_y_no_hereda_costes():
    cli, pedidos = apify(estado="RUNNING")
    c = LinkedInApify(cli)
    assert len(list(c.traer(Busqueda("linkedin:remoto-es", "linkedin", {}, 168)))) == 2
    assert any(p.url.path.endswith("/actor-runs/r1") for p in pedidos) and c.coste_usd == 0.02
    cli2, _ = apify(estado="FAILED")
    c.cliente = cli2
    with pytest.raises(ErrorFuente):
        list(c.traer(Busqueda("linkedin:malaga-es", "linkedin", {}, 24)))
    assert c.coste_usd == c.PRECIO_EJECUCION  # la fallida cuesta su arranque, no lo de la anterior
