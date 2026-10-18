"""InfoJobs (infojobs.net), directo: el portal con más ofertas propias en España.

Se lee el listado web con el adaptador `infojobs_es` de ats-scrapers (httpcloak
salta la protección). Las rutas semánticas (/ofertas-trabajo/malaga) y la ficha
de cada oferta caen en captcha; el listado con parámetros, no.

Comprobado el 16-oct-2026:
  - La descripción del listado está completa (0 de 55 acabadas en «…», hasta
    ~4.000 caracteres). Lo que no trae es el bloque estructurado de requisitos
    de la ficha, que tampoco se puede leer; los requisitos suelen ir en el texto.
  - La copia de InfoJobs que tiene freehire llevaba 9 días sin actualizarse.

Cuidado con la IP de casa: unas 8 peticiones en 20 minutos bastaron para que
saltara el captcha en todas las búsquedas (16-oct-2026). Por eso:
  - se busca por provincia y categoría (Informática), no término a término, y el
    filtro por rol lo hace después la puntuación: ~4 peticiones al día;
  - se para de paginar en cuanto se llega a ofertas más viejas que la ventana;
  - si salta el captcha no se reintenta (empeora): la ejecución queda en error y
    se vuelve a probar en la siguiente.
"""

import asyncio
import html
import logging
import time
import unicodedata
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from job_radar.fuentes.base import Bruto, Busqueda, ErrorFuente, Intencion, Oferta, limpio, numero
from job_radar.preferencias import Modalidad

log = logging.getLogger(__name__)

LISTADO = "https://www.infojobs.net/ofertas-trabajo"
INFORMATICA = 150      # categoryIds: Informática y telecomunicaciones
SOLO_TELETRABAJO = 2   # teleworkingIds: 1 presencial, 2 solo teletrabajo, 3 híbrido
MAX_PAGINAS = 5        # 22 ofertas por página
PAUSA_S = 20           # entre dos peticiones cualesquiera a InfoJobs
MARGEN_H = 12          # solape de la ventana: mejor repetido que perdido

# provinceIds, sacados de `aggregation.province` de las respuestas.
PROVINCIAS = {
    "alava": 2, "araba": 2, "albacete": 3, "alicante": 4, "alacant": 4, "almeria": 5, "asturias": 6,
    "avila": 7, "badajoz": 8, "barcelona": 9, "burgos": 10, "caceres": 11, "cadiz": 12, "cantabria": 13,
    "castellon": 14, "castello": 14, "ceuta": 15, "ciudad real": 16, "cordoba": 17, "cuenca": 18,
    "girona": 19, "las palmas": 20, "granada": 21, "guadalajara": 22, "guipuzcoa": 23, "gipuzkoa": 23,
    "huelva": 24, "huesca": 25, "islas baleares": 26, "illes balears": 26, "jaen": 27, "a coruna": 28,
    "la rioja": 29, "leon": 30, "lleida": 31, "lugo": 32, "madrid": 33, "malaga": 34, "melilla": 35,
    "murcia": 36, "navarra": 37, "ourense": 38, "palencia": 39, "pontevedra": 40, "salamanca": 41,
    "segovia": 42, "sevilla": 43, "soria": 44, "tarragona": 45, "santa cruz de tenerife": 46,
    "teruel": 47, "toledo": 48, "valencia": 49, "valladolid": 50, "vizcaya": 51, "bizkaia": 51,
    "zamora": 52, "zaragoza": 53,
}

PERIODO = {"HOUR": "hora", "DAY": "dia", "WEEK": "semana", "MONTH": "mes", "YEAR": "ano"}

_ultima_peticion = 0.0


