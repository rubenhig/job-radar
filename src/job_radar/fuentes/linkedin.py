"""LinkedIn a través de la API de fantastic.jobs: el scraping lo hacen ellos, no nuestra IP.

La normalización es común; lo que cambia según el intermediario (RapidAPI o
Apify) es solo `traer`. Así, cambiar de intermediario es cambiar `conector` en
config/fuentes.yaml.

Los campos `ai_*` los infiere fantastic.jobs con un modelo: si una oferta los
usa, quedan marcados en `derivados`. Cuando la fuente trae el dato original
(`salary`, `employment_type`), manda el original.
"""

import os
from collections.abc import Iterator
from typing import Any

import httpx

from job_radar.fuentes.base import (Bruto, Busqueda, ErrorFuente, Intencion, Oferta, cargar_env, limpio, numero,
                                   reintentar)
from job_radar.preferencias import Modalidad

MODALIDAD = {"On-site": Modalidad.PRESENCIAL, "Hybrid": Modalidad.HIBRIDO,
             "Remote OK": Modalidad.REMOTO, "Remote Solely": Modalidad.REMOTO}
PERIODO = {"HOUR": "hora", "DAY": "dia", "WEEK": "semana", "MONTH": "mes", "YEAR": "ano"}
CONTRATO = {"FULL_TIME": "tiempo_completo", "PART_TIME": "tiempo_parcial", "CONTRACTOR": "autonomo",
            "TEMPORARY": "temporal", "INTERN": "practicas"}
PAISES = {"Spain": "ES", "Portugal": "PT", "France": "FR", "Germany": "DE", "Italy": "IT", "Ireland": "IE",
          "Netherlands": "NL", "Belgium": "BE", "United Kingdom": "GB", "United States": "US", "Poland": "PL"}
NOMBRE_PAIS = {v: k for k, v in PAISES.items()}


def ventana(frecuencia_h: int) -> str:
    """`time_frame` de la API: el menor que cubre la frecuencia."""
    for horas, valor in ((1, "1h"), (24, "24h"), (168, "7d")):
        if frecuencia_h <= horas:
            return valor
    return "6m"


def expresion(terminos: tuple[str, ...]) -> str:
    """Sintaxis tipo Google de la API: OR, y frases entre comillas."""
    return " OR ".join(f'"{t}"' if " " in t else t for t in terminos)


def _unico(valores: list | None) -> Any:
    return valores[0] if valores and len(valores) == 1 else None


def _primero(valores: list | None, mapa: dict) -> Any:
    return next((mapa[v] for v in valores or [] if v in mapa), None)


