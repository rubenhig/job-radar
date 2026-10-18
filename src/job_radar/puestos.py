"""Agrupar ofertas en puestos: la misma vacante, venga de la fuente o la consultora que venga.

Tres reglas, calibradas con las ofertas reales de Málaga (16-oct-2026):

  0. Siempre, títulos compatibles: uno contiene al otro, quitando seniority y
     palabras vacías. Ninguna medida difusa separa «Senior AI Engineer» de
     «Senior Backend Engineer» (91 y 89), pero cada uno tiene su palabra propia.
  1. Misma empresa: la misma oferta en varias fuentes. Si los títulos no son
     iguales, la descripción también tiene que parecerse (una empresa publica
     varios puestos con títulos que se contienen: «Java Architect + AI» y «AI Architect»).
  2. Descripción casi idéntica: reenvíos de agregadores (EngRadar, WhatJobs)
     con otra empresa.
  3. Título parecido y descripción que comparte los términos raros: la misma
     vacante publicada por varias consultoras. Cada consultora reescribe el
     anuncio, así que la similitud de texto normal no sirve (55-68 tanto para el
     mismo puesto como para puestos distintos). Lo que comparten son los términos
     poco frecuentes (MCP, SDD, LangGraph, el horario…), y eso se mide pesando
     cada palabra por su rareza en el corpus (IDF). Las consultoras no se anuncian
     como tales («En X buscamos…»), así que no se puede exigir que lo sean.

Los grupos no se encadenan: dos grupos se unen solo si la mayoría de los pares
entre ellos cumple alguna regla (enlace medio), no por un único puente.

Solo se comparan ofertas de la misma zona (ciudad, o remoto en el mismo país);
una oferta sin modalidad está en las dos zonas.
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
CADUCIDAD_DIAS = 45   # una oferta publicada hace más y que no se ha vuelto a ver en NO_VISTA_DIAS se da por cerrada
NO_VISTA_DIAS = 14
UMBRAL_EMPRESA = 90
UMBRAL_TITULO_CONSULTORAS = 80
UMBRAL_REENVIO = 0.9
UMBRAL_CONSULTORAS = 0.35
UMBRAL_MISMA_EMPRESA = 0.35  # descripción que deben compartir dos títulos distintos de la misma empresa
ENLACE = 0.5                 # fracción de pares que deben casar para unir dos grupos
FUERZA = {"misma_empresa": 0, "reenvio": 1, "consultoras": 2}

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


# Lo que no es del puesto. Lo demás entre paréntesis sí lo es: «(AI Training)», «(Infraestructura IA)».
RUIDO_TITULO = re.compile(
    r"\b(m/f/d|m/w/d|f/m/d|x/f/m|h/m/x|h/m|m/f|all genders|ref|hibrido|hybrid|remoto|remote|presencial|teletrabajo|"
    r"full|anywhere|worldwide|europe|emea|spain|espana|malaga|madrid|barcelona|sevilla|valencia)\b|100%")


def clave_titulo(titulo: str) -> str:
    """Sin lo que no es del puesto: (m/f/d), modalidad, ciudad, códigos."""
    t = RUIDO_TITULO.sub(" ", _plano(titulo))
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
    """Dónde se compara una oferta. En remoto la ciudad del anuncio no distingue el puesto:
    la misma vacante remota se publica en Madrid, Murcia y Málaga a la vez."""
    if o.get("modalidad") == "remoto" and o.get("pais"):
        return "remoto:" + o["pais"]
    if o.get("ciudad"):
        return "ciudad:" + re.sub(r"\W+", " ", _plano(o["ciudad"])).strip()
    return None


def zonas(o: dict) -> set[str]:
    """Una oferta sin modalidad (Indeed casi nunca la da) puede ser la versión remota del puesto:
    se compara también con las remotas de su país."""
    salida = {z} if (z := zona(o)) else set()
    if o.get("modalidad") is None and o.get("pais"):
        salida.add("remoto:" + o["pais"])
    return salida


def mismo_puesto(a: dict, b: dict, idf: dict[str, float]) -> str | None:
    """La regla que los une, o None. `a` y `b` llevan `_titulo`, `_tokens`, `_empresa` y `_palabras` precalculados."""
    if not titulos_compatibles(a["_tokens"], b["_tokens"]):
        return None
    misma_empresa = (a["_empresa"] and b["_empresa"]
                     and fuzz.token_set_ratio(a["_empresa"], b["_empresa"]) >= UMBRAL_EMPRESA)
    if misma_empresa and a["_tokens"] == b["_tokens"]:
        return "misma_empresa"
    if not a["_palabras"] or not b["_palabras"]:
        return None
    comunes = sum(idf.get(w, 0) for w in a["_palabras"] & b["_palabras"])
    menor = min(sum(idf.get(w, 0) for w in a["_palabras"]), sum(idf.get(w, 0) for w in b["_palabras"]))
    parecido = comunes / menor if menor else 0
    if misma_empresa and parecido >= UMBRAL_MISMA_EMPRESA:
        return "misma_empresa"
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

    por_zona = defaultdict(list)
    for o in ofertas:
        for z in zonas(o):
            por_zona[z].append(o)
    pares = {}  # los que cumplen alguna regla → la regla
    for lista in por_zona.values():
        for a, b in combinations(lista, 2):
            par = frozenset((a["id"], b["id"]))
            if par not in pares and (regla := mismo_puesto(a, b, idf)):
                pares[par] = regla

    # Enlace medio: dos grupos se unen si al menos la mitad de sus pares casan. Así un título
    # genérico («AI Engineer») no hace de puente entre puestos distintos de la misma empresa.
    # Primero las reglas fuertes: la misma oferta en varias fuentes se junta antes de compararla con otras.
    grupo_de = {o["id"]: frozenset([o["id"]]) for o in ofertas}
    for par in sorted(pares, key=lambda p: (FUERZA[pares[p]], sorted(p))):
        a, b = (grupo_de[i] for i in par)
        if a is b:
            continue
        casan = sum(frozenset((x, y)) in pares for x in a for y in b)
        if casan >= ENLACE * len(a) * len(b):
            unido = a | b
            for i in unido:
                grupo_de[i] = unido
    return [sorted(g) for g in set(grupo_de.values())]


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


def heredar_etiqueta(db, origen: int, destino: int) -> None:
    """Al fusionar puestos, la etiqueta de Rubén pasa al que queda. Si los dos tenían, gana la más reciente."""
    if "etiqueta" not in db.table_names():
        return
    db.execute("""INSERT INTO etiqueta (puesto_id, valor, motivo, creada_en, actualizada_en)
                  SELECT ?, valor, motivo, creada_en, actualizada_en FROM etiqueta WHERE puesto_id = ?
                  ON CONFLICT (puesto_id) DO UPDATE SET valor = excluded.valor, motivo = excluded.motivo,
                      actualizada_en = excluded.actualizada_en
                  WHERE excluded.actualizada_en > etiqueta.actualizada_en""", [destino, origen])
    db.execute("DELETE FROM etiqueta WHERE puesto_id = ?", [origen])


def heredar_guardado(db, origen: int, destino: int) -> None:
    """Al fusionar puestos, lo guardado en Mi lista pasa al que queda (si este no estaba ya guardado)."""
    if "guardado" not in db.table_names():
        return
    db.execute("""INSERT OR IGNORE INTO guardado (puesto_id, estado, prioridad, notas, etiquetas, historial,
                                                  creado_en, actualizado_en)
                  SELECT ?, estado, prioridad, notas, etiquetas, historial, creado_en, actualizado_en
                  FROM guardado WHERE puesto_id = ?""", [destino, origen])
    db.execute("DELETE FROM guardado WHERE puesto_id = ?", [origen])


def actualizar(db, dias: int = VENTANA_DIAS) -> dict[str, int]:
    """Recalcula los puestos de las ofertas vistas en la ventana. Devuelve cuántos se crean, cambian y fusionan."""
    desde = (datetime.now(UTC) - timedelta(days=dias)).isoformat(timespec="seconds")
    ofertas = [dict(r) for r in db.query("SELECT * FROM oferta WHERE vista_ultima >= ?", [desde])]
    por_id = {o["id"]: o for o in ofertas}
    m = Counter()
    ahora = almacen.ahora()
    usados = set()  # si un grupo se parte, cada trozo necesita su propio puesto
    for ids in sorted(agrupar(ofertas), key=len, reverse=True):  # el trozo grande conserva el puesto
        miembros = [por_id[i] for i in ids]
        previos = Counter(o["puesto_id"] for o in miembros if o["puesto_id"] and o["puesto_id"] not in usados)
        if previos:
            # El que más ofertas tenía; a igualdad, el más antiguo. Los demás quedan fusionados en él.
            puesto_id = min(previos, key=lambda p: (-previos[p], p))
            for otro in set(previos) - {puesto_id}:
                db["puesto"].update(otro, {"estado": f"fusionado:{puesto_id}", "actualizado_en": ahora})
                heredar_etiqueta(db, otro, puesto_id)
                heredar_guardado(db, otro, puesto_id)
                usados.add(otro)
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
        usados.add(puesto_id)
        sin_asignar = [o["id"] for o in miembros if o["puesto_id"] != puesto_id]
        if sin_asignar:
            db.execute(f"UPDATE oferta SET puesto_id = ? WHERE id IN ({','.join('?' * len(sin_asignar))})",
                       [puesto_id, *sin_asignar])
    db.conn.commit()
    return dict(m)


def cerrar(db, ahora: datetime | None = None) -> dict[str, int]:
    """Ciclo de vida. Una oferta se cierra si la fuente la da por cerrada o caducada (`valida_hasta`), o si se
    publicó hace más de CADUCIDAD_DIAS y no se ha vuelto a ver en NO_VISTA_DIAS (las búsquedas miran ventanas
    cortas: no volver a verla no basta). Un puesto se cierra cuando lo están todas sus ofertas, y se reabre si
    alguna vuelve (`guardar_oferta` reabre la oferta al verla de nuevo). Fechas comparadas a segundos (ISO)."""
    ahora = ahora or datetime.now(UTC)
    iso = lambda d: d.isoformat(timespec="seconds")[:19]  # noqa: E731 — las fuentes mezclan formatos de zona
    m = {}
    m["ofertas_cerradas"] = db.execute("""
        UPDATE oferta SET cerrada_en = ? WHERE cerrada_en IS NULL AND (
            (valida_hasta IS NOT NULL AND substr(valida_hasta, 1, 19) < ?)
            OR (substr(COALESCE(publicada_en, vista_primera), 1, 19) < ? AND substr(vista_ultima, 1, 19) < ?))""",
        [almacen.ahora(), iso(ahora), iso(ahora - timedelta(days=CADUCIDAD_DIAS)),
         iso(ahora - timedelta(days=NO_VISTA_DIAS))]).rowcount
    m["puestos_cerrados"] = db.execute("""
        UPDATE puesto SET estado = 'cerrado', actualizado_en = ? WHERE estado = 'abierto'
        AND NOT EXISTS (SELECT 1 FROM oferta o WHERE o.puesto_id = puesto.id AND o.cerrada_en IS NULL)""",
        [almacen.ahora()]).rowcount
    m["puestos_reabiertos"] = db.execute("""
        UPDATE puesto SET estado = 'abierto', actualizado_en = ? WHERE estado = 'cerrado'
        AND EXISTS (SELECT 1 FROM oferta o WHERE o.puesto_id = puesto.id AND o.cerrada_en IS NULL)""",
        [almacen.ahora()]).rowcount
    db.conn.commit()
    return {k: v for k, v in m.items() if v}
