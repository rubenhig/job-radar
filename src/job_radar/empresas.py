"""Empresas: quién está detrás de los puestos, para seguirlas o descartarlas.

La lista se llena sola desde las ofertas: el nombre se normaliza (`clave_empresa`: «ARELANCE S.L.» y
«Arelance» son la misma) y cada oferta y cada puesto quedan enlazados a su empresa. Rubén decide el
estado (seguida, pendiente, descartada) y escribe notas. Una empresa descartada hace que la criba
descarte sus puestos; el encaje (mejor nota, cuántos de IA, si contrata en remoto) se calcula con sus
puestos, no se escribe a mano.

Las consultoras casi nunca vienen marcadas por la fuente: además de `es_agencia`, cuenta lo que dice la
puntuación de sus puestos (veredicto «intermediario»).
"""

import json
from collections import Counter, defaultdict

from job_radar import almacen
from job_radar.puestos import clave_empresa


def actualizar(db) -> dict[str, int]:
    """Crea las empresas que falten, enlaza ofertas y puestos, y ajusta nombres, alias y agencias."""
    m = Counter()
    ahora = almacen.ahora()
    por_clave = {r["clave"]: r["id"] for r in db.query("SELECT id, clave FROM empresa")}
    nombres = defaultdict(Counter)
    for o in db.query("SELECT id, empresa, empresa_id, es_agencia FROM oferta WHERE empresa IS NOT NULL"):
        clave = clave_empresa(o["empresa"])
        if not clave:
            continue
        if clave not in por_clave:
            por_clave[clave] = db["empresa"].insert({"nombre": o["empresa"].strip(), "clave": clave,
                                                     "creada_en": ahora}).last_pk
            m["creadas"] += 1
        nombres[por_clave[clave]][o["empresa"].strip()] += 1
        if o["empresa_id"] != por_clave[clave]:
            db.execute("UPDATE oferta SET empresa_id = ? WHERE id = ?", [por_clave[clave], o["id"]])
            m["ofertas_enlazadas"] += 1
    for empresa_id, cuenta in nombres.items():  # el nombre, el que más se usa; los demás, alias
        nombre = cuenta.most_common(1)[0][0]
        alias = json.dumps(sorted(cuenta), ensure_ascii=False) if len(cuenta) > 1 else None
        db.execute("UPDATE empresa SET nombre = ?, alias = ? WHERE id = ? AND (nombre != ? OR alias IS NOT ?)",
                   [nombre, alias, empresa_id, nombre, alias])
    db.execute("""UPDATE empresa SET es_agencia = 1 WHERE es_agencia IS NOT 1
                  AND id IN (SELECT empresa_id FROM oferta WHERE es_agencia = 1)""")
    for p in db.query("SELECT id, fusion, empresa_id FROM puesto WHERE estado IN ('abierto', 'cerrado')"):
        nombre = (json.loads(p["fusion"] or "{}").get("empresa") or {}).get("valor")
        empresa_id = por_clave.get(clave_empresa(nombre)) if nombre else None
        if empresa_id != p["empresa_id"]:
            db.execute("UPDATE puesto SET empresa_id = ? WHERE id = ?", [empresa_id, p["id"]])
            m["puestos_enlazados"] += 1
    db.conn.commit()
    return dict(m)
