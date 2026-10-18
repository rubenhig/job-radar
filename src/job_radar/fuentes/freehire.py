"""freehire (freehire.me): agregador MIT de ~3M ofertas de ATS y portales, con API pública.

Búsqueda (comprobado el 16-oct-2026):
  - Según la documentación, en `q` las palabras sueltas van con OR y una frase
    entre comillas es un AND de sus palabras. Pero con `q_fields=title` solo
    cuenta la primera palabra (`python java` da lo mismo que `python`), así que
    se lanza una consulta por término.
  - En una ciudad hay pocas ofertas al día: se traen todas las técnicas
    (`is_tech`) y la puntuación decide. En remoto, una consulta por término principal.

Ventana: `open_within_days` (cuándo lo vio freehire por primera vez), no
`posted_within_days`, que algunas fuentes reescriben en cada rastreo.
"""

import math
import time
import unicodedata
from collections.abc import Iterator
from typing import Any

import httpx

from job_radar.fuentes.base import (UA, Bruto, Busqueda, ErrorFuente, Intencion, Oferta, limpio, modalidad_en, numero,
                                    reintentar)
from job_radar.preferencias import Modalidad

URL = "https://freehire.me/api/v1/agent/jobs/search"  # la de /agent trae la descripción completa
POR_PAGINA = 100
MAX_PAGINAS = 10
PAUSA_S = 2

MODALIDAD = {"remote": Modalidad.REMOTO, "hybrid": Modalidad.HIBRIDO, "onsite": Modalidad.PRESENCIAL}
PERIODO = {"hour": "hora", "day": "dia", "week": "semana", "month": "mes", "year": "ano"}
CONTRATO = {"full_time": "tiempo_completo", "part_time": "tiempo_parcial", "contract": "autonomo",
            "internship": "practicas", "fellowship": "practicas", "temporary": "temporal"}
AGENCIA = {"agency": True, "outstaff": True, "product": False, "inhouse": False, "startup": False,
           "outsource": False, "government": False}


# freehire mete a veces el país en `cities` («United Arab Emirates», «Germany»): no es una ciudad.
NOMBRES_PAIS = {"spain", "espana", "germany", "deutschland", "poland", "france", "portugal", "italy", "ireland",
                "netherlands", "belgium", "united kingdom", "united states", "usa", "united arab emirates", "uae",
                "saudi arabia", "qatar", "jamaica", "ukraine", "romania", "greece", "europe", "remote"}


def _plano(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


def consultas(terminos: tuple[str, ...]) -> list[str]:
    """Una consulta por término; las frases que ya cubre un término suelto sobran ('AI agents' ⊂ 'AI')."""
    sueltos = {t.lower() for t in terminos if " " not in t}
    return [t if " " not in t else f'"{t}"' for t in terminos
            if " " not in t or not sueltos & set(t.lower().split())]


class Freehire:
    fuente = "freehire"
    version = "freehire-api/3"  # /2: España en la lista de países, modalidad del título; /3: valida_hasta
    personales = ()
    # Métricas del sitio, no de la oferta: cambian en cada consulta.
    volatiles = ("view_count", "applied_count", "upvote_count", "downvote_count", "my_vote", "last_seen_at")

    def __init__(self, cliente: httpx.Client | None = None):
        self.cliente = cliente
        self.cuota = None

    def parametros(self, i: Intencion) -> list[dict[str, Any]]:
        if not i.remota:
            return [{"cities": i.ciudad, "is_tech": "tech"}]
        donde = {"countries": i.pais.lower(), "work_mode": "remote"}
        if i.empresa_extranjera and not i.mercado:
            donde["regions"] = "eu"  # la geografía se suma (OR): España o UE
        return [{**donde, "q": q, "q_fields": "title"} for q in consultas(i.terminos)]

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        dias = max(2, math.ceil(busqueda.horas / 24) + 1)  # con solape: mejor repetido que perdido
        base = {**busqueda.parametros, "open_within_days": dias, "sort": "created_at", "order": "desc",
                "description_format": "text", "limit": POR_PAGINA}
        cli = self.cliente or httpx.Client(headers={"User-Agent": UA}, timeout=60)
        try:
            offset = 0
            for _ in range(MAX_PAGINAS):
                datos = _pagina(cli, {**base, "offset": offset})
                meta = datos.get("meta") or {}
                if meta.get("ignored_params"):  # un filtro ignorado parece un resultado amplio: es un error
                    raise ErrorFuente(f"freehire ignoró parámetros: {meta['ignored_params']}")
                for j in datos["data"]:
                    if isinstance(j.get("reality"), dict):  # la edad cambia cada día; el resto de `reality` no
                        j["reality"] = {k: v for k, v in j["reality"].items() if k != "age_days"}
                    yield Bruto.de(j["public_slug"], j, self.personales, self.volatiles)
                offset += len(datos["data"])
                if not datos["data"] or offset >= meta.get("total", 0):
                    return
                time.sleep(PAUSA_S)
        finally:
            if self.cliente is None:
                cli.close()

    def normalizar(self, j: dict[str, Any]) -> Oferta:
        e = j.get("enrichment") or {}
        ciudades, paises = j.get("cities") or [], j.get("countries") or []
        o = Oferta(
            fuente_id=self.fuente,
            id_externo=j["public_slug"],
            url=limpio(j.get("url")),
            titulo=j["title"].strip(),
            empresa=limpio(j.get("company")),
            ciudad=ciudades[0] if len(ciudades) == 1 and _plano(ciudades[0]) not in NOMBRES_PAIS else None,
            # Si España está en la lista, la oferta es de España (un remoto «Spain, Portugal…» se puede hacer aquí).
            pais="ES" if "es" in paises else (paises[0].upper() if len(paises) == 1 else None),
            modalidad=MODALIDAD.get(j.get("work_mode")) or modalidad_en(j["title"]),
            salario_min=numero(e.get("salary_min")),
            salario_max=numero(e.get("salary_max")),
            salario_moneda=limpio(e.get("salary_currency")),
            salario_periodo=PERIODO.get(e.get("salary_period")),
            descripcion=limpio(j.get("description")),
            publicada_en=j.get("posted_at") or j.get("created_at"),
            valida_hasta=j.get("closed_at"),  # freehire la da por cerrada desde entonces
            experiencia=limpio(e.get("seniority")),
            contrato=CONTRATO.get(e.get("employment_type")),
            skills=j.get("skills") or None,
            ingles=limpio(e.get("english_level")),
            es_agencia=AGENCIA.get(e.get("company_type")),
        )
        # Todo lo de `enrichment` (y las skills) lo infiere freehire con un modelo.
        derivados = [c for c in ("salario_min", "salario_max", "salario_moneda", "salario_periodo", "experiencia",
                                 "contrato", "skills", "ingles", "es_agencia") if getattr(o, c) is not None]
        return o.model_copy(update={"derivados": derivados or None})


@reintentar
def _pagina(cli: httpx.Client, parametros: dict) -> dict:
    r = cli.get(URL, params=parametros)
    r.raise_for_status()
    return r.json()
