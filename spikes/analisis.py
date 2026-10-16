"""Spike: resume qué datos dio cada fuente (lee los CSVs de data/spike/)."""

import re
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parent.parent / "data" / "spike"

IA = re.compile(r"\b(?:ia|ai|llm|genai|gen ai|agent\w*|agente\w*|rag|machine learning|ml)\b", re.I)
MALAGA = re.compile(r"m[áa]laga|marbella|torremolinos|benalm[áa]dena|fuengirola|estepona|antequera", re.I)
ESPANA_O_REMOTO = re.compile(r"spain|españa|espana|remot|europe|emea|madrid|barcelona|valencia|sevilla|m[áa]laga", re.I)


def pct(serie: pd.Series) -> str:
    return f"{100 * serie.mean():.0f}%" if len(serie) else "-"


def clave(titulo, empresa) -> str:
    return re.sub(r"\W+", " ", f"{titulo} {empresa}".lower()).strip()


def seccion(titulo: str):
    print(f"\n{'=' * 70}\n{titulo}\n{'=' * 70}")


def analizar_jobspy():
    df = pd.read_csv(DIR / "jobspy.csv")
    seccion(f"JOBSPY — {len(df)} filas")

    print("\nPor sitio y búsqueda:")
    print(df.pivot_table(index="busqueda", columns=["ubicacion_busqueda", "site"], values="id",
                         aggfunc="count", fill_value=0).to_string())

    df["clave"] = [clave(t, c) for t, c in zip(df["title"], df["company"])]
    unicas = df.drop_duplicates("clave")
    entre_sitios = df.groupby("clave")["site"].nunique()
    print(f"\nOfertas únicas: {len(unicas)} de {len(df)} filas "
          f"({len(df) - len(unicas)} repetidas entre búsquedas/sitios)")
    print(f"Ofertas que aparecen en más de un sitio: {(entre_sitios > 1).sum()}")

    print("\nCalidad de campos (sobre ofertas únicas), por sitio:")
    calidad = unicas.groupby("site").apply(lambda g: pd.Series({
        "n": len(g),
        "salario": pct(g["min_amount"].notna()),
        "is_remote informado": pct(g["is_remote"].notna()),
        "remoto=True": pct(g["is_remote"] == True),  # noqa: E712
        "descripción >300c": pct(g["description"].fillna("").str.len() > 300),
        "url directa": pct(g["job_url_direct"].notna()),
        "título con IA": pct(g["title"].fillna("").str.contains(IA)),
    }), include_groups=False)
    print(calidad.to_string())

    malaga = unicas[unicas["ubicacion_busqueda"] == "malaga"]
    en_malaga = malaga["location"].fillna("").str.contains(MALAGA)
    print(f"\nBúsquedas 'Málaga': {pct(en_malaga)} de las ofertas están realmente en la provincia "
          f"({en_malaga.sum()}/{len(malaga)}). Ubicaciones más comunes:")
    print(malaga["location"].value_counts().head(8).to_string())

    print("\nEmpresas con más ofertas:")
    print(unicas["company"].value_counts().head(15).to_string())

    print("\nMuestra de ofertas en Málaga con IA en el título:")
    muestra = malaga[en_malaga & malaga["title"].fillna("").str.contains(IA)]
    for _, f in muestra.head(12).iterrows():
        print(f"  - [{f['site']}] {f['title']} — {f['company']} ({f['location']})")


def analizar_tecnoempleo():
    df = pd.read_csv(DIR / "tecnoempleo.csv").fillna("")
    seccion(f"TECNOEMPLEO — {len(df)} ofertas (últimas del feed, toda España)")
    print("\nProvincia/modalidad más comunes:")
    print(df["provincia"].value_counts().head(10).to_string())
    texto = df["title"] + " " + df["description"]
    ia = texto.str.contains(IA)
    sitio = (df["provincia"] + " " + df["poblacion"]).str.contains(MALAGA) | df["provincia"].str.contains("remoto|teletrabajo", case=False)
    print(f"\nCon IA: {ia.sum()} · En Málaga o 100% remoto: {sitio.sum()} · Ambas: {(ia & sitio).sum()}")
    for _, f in df[ia & sitio].iterrows():
        print(f"  - {f['title']} — {f['company']} ({f['provincia']})")


def analizar_ats():
    if not (DIR / "ats.csv").exists():
        return
    det = pd.read_csv(DIR / "ats_detectados.csv")
    df = pd.read_csv(DIR / "ats.csv").fillna("")
    seccion(f"ATS — {len(det)} empresas detectadas, {len(df)} ofertas en sus webs de empleo")
    df["es_o_remoto"] = (df["location"].astype(str) + " " + df["remote"].astype(str)).str.contains(ESPANA_O_REMOTO)
    df["ia"] = df["title"].str.contains(IA)
    resumen = df.groupby(["ats", "slug"]).agg(
        ofertas=("title", "size"), espana_o_remoto=("es_o_remoto", "sum"), con_ia=("ia", "sum"))
    print(resumen.sort_values("ofertas", ascending=False).to_string())
    print("\nOfertas con IA y compatibles con España/remoto:")
    for _, f in df[df["ia"] & df["es_o_remoto"]].head(15).iterrows():
        print(f"  - [{f['slug']}] {f['title']} ({f['location']}, {f['remote']})")


if __name__ == "__main__":
    analizar_jobspy()
    analizar_tecnoempleo()
    analizar_ats()
