"""Conectores de fuentes de ofertas. El contrato está en `base.py`."""

from job_radar.fuentes.base import Bruto, Busqueda, Conector, Intencion, Oferta
from job_radar.fuentes.freehire import Freehire

# Versión del conector → clase. `config/fuentes.yaml` elige cuál usa cada fuente.
CONECTORES: dict[str, type] = {c.version: c for c in (Freehire,)}


def conector(version: str) -> Conector:
    try:
        return CONECTORES[version]()
    except KeyError:
        raise KeyError(f"No hay conector '{version}'. Disponibles: {sorted(CONECTORES)}") from None


__all__ = ["Bruto", "Busqueda", "CONECTORES", "Conector", "Intencion", "Oferta", "conector"]
