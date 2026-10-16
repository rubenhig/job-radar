"""Fase 1 · solapamiento de fuentes en Málaga (últimos 7 días, puestos técnicos).

¿Cuántas ofertas aporta cada fuente que no tenga ninguna otra? Con eso se
decide la lista de fuentes v1 (#11).

Fuentes:
  - LinkedIn (fantastic.jobs): lo guardado por prueba_linkedin_api.py (no gasta cuota)
  - freehire: /jobs/search, Málaga, publicadas en 7 días
  - InfoJobs: Málaga + Informática, 3 páginas
  - Indeed (JobSpy): varias búsquedas técnicas en Málaga, 7 días

Mismas reglas para todas: título técnico (regex) y publicada en los últimos 7
días. Dos ofertas son la misma si la empresa y el título se parecen
(rapidfuzz token_set_ratio).
"""

import asyncio
import json
import re
import time
from datetime import UTC, datetime, timedelta
from itertools import combinations
from pathlib import Path

import httpx
import pandas as pd
from ats_scrapers.scrapers.infojobs_es import InfoJobsSpainScraper
from jobspy import scrape_jobs
from rapidfuzz import fuzz

OUT = Path(__file__).resolve().parent.parent / "data" / "spike"
DESDE = datetime.now(UTC) - timedelta(days=7)
UA = {"User-Agent": "job-radar/0.1 (personal job radar; github.com/rubenhig/job-radar)"}

TECH = re.compile(
    r"engineer|developer|desarroll|programad|software|\bdata\b|datos|\bia\b|\bai\b|machine learning|"
    r"devops|cloud|back-?end|front-?end|full.?stack|python|java|\.net|\bqa\b|arquitect|architect|"
    r"tech lead|\bsre\b|ingenier|sistemas|ciberseg|security|analista", re.I)
IA = re.compile(r"\b(?:ia|ai|llm|genai|agent\w*|agente\w*|machine learning|ml)\b", re.I)


def fila(fuente, titulo, empresa, fecha, url):
    return {"fuente": fuente, "titulo": (titulo or "").strip(), "empresa": (empresa or "").strip(),
            "fecha": pd.to_datetime(fecha, utc=True, errors="coerce"), "url": url}


def linkedin():
    jobs = json.loads((OUT / "linkedin_api_malaga_tech_7d.json").read_text())
    return [fila("linkedin", j["title"], j["organization"], j["date_posted"], j["url"]) for j in jobs]


def freehire():
    filas, offset = [], 0
    with httpx.Client(headers=UA, timeout=60) as cli:
        while True:
            r = cli.get("https://freehire.me/api/v1/jobs/search",
                        params={"cities": "Málaga", "posted_within_days": 7, "limit": 100, "offset": offset})
            r.raise_for_status()
            d = r.json()
            if offset == 0 and d["meta"].get("ignored_params"):
                print(f"  ! freehire ignoró: {d['meta']['ignored_params']}")
            filas += [fila(f"freehire", j["title"], j["company"], j.get("posted_at"), j["url"]) for j in d["data"]]
            offset += 100
            if offset >= d["meta"]["total"] or not d["data"]:
                return filas
            time.sleep(2)


def infojobs():
    filas = []
    url = "https://www.infojobs.net/ofertas-trabajo?provinceIds=34&categoryIds=150&sortBy=PUBLICATION_DATE"
    sc = InfoJobsSpainScraper("any", listing_url=url, max_pages=3)
    for pagina in (1, 2, 3):
        payload = asyncio.run(sc._fetch_page(pagina))
        for o in payload.get("offers") or []:
            j = sc._parse_offer(o)
            if j:
                filas.append(fila("infojobs", j.title, j.company, j.posted_at, str(j.url)))
        if pagina * 22 >= (payload.get("overview") or {}).get("totalElements", 0):
            break
        time.sleep(10)
    return filas


