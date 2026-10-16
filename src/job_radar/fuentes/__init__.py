"""Conectores de fuentes de ofertas. El contrato está en `base.py`."""

from job_radar.fuentes.base import Bruto, Busqueda, Conector, Intencion, Oferta
from job_radar.fuentes.freehire import Freehire
from job_radar.fuentes.indeed import Indeed
from job_radar.fuentes.infojobs import InfoJobs
from job_radar.fuentes.linkedin import LinkedInRapidAPI

# Versión del conector → clase. `config/fuentes.yaml` elige cuál usa cada fuente.
CONECTORES: dict[str, type] = {c.version: c for c in (Freehire, InfoJobs, LinkedInRapidAPI, Indeed)}


def conector(version: str) -> Conector:
    try:
        return CONECTORES[version]()
    except KeyError:
        raise KeyError(f"No hay conector '{version}'. Disponibles: {sorted(CONECTORES)}") from None


__all__ = ["Bruto", "Busqueda", "CONECTORES", "Conector", "Intencion", "Oferta", "conector"]
