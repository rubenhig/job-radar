"""Fase 1 · prueba de la API pública de freehire (https://freehire.me/docs/api).

freehire (MIT) agrega ~3M ofertas de 92 ATS y ~100 portales (InfoJobs, Manfred,
Get on Board, WTTJ, Himalayas…), deduplicadas y enriquecidas (seniority, nivel
de inglés, salario, señal de oferta fantasma). Sin clave.

Lo que verifica, por búsqueda:
  - cuántas ofertas hay y de qué fuentes vienen (`/jobs/facets`),
  - qué campos llegan rellenos (`/agent/jobs/search`, con descripción completa),
  - una muestra de títulos para juzgar relevancia.
"""

import time
from collections import Counter

import httpx

BASE = "https://freehire.me/api/v1"
UA = {"User-Agent": "job-radar/0.1 (personal job radar; github.com/rubenhig/job-radar)"}
PAUSA = 3

# Vocabulario: países en ISO (`es`), ciudades con su nombre (`Málaga`),
# work_mode remote/hybrid/onsite. Ver /jobs/facets.
BUSQUEDAS = {
    "málaga · todo": {"cities": "Málaga"},
    "málaga · tech": {"cities": "Málaga", "is_tech": "true"},
    "españa · remoto · IA": {"countries": "es", "work_mode": "remote", "q": "AI engineer OR LLM OR agentes"},
    "UE · remoto · LLM": {"regions": "eu", "work_mode": "remote", "q": "LLM engineer"},
}


def top(d: dict, n=8) -> str:
    return ", ".join(f"{k} {v}" for k, v in Counter(d).most_common(n)) or "-"


def probar(cli: httpx.Client, etiqueta: str, filtros: dict):
    f = cli.get(f"{BASE}/jobs/facets", params=filtros).raise_for_status().json()["data"]
    fac = f["facets"]
    print(f"\n[{etiqueta}] total={f['total']}")
    print(f"  fuentes: {top(fac.get('source', {}))}")
    print(f"  modalidad: {top(fac.get('work_mode', {}))} · seniority: {top(fac.get('seniority', {}), 5)}")
    print(f"  inglés: {top(fac.get('english_level', {}), 5)} · fantasma: {top(fac.get('reality', {}), 5)}")
    time.sleep(PAUSA)

    jobs = cli.get(f"{BASE}/agent/jobs/search",
                   params={**filtros, "limit": 20, "sort": "created_at", "description_format": "text"}
                   ).raise_for_status().json()["data"]
    if not jobs:
        return

    def pct(cond):
        return f"{100 * sum(map(cond, jobs)) / len(jobs):.0f}%"

    enr = lambda j: j.get("enrichment") or {}  # noqa: E731
    print(f"  muestra {len(jobs)}: descripción >300c {pct(lambda j: len(j.get('description') or '') > 300)} · "
          f"salario {pct(lambda j: enr(j).get('salary_min') is not None)} · "
          f"seniority {pct(lambda j: bool(enr(j).get('seniority')))} · "
          f"inglés {pct(lambda j: bool(enr(j).get('english_level')))}")
    for j in jobs[:8]:
        print(f"  - {j['title']} — {j['company']} ({j.get('location')}, {j.get('work_mode')}) "
              f"[{j['source']}, {(j.get('posted_at') or '')[:10]}]")
    time.sleep(PAUSA)


def main():
    with httpx.Client(headers=UA, timeout=60) as cli:
        for etiqueta, filtros in BUSQUEDAS.items():
            try:
                probar(cli, etiqueta, filtros)
            except httpx.HTTPError as e:
                print(f"\n[{etiqueta}] ! {e}")


if __name__ == "__main__":
    main()
