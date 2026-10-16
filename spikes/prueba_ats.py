"""Fase 1 · prueba de la herramienta ATS: ats-scrapers (MIT).

Prueba: leer las ofertas de tres empresas de Málaga con ATS distintos.
  - Ebury     → Greenhouse EU (adaptador de ats-scrapers)
  - Accenture → Workday (llamada filtrada: el adaptador no admite búsqueda)
  - Freepik   → Teamtailor con dominio propio (RSS: el adaptador solo admite slugs)
"""

import xml.etree.ElementTree as ET

import httpx
from ats_scrapers.resolve import get_scraper_for_url

UA = {"User-Agent": "radar-malaga/0.1 (personal job radar)"}


def ebury():
    jobs = get_scraper_for_url("https://job-boards.eu.greenhouse.io/ebury").fetch()
    malaga = [j for j in jobs if "laga" in (j.location or "").lower()]
    con_desc = sum(1 for j in jobs if len(j.description or "") > 300)
    print(f"Ebury (Greenhouse): {len(jobs)} ofertas, {len(malaga)} en Málaga, {con_desc} con descripción")
    for j in malaga[:5]:
        print(f"  - {j.title} | {j.location}")


def accenture_malaga():
    r = httpx.post(
        "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/AccentureCareers/jobs",
        json={"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "Malaga"},
        headers=UA, timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    print(f"Accenture (Workday, búsqueda 'Malaga'): {d['total']} ofertas")
    for j in d["jobPostings"][:5]:
        print(f"  - {j['title']} | {j.get('postedOn')}")


def freepik():
    r = httpx.get("https://jobs.magnific.com/jobs.rss", headers=UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    ns = {"tt": "https://teamtailor.com/locations"}
    items = ET.fromstring(r.content).findall(".//item")
    print(f"Freepik (Teamtailor RSS): {len(items)} ofertas")
    for i in items[:5]:
        ciudades = [l.findtext("tt:city", namespaces=ns) for l in i.findall(".//tt:location", ns)]
        print(f"  - {i.findtext('title')} | {ciudades} | remoto: {i.findtext('remoteStatus')}")


if __name__ == "__main__":
    ebury()
    accenture_malaga()
    freepik()
