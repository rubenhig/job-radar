"""Fase 1 · prueba de InfoJobs con el adaptador `infojobs_es` de ats-scrapers.

El adaptador lee el listado de infojobs.net a través de httpcloak (suplantación
de huella TLS) y por defecto recorre todo el catálogo (~66k ofertas). Aquí lo
acotamos: una sola página por búsqueda y una pausa larga entre búsquedas, para
no quemar la IP de casa.

Lo que verifica:
  - que pasa la protección (página 1 con datos, no captcha),
  - que el filtro de la URL funciona (`totalElements` pequeño, no ~66k),
  - qué campos llegan rellenos (descripción, salario, modalidad, empresa).

Requiere: uv add httpcloak
"""

import asyncio
import time

from ats_scrapers.scrapers.infojobs_es import InfoJobsSpainScraper

# Las rutas semánticas (/ofertas-trabajo/malaga) caen en captcha; los
# parámetros de búsqueda no. Códigos sacados de `aggregation` en la respuesta:
# provinceIds 34 = Málaga · categoryIds 150 = Informática y telecomunicaciones ·
# teleworkingIds 1 presencial, 2 solo teletrabajo, 3 híbrido.
# Si `totalElements` sale ~66k, el filtro se está ignorando.
BASE = "https://www.infojobs.net/ofertas-trabajo"
BUSQUEDAS = {
    "malaga · informática": f"{BASE}?provinceIds=34&categoryIds=150&sortBy=PUBLICATION_DATE",
    "teletrabajo · ia": f"{BASE}?keyword=inteligencia%20artificial&teleworkingIds=2",
    "malaga · ia": f"{BASE}?keyword=ia&provinceIds=34",
}
PAUSA = 15  # segundos entre búsquedas


async def una_pagina(etiqueta: str, url: str):
    sc = InfoJobsSpainScraper("any", listing_url=url, max_pages=1)
    payload = await sc._fetch_page(1)
    total = (payload.get("overview") or {}).get("totalElements")
    jobs = [j for j in (sc._parse_offer(o) for o in payload.get("offers") or []) if j]

    def pct(cond):
        return f"{100 * sum(map(cond, jobs)) / len(jobs):.0f}%" if jobs else "-"

    print(f"\n[{etiqueta}] total={total} · página 1: {len(jobs)} ofertas")
    print(f"  descripción >300c {pct(lambda j: len(j.description or '') > 300)} · "
          f"salario {pct(lambda j: j.salary_min is not None)} · "
          f"modalidad {pct(lambda j: bool((j.raw or {}).get('modality')))} · "
          f"empresa visible {pct(lambda j: j.company != 'Empresa confidencial')}")
    for j in jobs[:8]:
        modalidad = (j.raw or {}).get("modality", "?")
        print(f"  - {j.title} — {j.company} ({j.location}, {modalidad}) {j.salary_summary or ''}")


async def main():
    for i, (etiqueta, url) in enumerate(BUSQUEDAS.items()):
        if i:
            time.sleep(PAUSA)
        try:
            await una_pagina(etiqueta, url)
        except Exception as e:  # una búsqueda fallida no tumba el resto
            print(f"\n[{etiqueta}] ! {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
