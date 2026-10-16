"""Perfil desde el CV: competencias con evidencia.

Claude extrae el perfil con salida estructurada y, para cada competencia,
copia citas literales del CV. Después Python comprueba que cada cita existe de
verdad en el texto del CV: lo que no se puede comprobar se marca, no se cree.

Uso:
    uv run python -m job_radar.perfil --cv ~/projects/CV/cv-ruben-higuera-en.pdf
"""

import argparse
import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import html2text
import yaml
from pydantic import BaseModel, Field
from pypdf import PdfReader
from rapidfuzz import fuzz

from job_radar import almacen
from job_radar.llm import ClaudeCLI, MotorLLM

SALIDA = almacen.DATOS / "perfil" / "perfil_cv.yaml"

Categoria = Literal[
    "lenguaje", "framework", "ia_llm", "datos", "cloud_devops", "arquitectura",
    "dominio", "metodologia", "herramienta", "blanda",
]
Nivel = Literal["basico", "intermedio", "avanzado", "experto"]


class Competencia(BaseModel):
    nombre: str = Field(description="Nombre canónico y corto, p. ej. 'Python', 'RAG', 'Java'")
    categoria: Categoria
    nivel: Nivel = Field(description="Inferido de años, responsabilidad y resultados descritos en el CV")
    anos: float | None = Field(None, description="Años aproximados de uso, solo si se deducen del CV")
    evidencias: list[str] = Field(min_length=1, description="Citas LITERALES del CV, copiadas carácter a carácter")


class Experiencia(BaseModel):
    empresa: str
    puesto: str
    inicio: str = Field(description="AAAA-MM")
    fin: str | None = Field(None, description="AAAA-MM, o null si es el puesto actual")
    resumen: str
    logros: list[str] = Field(description="Citas literales del CV con resultados o responsabilidades")


class Formacion(BaseModel):
    titulo: str
    centro: str
    inicio: str | None = None
    fin: str | None = None


class IdiomaCV(BaseModel):
    idioma: str
    nivel: str
    evidencia: str = Field(description="Cita literal del CV")


class PerfilCV(BaseModel):
    nombre: str
    titular: str
    resumen: str = Field(description="2–3 frases, solo con lo que dice el CV")
    anos_experiencia: float | None = None
    experiencias: list[Experiencia]
    formacion: list[Formacion]
    competencias: list[Competencia]
    idiomas: list[IdiomaCV]
    certificaciones: list[str] = []


SISTEMA = """Eres un extractor de perfiles profesionales. Tu salida se usará para
evaluar automáticamente el encaje del candidato con ofertas de empleo, así que
la precisión importa más que la exhaustividad.

Reglas:
- Usa SOLO lo que dice el CV. No infieras tecnologías que no aparezcan.
- Cada evidencia es una cita LITERAL del CV, en el idioma original del CV: copia
  el fragmento exacto, sin traducir, sin parafrasear, sin cambiar mayúsculas ni
  signos. Basta con la frase o parte de frase que lo demuestra.
- Nivel: 'experto' solo con varios años y responsabilidad clara (liderar, diseñar
  desde cero, adopción medible); 'avanzado' con uso profesional sostenido;
  'intermedio' con uso puntual o en un proyecto; 'basico' si solo se menciona.
- Agrupa sinónimos en una competencia (p. ej. 'LLM' y 'IA generativa' → 'IA generativa / LLM').
- Nombres de competencias, resúmenes y niveles, en español; las citas, sin traducir."""


def cv_a_texto(ruta: Path) -> str:
    """PDF, HTML o texto → texto plano, sin enlaces ni negritas (para poder verificar citas)."""
    if ruta.suffix.lower() == ".pdf":
        # El modo "layout" respeta la maquetación: sin él, en CVs a columnas los
        # logros de cada puesto salen al final, separados de su experiencia.
        paginas = (pag.extract_text(extraction_mode="layout") for pag in PdfReader(ruta).pages)
        texto = "\n".join(paginas)
        texto = re.sub(r"[ \t]+", " ", texto)
        return re.sub(r"\n\s*\n+", "\n", texto).strip()
    contenido = ruta.read_text(encoding="utf-8")
    if ruta.suffix.lower() in {".html", ".htm"}:
        h = html2text.HTML2Text()
        h.body_width = 0
        h.ignore_images = True
        h.ignore_links = True
        h.ignore_emphasis = True
        contenido = h.handle(contenido)
    return contenido


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto).lower()
    texto = re.sub(r"[*_`#>\[\]]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def verificar_cita(cita: str, texto_cv: str, umbral: int = 92) -> bool:
    """¿Está la cita en el CV? Literal tras normalizar espacios y mayúsculas;
    si no, se tolera una diferencia mínima (comillas, guiones) con fuzzy."""
    c, t = _normalizar(cita), _normalizar(texto_cv)
    if not c:
        return False
    return c in t or fuzz.partial_ratio(c, t) >= umbral


def citas_no_verificadas(perfil: PerfilCV, texto_cv: str) -> list[str]:
    citas = [(f"competencia {c.nombre}", e) for c in perfil.competencias for e in c.evidencias]
    citas += [(f"logro en {x.empresa}", l) for x in perfil.experiencias for l in x.logros]
    citas += [(f"idioma {i.idioma}", i.evidencia) for i in perfil.idiomas]
    return [f"{donde}: «{cita}»" for donde, cita in citas if not verificar_cita(cita, texto_cv)]


def extraer(ruta_cv: Path, motor: MotorLLM) -> dict:
    texto = cv_a_texto(ruta_cv)
    perfil, uso = motor.extraer(f"CV del candidato:\n\n{texto}", PerfilCV, sistema=SISTEMA)
    return {
        "meta": {
            "cv": str(ruta_cv),
            "cv_sha256": hashlib.sha256(texto.encode()).hexdigest()[:16],
            "extraido_en": datetime.now(UTC).isoformat(timespec="seconds"),
            "motor": uso.motor,
            "modelo": uso.modelo,
            "coste_usd_equivalente": uso.coste_usd,
            "citas_no_verificadas": citas_no_verificadas(perfil, texto),
            "aprobado": False,  # lo cambia Rubén tras revisarlo (#15)
        },
        "perfil": perfil.model_dump(mode="json"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cv", type=Path, required=True)
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--modelo", default="opus")
    args = ap.parse_args()

    resultado = extraer(args.cv.expanduser(), ClaudeCLI(modelo=args.modelo))
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(yaml.safe_dump(resultado, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")

    p, m = resultado["perfil"], resultado["meta"]
    print(f"Perfil → {args.salida}")
    print(f"  {len(p['experiencias'])} experiencias · {len(p['competencias'])} competencias · {len(p['idiomas'])} idiomas")
    print(f"  citas no verificadas: {len(m['citas_no_verificadas'])}")
    for c in m["citas_no_verificadas"]:
        print(f"    - {c}")


if __name__ == "__main__":
    main()
