"""Lo que devuelve y recibe la API. De aquí sale el cliente tipado de la web (hey-api)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

Valor = Literal["top", "no_top"]


class Etiqueta(BaseModel):
    valor: Valor
    motivo: str | None = None
    actualizada_en: str | None = None


class EtiquetaEntrada(BaseModel):
    valor: Valor
    motivo: str | None = Field(None, max_length=1000)


class Salario(BaseModel):
    salario_min: float | None = None
    salario_max: float | None = None
    salario_moneda: str | None = None
    salario_periodo: str | None = None


class Via(BaseModel):
    """Por dónde llega un puesto: una fuente y quien publica (empresa o consultora)."""

    fuente: str
    empresa: str | None = None


class PuestoResumen(BaseModel):
    id: int
    titulo: str
    empresa: str | None = None
    ciudad: str | None = None
    pais: str | None = None
    modalidad: str | None = None
    salario: Salario | None = None
    publicada_en: str | None = None
    vista_primera: str
    vista_ultima: str
    vias: list[Via]
    ofertas: int
    etiqueta: Etiqueta | None = None


class PaginaPuestos(BaseModel):
    total: int
    items: list[PuestoResumen]


class Oferta(BaseModel):
    id: int
    fuente_id: str
    id_externo: str
    conector: str
    url: str | None = None
    titulo: str
    empresa: str | None = None
    ciudad: str | None = None
    region: str | None = None
    pais: str | None = None
    modalidad: str | None = None
    salario: Salario | None = None
    descripcion: str | None = None
    publicada_en: str | None = None
    experiencia: str | None = None
    contrato: str | None = None
    skills: list[str] | None = None
    ingles: str | None = None
    es_agencia: bool | None = None
    derivados: list[str] | None = None
    vista_primera: str
    vista_ultima: str


class CampoFusionado(BaseModel):
    """Un campo del puesto y de qué oferta sale."""

    valor: Any
    oferta_id: int | None = None
    fuente: str | None = None


class PuestoDetalle(PuestoResumen):
    estado: str
    fusion: dict[str, CampoFusionado]
    lista_ofertas: list[Oferta]


class EstadoFuente(BaseModel):
    id: str
    tipo: str
    conector: str
    activa: bool
    ultima_ejecucion: str | None = None
    ultimo_estado: str | None = None
    recibidas_7d: int = 0
    nuevas_7d: int = 0
    oferta_mas_reciente: str | None = None
    cuota: dict[str, Any] | None = None
    coste_mes_usd: float | None = None


class Alerta(BaseModel):
    fuente: str
    senal: str
    mensaje: str


class Fuentes(BaseModel):
    fuentes: list[EstadoFuente]
    alertas: list[Alerta]


class Resumen(BaseModel):
    """La portada: lo que ha pasado y lo que queda por hacer."""

    puestos: int
    puestos_nuevos_24h: int
    puestos_nuevos_7d: int
    ofertas: int
    varias_vias: int
    etiquetados: int
    etiquetados_top: int
    por_fuente: dict[str, int]
    alertas: int
