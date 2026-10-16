"""Agrupar ofertas en puestos: la misma vacante, venga de la fuente o la consultora que venga.

Tres reglas, calibradas con las ofertas reales de Málaga (16-oct-2026):

  0. Siempre, títulos compatibles: uno contiene al otro, quitando seniority y
     palabras vacías. Ninguna medida difusa separa «Senior AI Engineer» de
     «Senior Backend Engineer» (91 y 89), pero cada uno tiene su palabra propia.
  1. Misma empresa: la misma oferta en varias fuentes.
  2. Descripción casi idéntica: reenvíos de agregadores (EngRadar, WhatJobs)
     con otra empresa.
  3. Título parecido y descripción que comparte los términos raros: la misma
     vacante publicada por varias consultoras. Cada consultora reescribe el
     anuncio, así que la similitud de texto normal no sirve (55-68 tanto para el
     mismo puesto como para puestos distintos). Lo que comparten son los términos
     poco frecuentes (MCP, SDD, LangGraph, el horario…), y eso se mide pesando
     cada palabra por su rareza en el corpus (IDF).

Solo se comparan ofertas de la misma zona (ciudad, o remoto en el mismo país).
Los grupos se recalculan en una ventana de días, y cada grupo conserva el
puesto que ya tenía la mayoría de sus ofertas, para que los ids sean estables.
"""

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from itertools import combinations

from cleanco import basename
from rapidfuzz import fuzz

from job_radar import almacen

VENTANA_DIAS = 60
UMBRAL_EMPRESA = 90
UMBRAL_TITULO_CONSULTORAS = 80
UMBRAL_REENVIO = 0.9
UMBRAL_CONSULTORAS = 0.35

# Para comparar títulos: palabras que no distinguen un puesto de otro, y sinónimos.
VACIAS = {"senior", "junior", "mid", "de", "del", "la", "el", "los", "las", "y", "e", "a", "o", "en", "con",
          "para", "the", "and", "of", "for", "with", "to", "h", "m", "x", "f", "d"}
SINONIMOS = {"ia": "ai", "sr": "senior", "jr": "junior", "desarrollador": "developer", "programador": "developer",
             "ingeniero": "engineer", "dev": "developer", "fullstack": "full stack", "backend": "back end",
             "frontend": "front end", "tecnico": "technical", "lider": "lead"}

# Al fusionar, de qué fuente se fía más cada campo (docs/modelo.md).
PRIORIDAD = ["infojobs", "linkedin", "freehire", "indeed"]
CAMPOS = ["titulo", "empresa", "ciudad", "region", "pais", "modalidad", "descripcion", "experiencia",
          "contrato", "skills", "ingles", "url"]
SALARIO = ["salario_min", "salario_max", "salario_moneda", "salario_periodo"]