class _LinkedIn:
    fuente = "linkedin"
    personales = ("ai_hiring_manager_name", "ai_hiring_manager_email_address",
                  "recruiter_name", "recruiter_title", "recruiter_url")
    # Datos de la empresa que cambian con el tiempo sin que cambie la oferta.
    volatiles = ("org_linkedin_followers", "org_linkedin_headcount")

    def parametros(self, i: Intencion) -> list[dict[str, Any]]:
        pais = NOMBRE_PAIS.get(i.pais)
        if pais is None:
            return []
        if i.remota:
            # Las agencias inundan el remoto; en la ciudad se quedan, porque las consultoras son
            # muchas veces quien contrata (y así se ve el mismo puesto por varias vías).
            return [{"title": expresion(i.terminos), "location": pais,
                     "ai_work_arrangement": "Remote OK,Remote Solely", "organization_agency": "exclude"}]
        sin_acento = i.ciudad.translate(str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU"))
        lugar = i.ciudad if sin_acento == i.ciudad else f"{sin_acento} OR {i.ciudad}"
        return [{"title": expresion(i.terminos), "location": lugar}]

    def normalizar(self, j: dict[str, Any]) -> Oferta:
        derivados = []

        def derivado(campo: str, valor: Any) -> Any:
            if valor is not None:
                derivados.append(campo)
            return valor

        salario = j.get("salary") or {}
        valor = salario.get("value") or {} if isinstance(salario, dict) else {}
        if valor.get("minValue") or valor.get("value"):
            s_min, s_max = numero(valor.get("minValue") or valor.get("value")), numero(valor.get("maxValue"))
            moneda, periodo = salario.get("currency"), PERIODO.get(valor.get("unitText"))
        else:
            s_min = derivado("salario_min", numero(j.get("ai_salary_min_value") or j.get("ai_salary_value")))
            s_max = derivado("salario_max", numero(j.get("ai_salary_max_value") or j.get("ai_salary_value")))
            moneda = derivado("salario_moneda", limpio(j.get("ai_salary_currency")) if s_min or s_max else None)
            periodo = derivado("salario_periodo", PERIODO.get(j.get("ai_salary_unit_text")) if s_min or s_max else None)

        contrato = _primero(j.get("employment_type"), CONTRATO)
        if contrato is None:
            contrato = derivado("contrato", _primero(j.get("ai_employment_type"), CONTRATO))

        iso = _unico([((l.get("address") or {}).get("addressCountry")) for l in j.get("locations") or []])
        return Oferta(
            fuente_id=self.fuente,
            id_externo=str(j["id"]),
            url=limpio(j.get("url")),
            titulo=j["title"].strip(),
            empresa=limpio(j.get("organization")),
            ciudad=_unico(j.get("cities_derived")),
            region=_unico(j.get("regions_derived")),
            pais=iso or PAISES.get(_unico(j.get("countries_derived"))),
            modalidad=derivado("modalidad", MODALIDAD.get(j.get("ai_work_arrangement"))),
            salario_min=s_min, salario_max=s_max, salario_moneda=moneda, salario_periodo=periodo,
            descripcion=limpio(j.get("description_text")),
            publicada_en=j.get("date_posted"),
            experiencia=derivado("experiencia", limpio(j.get("ai_experience_level"))),
            contrato=contrato,
            skills=derivado("skills", j.get("ai_key_skills") or None),
            es_agencia=derivado("es_agencia", j.get("org_linkedin_recruitment_agency_derived")),
            derivados=None,
        ).model_copy(update={"derivados": derivados or None})


class LinkedInRapidAPI(_LinkedIn):
    """API v4 en RapidAPI: `GET /active-jb`, clave en RAPIDAPI_KEY."""

    version = "linkedin-fantastic-rapidapi/1"
    HOST = "linkedin-job-search-api.p.rapidapi.com"
    POR_PAGINA = 100
    MAX_PAGINAS = 3  # en el plan gratuito cada llamada cuenta: nunca más de 300 ofertas por búsqueda

    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente
        self.cuota = None

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        cargar_env()
        clave = os.environ.get("RAPIDAPI_KEY")
        if self.cliente is None and not clave:
            raise ErrorFuente("LinkedIn: falta RAPIDAPI_KEY en .env")
        host = os.environ.get("RAPIDAPI_HOST_LINKEDIN", self.HOST)
        cli = self.cliente or httpx.Client(headers={"X-RapidAPI-Key": clave, "X-RapidAPI-Host": host}, timeout=90)
        base = {**busqueda.parametros, "time_frame": ventana(busqueda.frecuencia_h),
                "description_format": "text", "limit": self.POR_PAGINA}
        try:
            for pagina in range(self.MAX_PAGINAS):
                r = _get(cli, f"https://{host}/active-jb", {**base, "offset": pagina * self.POR_PAGINA})
                self.cuota = {k.lower(): v for k, v in r.headers.items() if "ratelimit" in k.lower()} or self.cuota
                if r.status_code != 200:
                    raise ErrorFuente(f"LinkedIn (RapidAPI): HTTP {r.status_code}: {r.text[:300]}")
                trabajos = r.json()
                if not isinstance(trabajos, list):
                    raise ErrorFuente(f"LinkedIn (RapidAPI): respuesta inesperada: {str(trabajos)[:300]}")
                for j in trabajos:
                    yield Bruto.de(j["id"], j, self.personales, self.volatiles)
                if len(trabajos) < self.POR_PAGINA:
                    return
        finally:
            if self.cliente is None:
                cli.close()


@reintentar
def _get(cli: httpx.Client, url: str, parametros: dict) -> httpx.Response:
    r = cli.get(url, params=parametros)
    if r.status_code >= 500:
        r.raise_for_status()
    return r


class LinkedInApify(_LinkedIn):
    """El actor de fantastic.jobs en Apify: misma base de datos y mismos campos que la API de RapidAPI.

    Precio en el plan gratuito de Apify (comprobado el 16-oct-2026 en su API): 0,005 $ por
    oferta y 0,01 $ por ejecución, con un tope duro de 5 $ al mes. Cada ejecución se limita
    a lo que queda del presupuesto (`maxTotalChargeUsd`), así que nunca se pasa.
    """

    version = "linkedin-fantastic-apify/1"
    ACTOR = "fantastic-jobs~advanced-linkedin-job-search-api"
    API = "https://api.apify.com/v2"
    PRECIO_OFERTA = 0.005
    PRECIO_EJECUCION = 0.01
    PRESUPUESTO_MES = 4.8   # el plan gratuito corta en 5 $
    TOPE_EJECUCION = 1.0
    LIMITE = {"ciudad": 60, "remoto": 250}  # ofertas por ejecución

    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente
        self.cuota = None
        self.coste_usd = None

    def parametros(self, i: Intencion) -> list[dict[str, Any]]:
        pais = NOMBRE_PAIS.get(i.pais)
        if pais is None:
            return []
        if i.remota:
            return [{"titleSearch": list(i.terminos), "locationSearch": [pais], "removeAgency": True,
                     "aiWorkArrangementFilter": ["Remote OK", "Remote Solely"], "limit": self.LIMITE["remoto"]}]
        sin_acento = i.ciudad.translate(str.maketrans("áéíóúÁÉÍÓÚ", "aeiouAEIOU"))
        return [{"titleSearch": list(i.terminos), "locationSearch": sorted({i.ciudad, sin_acento}),
                 "limit": self.LIMITE["ciudad"]}]

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        cargar_env()
        token = os.environ.get("APIFY_TOKEN")
        if self.cliente is None and not token:
            raise ErrorFuente("LinkedIn: falta APIFY_TOKEN en .env")
        cli = self.cliente or httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=330)
        try:
            gastado = _json(_get(cli, f"{self.API}/users/me/limits", {}))["data"]["current"]["monthlyUsageUsd"]
            queda = round(self.PRESUPUESTO_MES - gastado, 4)
            self.cuota = {"usd-limit": str(self.PRESUPUESTO_MES), "usd-remaining": str(max(queda, 0))}
            if queda < self.PRECIO_EJECUCION + 10 * self.PRECIO_OFERTA:
                raise ErrorFuente(f"LinkedIn (Apify): presupuesto del mes agotado ({gastado:.2f} $ gastados)")
            entrada = {**busqueda.parametros, "timeRange": ventana(busqueda.frecuencia_h), "descriptionType": "text"}
            r = _post(cli, f"{self.API}/acts/{self.ACTOR}/runs", entrada,
                      {"waitForFinish": 300, "maxTotalChargeUsd": min(self.TOPE_EJECUCION, queda)})
            ejecucion = _json(r)["data"]
            if ejecucion["status"] != "SUCCEEDED":
                raise ErrorFuente(f"LinkedIn (Apify): la ejecución {ejecucion['id']} acabó en {ejecucion['status']}")
            trabajos = _json(_get(cli, f"{self.API}/datasets/{ejecucion['defaultDatasetId']}/items", {}))
            # Apify factura los eventos con retraso: el coste se calcula con sus precios.
            self.coste_usd = round(self.PRECIO_EJECUCION + self.PRECIO_OFERTA * len(trabajos), 4)
            for j in trabajos:
                yield Bruto.de(j["id"], j, self.personales, self.volatiles)
        finally:
            if self.cliente is None:
                cli.close()


def _json(r: httpx.Response) -> Any:
    if r.status_code >= 400:
        raise ErrorFuente(f"Apify: HTTP {r.status_code}: {r.text[:300]}")
    return r.json()


@reintentar
def _post(cli: httpx.Client, url: str, cuerpo: dict, parametros: dict) -> httpx.Response:
    r = cli.post(url, json=cuerpo, params=parametros)
    if r.status_code >= 500:
        r.raise_for_status()
    return r
