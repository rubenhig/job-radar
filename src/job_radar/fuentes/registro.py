"""Registro de fuentes (config/fuentes.yaml) y búsquedas derivadas de las preferencias.

Las preferencias dicen qué busca el candidato (Intenciones); cada conector lo
traduce a su vocabulario (Búsquedas). Así, añadir una ubicación o un rol en
`preferencias.yaml` cambia las búsquedas de todas las fuentes a la vez.
"""

import re
import unicodedata
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from job_radar import almacen
from job_radar.fuentes.base import Busqueda, Conector, Intencion
from job_radar.preferencias import Modalidad, Preferencias

RUTA_REGISTRO = almacen.RAIZ / "config" / "fuentes.yaml"


class Fuente(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["agregador", "portal", "api_terceros", "ats"]
    conector: str = Field(description="Versión exacta del conector activo, p. ej. 'freehire-api/1'")
    acceso: str
    coste: str
    terminos: str
    frecuencia_h: int = Field(gt=0)
    plan_b: list[str] = Field(min_length=1)
    activa: bool = True


class Registro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fuentes: dict[str, Fuente]

    def activas(self) -> dict[str, Fuente]:
        return {k: f for k, f in self.fuentes.items() if f.activa}


def cargar(ruta: Path = RUTA_REGISTRO) -> Registro:
    return Registro.model_validate(yaml.safe_load(ruta.read_text(encoding="utf-8")))


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", texto.lower()).strip("-")


def intenciones(p: Preferencias) -> list[Intencion]:
    """Una intención por ubicación presencial (términos amplios) y otra para remoto (solo principales)."""
    principales = tuple(p.roles.terminos.principales or p.roles.principales)
    amplios = tuple(p.roles.terminos.amplios or p.roles.secundarios)
    salida = [
        Intencion(id=f"{_slug(u.ciudad)}-{u.pais.lower()}", terminos=principales + amplios,
                  pais=u.pais, ciudad=u.ciudad, modalidades=tuple(u.modalidades))
        for u in p.ubicaciones
    ]
    if p.remoto and p.remoto.acepta:
        salida.append(Intencion(id=f"remoto-{p.remoto.desde_pais.lower()}", terminos=principales,
                                pais=p.remoto.desde_pais, modalidades=(Modalidad.REMOTO,),
                                empresa_extranjera=p.remoto.empresa_extranjera))
    return salida


def busquedas(p: Preferencias, registro: Registro, conectores: Mapping[str, Conector]) -> list[Busqueda]:
    """Las búsquedas de todas las fuentes activas, en el vocabulario de cada una."""
    salida = []
    for fuente_id, fuente in registro.activas().items():
        conector = conectores[fuente_id]
        for intencion in intenciones(p):
            varias = conector.parametros(intencion)
            for n, parametros in enumerate(varias, start=1):
                sufijo = f"-{n}" if len(varias) > 1 else ""
                salida.append(Busqueda(id=f"{fuente_id}:{intencion.id}{sufijo}", fuente=fuente_id,
                                       parametros=parametros, frecuencia_h=fuente.frecuencia_h))
    return salida


def sincronizar(db, registro: Registro, lista: list[Busqueda]) -> None:
    """Deja en el almacén las fuentes y búsquedas vigentes (para trazar cada ejecución)."""
    for fuente_id, f in registro.fuentes.items():
        almacen.registrar_fuente(db, fuente_id, f.tipo, f.conector, activa=f.activa)
    for b in lista:
        almacen.guardar_busqueda(db, b.id, b.fuente, b.parametros, b.frecuencia_h)
