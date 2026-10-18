"""Preferencias del candidato: lo que busca, como configuración y no como código.

Las preferencias definen qué búsquedas lanza cada fuente (ingesta) y qué
restricciones duras aplica la puntuación. Cada persona tiene su fichero
(`data/perfil/preferencias.yaml`, fuera del repo); `config/preferencias.ejemplo.yaml`
es la plantilla versionada.
"""

from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Modalidad(StrEnum):
    PRESENCIAL = "presencial"
    HIBRIDO = "hibrido"
    REMOTO = "remoto"


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid")  # una clave mal escrita es un error, no un silencio


class Ubicacion(Estricto):
    """Un sitio donde se acepta trabajar en persona (presencial o híbrido)."""

    ciudad: str
    pais: str = Field(pattern=r"^[A-Z]{2}$", description="ISO 3166-1 alfa-2, p. ej. ES")
    modalidades: list[Modalidad] = [Modalidad.PRESENCIAL, Modalidad.HIBRIDO]


class Remoto(Estricto):
    """Trabajo en remoto: desde qué país y para qué empresas."""

    acepta: bool = True
    desde_pais: str = Field(pattern=r"^[A-Z]{2}$", description="País desde el que se trabajaría")
    empresa_local: bool = True
    empresa_extranjera: bool = True
    mercados: list[str] = Field(default=[], description=(
        "Otros países cuyas ofertas en remoto se vigilan (p. ej. AE, SA, QA): un nicho, solo en fuentes gratuitas"))


class Terminos(Estricto):
    """Con qué palabras se buscan los roles en las fuentes. Vacío → los nombres de los roles."""

    principales: list[str] = Field(default=[], description="Se buscan en todas partes, también en remoto")
    amplios: list[str] = Field(default=[], description="Solo en las ubicaciones presenciales, donde el volumen es menor")
    tecnicos: list[str] = Field(default=[], description=(
        "No se buscan: con los demás términos, deciden si un título es técnico. Vacío → no se filtra por título"))


class Roles(Estricto):
    principales: list[str] = Field(min_length=1)
    secundarios: list[str] = []
    excluir: list[str] = Field(default=[], description="Términos que, en el título, descartan un puesto")
    terminos: Terminos = Terminos()


NivelIdioma = Literal["A1", "A2", "B1", "B2", "C1", "C2", "nativo"]


class Idioma(Estricto):
    nivel: NivelIdioma
    efecto: Literal["marcar", "excluir"] = Field(
        "marcar", description="Si un puesto pide más nivel: marcarlo o descartarlo")


class Informativo(Estricto):
    """Datos que se guardan y se muestran, pero no filtran."""

    filtra: Literal[False] = False


class SalarioDeseado(Estricto):
    """Bruto anual en euros. Cuenta en la nota cuando la oferta da salario (job_radar.puntuacion)."""

    actual: int | None = Field(None, gt=0, description="Por debajo de esto, el cambio es una rebaja")
    objetivo: int | None = Field(None, gt=0, description="Desde aquí, la nota suma lo máximo")

    @model_validator(mode="after")
    def ordenado(self):
        if self.actual and self.objetivo and self.objetivo < self.actual:
            raise ValueError("el objetivo no puede ser menor que el salario actual")
        return self


class Avisos(Estricto):
    inmediato_desde: int = Field(85, ge=0, le=100, description="Puntuación mínima para avisar al momento")
    resumen: Literal["diario", "semanal"] = "semanal"


class Preferencias(Estricto):
    version: int = 1
    ubicaciones: list[Ubicacion] = []
    remoto: Remoto | None = None
    roles: Roles
    idiomas: dict[str, Idioma] = {}
    salario: SalarioDeseado = SalarioDeseado()
    tipo_empresa: Informativo = Informativo()
    avisos: Avisos = Avisos()

    @model_validator(mode="after")
    def algun_sitio(self):
        if not self.ubicaciones and not (self.remoto and self.remoto.acepta):
            raise ValueError("hace falta al menos una ubicación o aceptar remoto")
        return self


def cargar(ruta: Path) -> Preferencias:
    return Preferencias.model_validate(yaml.safe_load(ruta.read_text(encoding="utf-8")))