def _sin_acentos(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def modalidad(teletrabajo: str | None) -> Modalidad | None:
    t = _sin_acentos(teletrabajo or "")
    if "hibrido" in t or "mixto" in t:
        return Modalidad.HIBRIDO
    if "teletrabajo" in t or "remoto" in t:
        return Modalidad.REMOTO
    if "presencial" in t:
        return Modalidad.PRESENCIAL
    return None


def contrato(tipo: str | None, jornada: str | None) -> str | None:
    t, j = _sin_acentos(tipo or ""), _sin_acentos(jornada or "")
    if "practicas" in t or "formacion" in t or "formativo" in t or "becario" in t:
        return "practicas"
    if "autonomo" in t:
        return "autonomo"
    if "determinada" in t or "discontinuo" in t or "temporal" in t:
        return "temporal"
    if "parcial" in j:
        return "tiempo_parcial"
    if "completa" in j:
        return "tiempo_completo"
    return None


class InfoJobs:
    fuente = "infojobs"
    version = "infojobs-ats-scrapers/1"
    personales = ()
    # Promoción de pago y estado de la tarjeta: cambian sin que cambie la oferta.
    volatiles = ("upsellings", "states")

    def __init__(self, pedir_pagina=None):
        self._pedir_pagina = pedir_pagina or _pedir_pagina
        self.cuota = None

    def parametros(self, i: Intencion) -> list[dict[str, Any]]:
        if i.pais != "ES":
            return []
        if i.remota:
            return [{"teleworkingIds": SOLO_TELETRABAJO, "categoryIds": INFORMATICA}]
        provincia = PROVINCIAS.get(_sin_acentos(i.ciudad))
        if provincia is None:  # una ubicación nueva no debe tumbar la ingesta de las demás fuentes
            log.warning("InfoJobs: no sé el provinceIds de '%s'; añádelo a PROVINCIAS. No se busca ahí.", i.ciudad)
            return []
        return [{"provinceIds": provincia, "categoryIds": INFORMATICA}]

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        """Por fecha de publicación, y se para en la página que ya llega a ofertas más viejas que la ventana."""
        desde = datetime.now(UTC) - timedelta(hours=busqueda.horas + MARGEN_H)
        parametros = {**busqueda.parametros, "sinceDate": "_7_DAYS", "sortBy": "PUBLICATION_DATE"}
        consulta = "&".join(f"{k}={v}" for k, v in parametros.items())
        for pagina in range(1, MAX_PAGINAS + 1):
            datos = self._pedir_pagina(f"{LISTADO}?{consulta}", pagina)
            ofertas = datos.get("offers")
            if ofertas is None:
                raise ErrorFuente("InfoJobs: la respuesta no trae `offers`; ¿ha cambiado el formato?")
            viejas = 0
            for o in ofertas:
                # El enlace lleva la página y el orden de la búsqueda: fuera, o la misma oferta cambiaría de huella.
                o = {**o, "link": (o.get("link") or "").split("?")[0]}
                yield Bruto.de(o["code"], o, self.personales, self.volatiles)
                publicada = o.get("publishedAt")
                viejas += bool(publicada and datetime.fromisoformat(publicada) < desde)
            total = (datos.get("overview") or {}).get("totalElements") or 0
            if not ofertas or viejas or pagina * len(ofertas) >= total:
                return

    def normalizar(self, o: dict[str, Any]) -> Oferta:
        salario = o.get("salary") or {}
        rango = salario.get("range") or {}
        return Oferta(
            fuente_id=self.fuente,
            id_externo=o["code"],
            url="https:" + o["link"] if o["link"].startswith("//") else o["link"],
            titulo=html.unescape(o["title"]).strip(),
            empresa=limpio(html.unescape(o.get("companyName") or "")),
            ciudad=limpio(o.get("city")),
            pais="ES",
            modalidad=modalidad(o.get("teleworking")),
            salario_min=numero(rango.get("min")),
            salario_max=numero(rango.get("max")),
            salario_moneda=limpio(salario.get("currency")),
            salario_periodo=PERIODO.get(salario.get("period")),
            descripcion=limpio(html.unescape(o.get("description") or "")),
            publicada_en=o.get("publishedAt"),
            contrato=contrato(o.get("contractType"), o.get("workday")),
        )


def _pedir_pagina(url: str, pagina: int) -> dict[str, Any]:
    from ats_scrapers.scrapers.infojobs_es import InfoJobsSpainScraper

    global _ultima_peticion
    espera = PAUSA_S - (time.monotonic() - _ultima_peticion)
    if espera > 0:
        time.sleep(espera)
    from ats_scrapers.exceptions import ScraperError

    # `_fetch_page` es interno del adaptador: si cambia, falla aquí y lo vemos en la ejecución.
    adaptador = InfoJobsSpainScraper("any", listing_url=url, max_pages=1)
    try:
        return asyncio.run(adaptador._fetch_page(pagina))
    except ScraperError as e:
        if "captcha" in str(e):
            raise ErrorFuente("InfoJobs: captcha, la IP está marcada. No se reintenta hasta la próxima ejecución") from e
        raise
    finally:
        _ultima_peticion = time.monotonic()
