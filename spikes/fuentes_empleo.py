"""Spike: recoge ofertas reales de varias fuentes para ver qué datos dan.

No hay base de datos ni LLM: solo CSVs en data/spike/ para analizarlos
después con spikes/analisis.py.

Fuentes:
  - JobSpy (LinkedIn, Indeed España, Google Jobs)
  - RSS de Tecnoempleo
  - Endpoints públicos de ATS (Greenhouse, Lever, Ashby, Workable), para las
    empresas que detectemos en las URLs de las ofertas anteriores.
"""

import html
import re
import time
from pathlib import Path

import feedparser
import httpx
import pandas as pd
from jobspy import scrape_jobs

OUT = Path(__file__).resolve().parent.parent / "data" / "spike"

TERMINOS = ["AI Engineer", "LLM Engineer", "agentes IA", "Software Engineer"]
UBICACIONES = [
    {"etiqueta": "malaga", "location": "Málaga, Spain", "is_remote": False},
    {"etiqueta": "remoto_es", "location": "Spain", "is_remote": True},
]
SITIOS = ["linkedin", "indeed", "google"]
RESULTADOS_POR_BUSQUEDA = 20
HORAS = 24 * 30  # último mes

TECNOEMPLEO_RSS = "https://www.tecnoempleo.com/alertas-empleo-rss.php"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) radar-malaga-spike"


def recoger_jobspy() -> pd.DataFrame:
    frames = []
    for termino in TERMINOS:
        for ubi in UBICACIONES:
            google_q = f"{termino} jobs {'remote Spain' if ubi['is_remote'] else 'near Málaga, Spain'}"
            print(f"[jobspy] '{termino}' @ {ubi['etiqueta']}")
            try:
                df = scrape_jobs(
                    site_name=SITIOS,
                    search_term=termino,
                    google_search_term=google_q,
                    location=ubi["location"],
                    is_remote=ubi["is_remote"],
                    country_indeed="spain",
                    results_wanted=RESULTADOS_POR_BUSQUEDA,
                    hours_old=HORAS,
                    fetch_description=True,
                    verbose=0,
                )
            except Exception as e:  # una búsqueda fallida no tumba el resto
                print(f"  ! error: {e}")
                continue
            df["busqueda"] = termino
            df["ubicacion_busqueda"] = ubi["etiqueta"]
            print(f"  {len(df)} ofertas ({df['site'].value_counts().to_dict() if len(df) else {}})")
            frames.append(df)
            time.sleep(5)  # cortesía con LinkedIn
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _campo(texto: str, nombre: str) -> str:
    m = re.search(rf"<b>{nombre}:</b>&nbsp;(.*?)<br", texto, flags=re.S)
    return html.unescape(m.group(1)).strip() if m else ""


def recoger_tecnoempleo() -> pd.DataFrame:
    print("[tecnoempleo] RSS")
    resp = httpx.get(TECNOEMPLEO_RSS, headers={"User-Agent": UA}, timeout=30, follow_redirects=True)
    feed = feedparser.parse(resp.content)
    filas = []
    for e in feed.entries:
        desc = e.get("description", "")
        filas.append(
            {
                "title": e.get("title", ""),
                "job_url": e.get("link", ""),
                "date_posted": e.get("published", ""),
                "company": _campo(desc, "Empresa"),
                "provincia": _campo(desc, "Provincia"),
                "poblacion": _campo(desc, "Población"),
                "description": re.sub(r"<[^>]+>", " ", html.unescape(desc.split("Descripción:</b>&nbsp;")[-1])).strip(),
            }
        )
    print(f"  {len(filas)} ofertas")
    return pd.DataFrame(filas)


# --- ATS -------------------------------------------------------------------

PATRONES_ATS = {
    "greenhouse": r"(?:job-boards|boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]+)",
    "lever": r"jobs(?:\.eu)?\.lever\.co/([\w-]+)",
    "ashby": r"jobs\.ashbyhq\.com/([\w%.-]+)",
    "workable": r"apply\.workable\.com/([\w-]+)",
}
SLUGS_IGNORADOS = {"j", "api", "embed"}


