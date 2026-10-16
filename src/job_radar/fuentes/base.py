"""El contrato de un conector de fuente, y lo que intercambia con el resto del sistema.

Cada fuente externa es un conector con tres operaciones:

  - `parametros(intencion)`: traduce lo que busca el candidato al vocabulario de la fuente.
  - `traer(busqueda)`: red. Pide a la fuente y devuelve Brutos, ya sin datos personales.
  - `normalizar(payload)`: pura, sin red. Convierte un bruto en una Oferta.

Nada más del sistema sabe cómo es una fuente por dentro: solo conoce Intencion,
Busqueda, Bruto y Oferta. Diseño en docs/modelo.md.
"""

import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from job_radar.preferencias import Modalidad

RAIZ = Path(__file__).resolve().parents[3]
UA = "job-radar/0.1 (radar personal de empleo; github.com/rubenhig/job-radar)"


class ErrorFuente(RuntimeError):
    """La fuente respondió algo que el conector no esperaba (formato, parámetros ignorados…)."""


def transitorio(e: BaseException) -> bool:
    """Fallos que suelen arreglarse solos: red y errores 5xx. Un 4xx o un captcha, no."""
    if isinstance(e, httpx.TransportError):
        return True
    return isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500


# Para envolver una sola petición a la fuente (no un `traer` entero, que es un generador).
reintentar = retry(retry=retry_if_exception(transitorio), stop=stop_after_attempt(3),
                   wait=wait_exponential(multiplier=2, max=30), reraise=True)


# --- lo que se busca ------------------------------------------------------------


@dataclass(frozen=True)
class Intencion:
    """Qué se busca, en términos del candidato y no de ninguna fuente.

    Sale de las preferencias: una por ubicación presencial y otra para remoto.
    """

    id: str                                   # 'malaga-es', 'remoto-es'
    terminos: tuple[str, ...]                 # términos de búsqueda, en cualquier idioma
    pais: str                                 # ISO 3166-1 alfa-2
    modalidades: tuple[Modalidad, ...]
    ciudad: str | None = None                 # None en remoto
    empresa_extranjera: bool = True           # remoto: aceptar empresas de fuera que contraten en el país

    @property
    def remota(self) -> bool:
        return self.ciudad is None


@dataclass(frozen=True)
class Busqueda:
    """Una consulta concreta a una fuente, ya en su vocabulario."""

    id: str                                   # 'linkedin:malaga-es'
    fuente: str
    parametros: dict[str, Any]
    frecuencia_h: int


# --- lo que trae la fuente ------------------------------------------------------


@dataclass
class Bruto:
    """La respuesta de la fuente para una oferta, tal cual, menos los datos personales."""

    id_externo: str
    payload: dict[str, Any]
    eliminados: list[str] = field(default_factory=list)  # campos personales quitados (con valor)

    @classmethod
    def de(cls, id_externo: Any, payload: dict[str, Any], personales: Iterable[str] = (),
           volatiles: Iterable[str] = ()) -> "Bruto":
        """Construye el bruto quitando antes los campos personales: nunca llegan a guardarse.

        Los volátiles (contadores de visitas, "visto por última vez"…) no son de la
        oferta sino de la fuente; se quitan para que la misma oferta no parezca
        nueva en cada ejecución.
        """
        limpio = {k: v for k, v in payload.items() if k not in set(volatiles)}
        eliminados = [c for c in personales if c in limpio and _tiene_valor(limpio.pop(c))]
        return cls(str(id_externo), limpio, eliminados)


def _tiene_valor(v: Any) -> bool:
    return v not in (None, "", [], {}) and v == v  # v == v descarta NaN


# --- lo que entiende el sistema -------------------------------------------------

Periodo = Literal["hora", "dia", "semana", "mes", "ano"]
Contrato = Literal["tiempo_completo", "tiempo_parcial", "temporal", "practicas", "autonomo"]


class Oferta(BaseModel):
    """Una publicación normalizada de una fuente. Los campos comunes de docs/modelo.md.

    Lo que la fuente no trae queda vacío, nunca inventado. Si un campo lo ha
    inferido un modelo de la fuente (los `ai_*` de fantastic.jobs, el
    `enrichment` de freehire), su nombre va en `derivados`.
    """

    model_config = ConfigDict(extra="forbid")

    fuente_id: str
    id_externo: str
    url: str | None = None
    titulo: str = Field(min_length=1)
    empresa: str | None = None
    ciudad: str | None = None
    region: str | None = None
    pais: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    modalidad: Modalidad | None = None
    salario_min: float | None = None
    salario_max: float | None = None
    salario_moneda: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    salario_periodo: Periodo | None = None
    descripcion: str | None = None
    publicada_en: datetime | None = None
    experiencia: str | None = None
    contrato: Contrato | None = None
    skills: list[str] | None = None
    ingles: str | None = None
    es_agencia: bool | None = None
    derivados: list[str] | None = None

    def fila(self) -> dict[str, Any]:
        """Para el almacén: fechas en ISO y vocabularios como texto."""
        return self.model_dump(mode="json")


class Conector(Protocol):
    fuente: ClassVar[str]          # 'linkedin'
    version: ClassVar[str]         # 'linkedin-fantastic-rapidapi/1': cambia si cambia la interpretación
    personales: ClassVar[tuple[str, ...]]  # campos del payload que nunca se guardan
    volatiles: ClassVar[tuple[str, ...]]   # campos que cambian en cada consulta sin que cambie la oferta

    # Lo que la fuente diga de su cuota en la última llamada a `traer` (cabeceras, créditos…).
    cuota: dict[str, Any] | None
    # Opcional: lo que costó la última llamada a `traer`, si la fuente es de pago.
    # coste_usd: float | None

    def parametros(self, intencion: Intencion) -> list[dict[str, Any]]:
        """Intención → parámetros de la fuente. Lista vacía si la fuente no la cubre."""
        ...

    def traer(self, busqueda: Busqueda) -> Iterator[Bruto]:
        """Red. Puede fallar. Cada Bruto se construye con `Bruto.de(..., self.personales, self.volatiles)`."""
        ...

    def normalizar(self, payload: dict[str, Any]) -> Oferta:
        """Pura y determinista: sin red, sin reloj. Lanza una excepción si no entiende el payload."""
        ...


# --- ayudas comunes para normalizar ---------------------------------------------


def limpio(v: Any) -> Any:
    """Texto sin espacios sobrantes; vacío y NaN → None."""
    if isinstance(v, str):
        v = v.strip()
    return v if _tiene_valor(v) else None


def numero(v: Any) -> float | None:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n and n > 0 else None


def cargar_env(ruta: Path = RAIZ / ".env") -> None:
    """Claves de las fuentes desde `.env` (fuera del repo). Lo ya definido en el entorno manda."""
    if ruta.exists():
        for linea in ruta.read_text().splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