def indeed():
    filas = []
    for termino in ["software", "developer", "ingeniero", "data", "IA"]:
        df = scrape_jobs(site_name=["indeed"], search_term=termino, location="Málaga, Spain",
                         country_indeed="spain", results_wanted=50, hours_old=24 * 7, verbose=0)
        filas += [fila("indeed", r.title, r.company, r.date_posted, r.job_url) for r in df.itertuples()]
        time.sleep(3)
    return filas


def norm_empresa(e: str) -> str:
    e = e.lower()
    e = re.sub(r"\b(s\.?l\.?u?|s\.?a\.?u?|group|grupo|spain|españa|espana|ltd|gmbh|inc|sociedad limitada)\b", " ", e)
    return re.sub(r"\W+", " ", e).strip()


def norm_titulo(t: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]|\bm/f/d\b|\bh/m/x?\b|\bm/f\b", " ", t.lower())
    return re.sub(r"\W+", " ", t).strip()


def misma(a, b) -> bool:
    return (fuzz.token_set_ratio(norm_empresa(a["empresa"]), norm_empresa(b["empresa"])) >= 85
            and fuzz.token_set_ratio(norm_titulo(a["titulo"]), norm_titulo(b["titulo"])) >= 85)


def main():
    filas = []
    for nombre, f in [("linkedin", linkedin), ("freehire", freehire), ("infojobs", infojobs), ("indeed", indeed)]:
        print(f"[{nombre}] …")
        try:
            filas += f()
        except Exception as e:  # una fuente caída no tumba la medición
            print(f"  ! {type(e).__name__}: {e}")
    df = pd.DataFrame(filas)
    print(f"\nRecogidas: {df['fuente'].value_counts().to_dict()}")

    df = df[df["titulo"].str.contains(TECH) & (df["fecha"].isna() | (df["fecha"] >= DESDE))]
    df = df.drop_duplicates(["fuente", "titulo", "empresa"]).reset_index(drop=True)
    sin_fecha = df[df["fecha"].isna()]["fuente"].value_counts().to_dict()
    print(f"Técnicas y de los últimos 7 días: {df['fuente'].value_counts().to_dict()} (sin fecha: {sin_fecha})")

    # Agrupa ofertas equivalentes entre fuentes (unión simple: cada oferta se une al primer grupo que encaje).
    grupos: list[list[int]] = []
    for i, a in df.iterrows():
        for g in grupos:
            if any(misma(a, df.loc[k]) for k in g):
                g.append(i)
                break
        else:
            grupos.append([i])
    df["grupo"] = 0
    for n, g in enumerate(grupos):
        df.loc[g, "grupo"] = n
    fuentes_por_grupo = df.groupby("grupo")["fuente"].agg(lambda s: frozenset(s))
    df["fuentes_grupo"] = df["grupo"].map(fuentes_por_grupo)
    df["exclusiva"] = df["fuentes_grupo"].map(len) == 1

    fuentes = sorted(df["fuente"].unique())
    print(f"\nOfertas distintas (todas las fuentes): {len(grupos)}")
    print(f"\n{'fuente':10} {'ofertas':>8} {'exclusivas':>11} {'% excl.':>8} {'excl. con IA':>13}")
    for f in fuentes:
        d = df[df["fuente"] == f].drop_duplicates("grupo")
        ex = d[d["exclusiva"]]
        print(f"{f:10} {len(d):8} {len(ex):11} {100 * len(ex) / max(len(d), 1):7.0f}% {ex['titulo'].str.contains(IA).sum():13}")

    print("\nSolapamiento por parejas (ofertas en común):")
    for a, b in combinations(fuentes, 2):
        print(f"  {a} ∩ {b}: {sum(1 for s in fuentes_por_grupo if a in s and b in s)}")

    print("\nExclusivas con IA en el título, por fuente:")
    for f in fuentes:
        ex = df[(df["fuente"] == f) & df["exclusiva"] & df["titulo"].str.contains(IA)]
        for r in ex.head(8).itertuples():
            print(f"  [{f}] {r.titulo} — {r.empresa}")

    df.drop(columns=["fuentes_grupo"]).to_csv(OUT / "solapamiento.csv", index=False)
    print(f"\nDetalle en {OUT / 'solapamiento.csv'}")


if __name__ == "__main__":
    main()
