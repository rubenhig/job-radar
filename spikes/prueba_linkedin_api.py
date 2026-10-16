"""Fase 1 · prueba de la API de LinkedIn de fantastic.jobs vía RapidAPI.

El scraping lo hace fantastic.jobs desde su infraestructura (sin 429 en nuestra
IP). Plan gratuito: 25 llamadas y 250 ofertas al mes, así que esta prueba hace
solo 2 llamadas de 50 ofertas y guarda la respuesta en bruto en data/spike/
para analizarla sin volver a gastar cuota.

Requiere en .env (nunca va al repo):
    RAPIDAPI_KEY=...
    RAPIDAPI_HOST_LINKEDIN=linkedin-job-search-api.p.rapidapi.com   # opcional; ver "Code Snippets" en RapidAPI
"""

import json
import os
from collections import Counter
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent
OUT = RAIZ / "data" / "spike"


def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text().splitlines():
            if "=" in linea and not linea.lstrip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# API v4: un único endpoint con `time_frame` (1h, 24h, 7d, 6m); `title` y
# `location` admiten sintaxis tipo Google (OR, comillas, -excluir).
RUTA = "/active-jb"
TECH = 'engineer OR developer OR AI OR IA OR data OR software OR "machine learning"'
IA = 'AI OR IA OR LLM OR GenAI OR "machine learning" OR agent OR agentes'

BUSQUEDAS = {
    "malaga_tech_7d": {"title": TECH, "location": "Malaga OR Málaga"},
    "espana_remoto_ia_7d": {"title": IA, "location": "Spain", "ai_work_arrangement": "Remote OK,Remote Solely"},
}


def resumen(etiqueta: str, jobs: list[dict]):
    def pct(cond):
        return f"{100 * sum(bool(cond(j)) for j in jobs) / len(jobs):.0f}%" if jobs else "-"

    print(f"\n[{etiqueta}] {len(jobs)} ofertas")
    print(f"  descripción >300c {pct(lambda j: len(j.get('description_text') or '') > 300)} · "
          f"salario {pct(lambda j: j.get('ai_salary_min_value') or j.get('ai_salary_value') or j.get('salary'))} · "
          f"modalidad {pct(lambda j: bool(j.get('ai_work_arrangement')))} · "
          f"skills {pct(lambda j: bool(j.get('ai_key_skills')))} · "
          f"ficha de empresa {pct(lambda j: bool(j.get('org_linkedin_industry')))}")
    print(f"  modalidad: {dict(Counter(j.get('ai_work_arrangement') for j in jobs).most_common(5))}")
    print(f"  ciudades: {dict(Counter(c for j in jobs for c in (j.get('cities_derived') or [])).most_common(6))}")
    for j in jobs[:10]:
        print(f"  - {j.get('title')} — {j.get('organization')} "
              f"({', '.join(j.get('locations_derived') or [])}; {j.get('ai_work_arrangement')}) {(j.get('date_posted') or '')[:10]}")


def main():
    cargar_env()
    clave = os.environ.get("RAPIDAPI_KEY")
    if not clave:
        raise SystemExit("Falta RAPIDAPI_KEY en .env")
    host = os.environ.get("RAPIDAPI_HOST_LINKEDIN", "linkedin-job-search-api.p.rapidapi.com")
    OUT.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers={"X-RapidAPI-Key": clave, "X-RapidAPI-Host": host}, timeout=60) as cli:
        for etiqueta, filtros in BUSQUEDAS.items():
            guardado = OUT / f"linkedin_api_{etiqueta}.json"
            if guardado.exists():  # no gastar cuota repitiendo una búsqueda ya hecha
                jobs = json.loads(guardado.read_text())
                resumen(etiqueta, jobs)
                print(f"  (desde {guardado.name}; bórralo para volver a pedirlo)")
                continue
            r = cli.get(f"https://{host}{RUTA}",
                        params={**filtros, "time_frame": "7d", "limit": 50, "offset": 0, "description_format": "text"})
            cuota = {k: v for k, v in r.headers.items() if "ratelimit" in k.lower()}
            if r.status_code != 200:
                print(f"\n[{etiqueta}] ! HTTP {r.status_code}: {r.text[:300]}")
                continue
            jobs = r.json()
            guardado.write_text(json.dumps(jobs, ensure_ascii=False, indent=1))
            resumen(etiqueta, jobs)
            if jobs:
                print(f"  campos: {sorted(jobs[0])}")
            print(f"  cuota: {cuota}")


if __name__ == "__main__":
    main()