def _plano(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def clave_empresa(nombre: str | None) -> str:
    """'ARELANCE S.L.' y 'Arelance' → 'arelance'."""
    e = _plano(basename(nombre or ""))
    e = re.sub(r"\b(s\.?l\.?u?|s\.?a\.?u?|group|grupo|spain|espana|iberia|ltd|gmbh|inc)\b", " ", e)
    return re.sub(r"\W+", " ", e).strip()


def clave_titulo(titulo: str) -> str:
    """Sin lo que no es del puesto: (m/f/d), modalidad, ciudad, códigos."""
    t = _plano(titulo)
    t = re.sub(r"\(.*?\)|\[.*?\]|\bm/f/d\b|\bh/m/x?\b|\bm/f\b", " ", t)
    t = re.sub(r"\b(hibrido|hybrid|remoto|remote|presencial|malaga|teletrabajo|100%)\b", " ", t)
    t = re.sub(r"\b[0-9a-z]*\d[0-9a-z]*\b", " ", t)  # códigos internos como 02CC
    return re.sub(r"\W+", " ", t).strip()


def palabras_titulo(titulo: str) -> frozenset[str]:
    salida = set()
    for w in " ".join(SINONIMOS.get(w, w) for w in clave_titulo(titulo).split()).split():
        w = SINONIMOS.get(w, w)
        if w not in VACIAS:
            salida.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return frozenset(salida)


def titulos_compatibles(a: frozenset[str], b: frozenset[str]) -> bool:
    """Uno contiene al otro: «Technical Lead / SR Python» ⊂ «Senior Python Developer / Technical Lead».
    Si cada uno tiene su palabra propia («AI Engineer» y «Backend Engineer»), son puestos distintos."""
    return bool(a and b) and (a <= b or b <= a)


def _palabras(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][a-z0-9+#.\-]*[a-z0-9+#]", _plano(texto))}


def zona(o: dict) -> str | None:
    if o.get("ciudad"):
        return "ciudad:" + re.sub(r"\W+", " ", _plano(o["ciudad"])).strip()
    if o.get("modalidad") == "remoto" and o.get("pais"):
        return "remoto:" + o["pais"]
    return None


class _Grupos:
    def __init__(self, ids):
        self.padre = {i: i for i in ids}

    def raiz(self, i):
        while self.padre[i] != i:
            self.padre[i] = self.padre[self.padre[i]]
            i = self.padre[i]
        return i

    def unir(self, a, b):
        self.padre[self.raiz(a)] = self.raiz(b)

    def grupos(self):
        g = defaultdict(list)
        for i in self.padre:
            g[self.raiz(i)].append(i)
        return list(g.values())


def mismo_puesto(a: dict, b: dict, idf: dict[str, float]) -> str | None:
    """La regla que los une, o None. `a` y `b` llevan `_titulo`, `_tokens`, `_empresa` y `_palabras` precalculados."""
    if not titulos_compatibles(a["_tokens"], b["_tokens"]):
        return None
    if a["_empresa"] and b["_empresa"] and fuzz.token_set_ratio(a["_empresa"], b["_empresa"]) >= UMBRAL_EMPRESA:
        return "misma_empresa"
    if not a["_palabras"] or not b["_palabras"]:
        return None
    comunes = sum(idf.get(w, 0) for w in a["_palabras"] & b["_palabras"])
    menor = min(sum(idf.get(w, 0) for w in a["_palabras"]), sum(idf.get(w, 0) for w in b["_palabras"]))
    parecido = comunes / menor if menor else 0
    if parecido >= UMBRAL_REENVIO:
        return "reenvio"
    titulo = (fuzz.token_set_ratio(a["_titulo"], b["_titulo"]) + fuzz.token_sort_ratio(a["_titulo"], b["_titulo"])) / 2
    if titulo >= UMBRAL_TITULO_CONSULTORAS and parecido >= UMBRAL_CONSULTORAS:
        return "consultoras"
    return None


def agrupar(ofertas: list[dict]) -> list[list[int]]:
    """Ofertas (filas del almacén) → grupos de ids. Puro: sin base de datos."""
    for o in ofertas:
        o["_titulo"] = clave_titulo(o["titulo"])
        o["_tokens"] = palabras_titulo(o["titulo"])
        o["_empresa"] = clave_empresa(o.get("empresa"))
        o["_palabras"] = _palabras(f"{o['titulo']} {o.get('descripcion') or ''}")
    frecuencia = Counter(w for o in ofertas for w in o["_palabras"])
    idf = {w: math.log(len(ofertas) / n) for w, n in frecuencia.items()}

    grupos = _Grupos([o["id"] for o in ofertas])
    por_zona = defaultdict(list)
    for o in ofertas:
        por_zona[zona(o)].append(o)
    for z, lista in por_zona.items():
        if z is None:
            continue
        for a, b in combinations(lista, 2):
            if mismo_puesto(a, b, idf):
                grupos.unir(a["id"], b["id"])
    return grupos.grupos()


def fusionar(ofertas: list[dict]) -> dict:
    """Cada campo del puesto, con la oferta de la que sale. Prioridad por fuente; dentro, la más reciente."""
    orden = sorted(ofertas, key=lambda o: (PRIORIDAD.index(o["fuente_id"]) if o["fuente_id"] in PRIORIDAD
                                           else len(PRIORIDAD), -(datetime.fromisoformat(o["vista_ultima"])
                                                                  .timestamp())))
    fusion = {}
    for campo in CAMPOS:
        o = next((o for o in orden if o.get(campo) not in (None, "", "[]")), None)
        if o:
            fusion[campo] = {"valor": o[campo], "oferta_id": o["id"], "fuente": o["fuente_id"]}
    con_salario = next((o for o in orden if o.get("salario_min") or o.get("salario_max")), None)
    if con_salario:  # el salario va en bloque: mínimo, máximo, moneda y periodo de la misma oferta
        fusion["salario"] = {"valor": {c: con_salario.get(c) for c in SALARIO},
                             "oferta_id": con_salario["id"], "fuente": con_salario["fuente_id"]}
    publicadas = [o["publicada_en"] for o in ofertas if o.get("publicada_en")]
    if publicadas:
        fusion["publicada_en"] = {"valor": min(publicadas)}
    fusion["vias"] = {"valor": sorted({f"{o['fuente_id']}:{o.get('empresa') or '?'}" for o in ofertas})}
    return fusion


def actualizar(db, dias: int = VENTANA_DIAS) -> dict[str, int]:
    """Recalcula los puestos de las ofertas vistas en la ventana. Devuelve cuántos se crean, cambian y fusionan."""
    desde = (datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="seconds")
    ofertas = [dict(r) for r in db.query("SELECT * FROM oferta WHERE vista_ultima >= ?", [desde])]
    por_id = {o["id"]: o for o in ofertas}
    m = Counter()
    ahora = almacen.ahora()
    for ids in agrupar(ofertas):
        miembros = [por_id[i] for i in ids]
        previos = Counter(o["puesto_id"] for o in miembros if o["puesto_id"])
        if previos:
            # El que más ofertas tenía; a igualdad, el más antiguo. Los demás quedan fusionados en él.
            puesto_id = min(previos, key=lambda p: (-previos[p], p))
            for otro in set(previos) - {puesto_id}:
                db["puesto"].update(otro, {"estado": f"fusionado:{puesto_id}", "actualizado_en": ahora})
                m["fusionados"] += 1
        else:
            puesto_id = None
        fusion = fusionar(miembros)
        fila = {"titulo": fusion["titulo"]["valor"], "ciudad": fusion.get("ciudad", {}).get("valor"),
                "pais": fusion.get("pais", {}).get("valor"), "modalidad": fusion.get("modalidad", {}).get("valor"),
                "fusion": json.dumps(fusion, ensure_ascii=False), "actualizado_en": ahora}
        if puesto_id is None:
            puesto_id = db["puesto"].insert(fila | {"creado_en": ahora, "estado": "abierto"}).last_pk
            m["creados"] += 1
        elif json.loads(db["puesto"].get(puesto_id)["fusion"] or "{}") != fusion:
            db["puesto"].update(puesto_id, fila | {"estado": "abierto"})
            m["actualizados"] += 1
        sin_asignar = [o["id"] for o in miembros if o["puesto_id"] != puesto_id]
        if sin_asignar:
            db.execute(f"UPDATE oferta SET puesto_id = ? WHERE id IN ({','.join('?' * len(sin_asignar))})",
                       [puesto_id, *sin_asignar])
    db.conn.commit()
    return dict(m)
