"""Indeed (es.indeed.com) con JobSpy: fuente secundaria, cada pocos días.

Búsqueda (comprobado el 16-oct-2026): `search_term` admite OR, comillas y
paréntesis, y busca también en la descripción (trae algo de ruido, que filtra
la puntuación). En Indeed, `hours_old` no se puede combinar con `is_remote`,
así que el remoto se pide con términos (remoto, teletrabajo, remote).
"""

import re
from collections.abc import Iterator
from datetime import date, datetime
from typing import Any

from job_radar.fuentes.base import Bruto, Busqueda, Intencion, Oferta, limpio, modalidad_en, numero
from job_radar.preferencias import Modalidad

MARGEN_H = 12
RESULTADOS = 100
PERIODO = {"hourly": "hora", "daily": "dia", "weekly": "semana", "monthly": "mes", "yearly": "ano"}
CONTRATO = {"fulltime": "tiempo_completo", "parttime": "tiempo_parcial", "contract": "autonomo",
            "internship": "practicas", "temporary": "temporal"}
PAISES = {"spain": "ES", "es": "ES", "españa": "ES"}
REMOTO_COMO_CIUDAD = re.compile(r"(en )?remot[oa]|remote", re.I)
INDEED_PAIS = {"ES": ("spain", "España")}


def expresion(terminos: tuple[str, ...]) -> str:
    return " OR ".join(f'"{t}"' if " " in t else t for t in terminos)


def _a_json(v: Any) -> Any:
    """Una celda del DataFrame de JobSpy → JSON: NaN fuera, fechas en ISO."""
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, float) and v != v:
        return None
    if hasattr(v, "item"):  # escalares de numpy
        return v.item()
    return v


class Indeed:
    fuente = "indeed"
    version = "indeed-jobspy/2"  # /2: modalidad del título; «En remoto» y «AN» no son ciudades
    personales = ("emails",)
    # Valoraciones de la empresa en Indeed: cambian sin que cambie la oferta.
    volatiles = ("company_rating", "company_reviews_count")

    def __init__(self, buscar=None):
        self._buscar = buscar
        self.cuota = None

    def parametros(self, i: Intencion) -> list[dict[str, Any]]:
        if i.pais not in INDEED_PAIS:
            return []
        pais, nombre = INDEED_PAIS[i.pais]
        if i.remota:
            termino = f"({expresion(i.terminos)}) (remoto OR teletrabajo OR remote)"
            return [{"search_term": termino, "location": nombre, "country_indeed": pais}]
        return [{"search_term": expresion(i.terminos), "location": f"{i.ciudad}, {nombre}", "country_indeed": pais}]

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        buscar = self._buscar
        if buscar is None:
            from jobspy import scrape_jobs as buscar
        df = buscar(site_name=["indeed"], results_wanted=RESULTADOS, hours_old=busqueda.horas + MARGEN_H,
                    description_format="markdown", verbose=0, **busqueda.parametros)
        for fila in df.to_dict(orient="records"):
            fila = {k: _a_json(v) for k, v in fila.items()}
            yield Bruto.de(fila["id"], fila, self.personales, self.volatiles)

    def normalizar(self, j: dict[str, Any]) -> Oferta:
        partes = [p.strip() for p in (j.get("location") or "").split(",") if p.strip()]
        pais = PAISES.get(partes[-1].lower()) if partes else None
        ciudad = partes[0] if len(partes) >= 2 else None
        tipo = (j.get("work_from_home_type") or "").lower()
        if "hybrid" in tipo or "híbrido" in tipo:
            modalidad = Modalidad.HIBRIDO
        elif j.get("is_remote") is True or "remote" in tipo or "remoto" in tipo:
            modalidad = Modalidad.REMOTO
        else:  # Indeed no distingue presencial de «no lo dice»: se mira el título
            modalidad = modalidad_en(j["title"])
        if ciudad and REMOTO_COMO_CIUDAD.fullmatch(ciudad):  # «En remoto, ES»: modalidad, no ciudad
            ciudad, modalidad = None, modalidad or Modalidad.REMOTO
        elif ciudad and re.fullmatch(r"[A-Z]{2}", ciudad):  # «AN», «CT»: códigos de región, no ciudades
            ciudad = None
        contrato = next((CONTRATO[t.strip()] for t in (j.get("job_type") or "").split(",") if t.strip() in CONTRATO),
                        None)
        return Oferta(
            fuente_id=self.fuente,
            id_externo=str(j["id"]),
            url=limpio(j.get("job_url_direct")) or limpio(j.get("job_url")),
            titulo=j["title"].strip(),
            empresa=limpio(j.get("company")),
            ciudad=ciudad,
            region=partes[1] if len(partes) == 3 else None,
            pais=pais,
            modalidad=modalidad,
            salario_min=numero(j.get("min_amount")),
            salario_max=numero(j.get("max_amount")),
            salario_moneda=limpio(j.get("currency")),
            salario_periodo=PERIODO.get(j.get("interval")),
            descripcion=limpio(j.get("description")),
            publicada_en=j.get("date_posted"),
            experiencia=limpio(j.get("job_level")),
            contrato=contrato,
            skills=[s.strip() for s in j["skills"].split(",")] if isinstance(j.get("skills"), str) else None,
        )