def detectar_ats(df: pd.DataFrame) -> pd.DataFrame:
    """Busca URLs de ATS en las URLs directas y descripciones de las ofertas."""
    encontrados = {}
    for _, fila in df.iterrows():
        texto = " ".join(str(fila.get(c, "")) for c in ("job_url_direct", "job_url", "description"))
        for ats, patron in PATRONES_ATS.items():
            for slug in re.findall(patron, texto):
                slug = slug.lower()
                if slug in SLUGS_IGNORADOS:
                    continue
                encontrados.setdefault((ats, slug), str(fila.get("company", "")))
    return pd.DataFrame(
        [{"ats": a, "slug": s, "empresa_en_oferta": c} for (a, s), c in encontrados.items()]
    )


def _jobs_greenhouse(cli, slug):
    for base in ("https://boards-api.greenhouse.io", "https://boards-api.eu.greenhouse.io"):
        r = cli.get(f"{base}/v1/boards/{slug}/jobs")
        if r.status_code == 200:
            return [
                {"title": j["title"], "location": (j.get("location") or {}).get("name", ""),
                 "job_url": j.get("absolute_url", ""), "remote": None, "date_posted": j.get("updated_at", "")}
                for j in r.json().get("jobs", [])
            ]
    return None


def _jobs_lever(cli, slug):
    for base in ("https://api.lever.co", "https://api.eu.lever.co"):
        r = cli.get(f"{base}/v0/postings/{slug}", params={"mode": "json"})
        if r.status_code == 200 and isinstance(r.json(), list):
            return [
                {"title": j.get("text", ""), "location": (j.get("categories") or {}).get("location", ""),
                 "job_url": j.get("hostedUrl", ""), "remote": j.get("workplaceType"),
                 "date_posted": j.get("createdAt", "")}
                for j in r.json()
            ]
    return None


def _jobs_ashby(cli, slug):
    r = cli.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", params={"includeCompensation": "true"})
    if r.status_code != 200:
        return None
    return [
        {"title": j.get("title", ""), "location": j.get("location", ""), "job_url": j.get("jobUrl", ""),
         "remote": j.get("workplaceType") or j.get("isRemote"), "date_posted": j.get("publishedAt", "")}
        for j in r.json().get("jobs", [])
    ]


def _jobs_workable(cli, slug):
    r = cli.get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}")
    if r.status_code != 200:
        return None
    return [
        {"title": j.get("title", ""), "location": ", ".join(filter(None, [j.get("city"), j.get("country")])),
         "job_url": j.get("url", ""), "remote": j.get("telecommuting"), "date_posted": j.get("published_on", "")}
        for j in r.json().get("jobs", [])
    ]


LECTORES_ATS = {"greenhouse": _jobs_greenhouse, "lever": _jobs_lever, "ashby": _jobs_ashby, "workable": _jobs_workable}


def recoger_ats(detectados: pd.DataFrame) -> pd.DataFrame:
    filas = []
    with httpx.Client(headers={"User-Agent": UA}, timeout=30, follow_redirects=True) as cli:
        for _, d in detectados.iterrows():
            try:
                jobs = LECTORES_ATS[d["ats"]](cli, d["slug"])
            except Exception as e:
                print(f"  ! {d['ats']}/{d['slug']}: {e}")
                continue
            if jobs is None:
                print(f"  ! {d['ats']}/{d['slug']}: no responde")
                continue
            print(f"[ats] {d['ats']}/{d['slug']}: {len(jobs)} ofertas")
            for j in jobs:
                filas.append({"ats": d["ats"], "slug": d["slug"], **j})
            time.sleep(1)
    return pd.DataFrame(filas)


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    jobspy = recoger_jobspy()
    jobspy.to_csv(OUT / "jobspy.csv", index=False)

    tecno = recoger_tecnoempleo()
    tecno.to_csv(OUT / "tecnoempleo.csv", index=False)

    detectados = detectar_ats(pd.concat([jobspy, tecno], ignore_index=True))
    detectados.to_csv(OUT / "ats_detectados.csv", index=False)
    print(f"[ats] {len(detectados)} empresas con ATS detectado")
    if len(detectados):
        recoger_ats(detectados).to_csv(OUT / "ats.csv", index=False)

    print(f"\nCSVs en {OUT}")


if __name__ == "__main__":
    main()
