"""Almacén SQLite: la única fuente de verdad del sistema.

Trazabilidad: cada Oferta apunta al Bruto del que sale y cada Bruto a la
Ejecución que lo trajo (con la versión del conector). El Bruto es inmutable:
si una fuente devuelve el mismo contenido otra vez, no se duplica; si cambia,
se guarda como un bruto nuevo.

El esquema se crea con migraciones numeradas, así puede crecer sin perder datos.
Diseño en docs/modelo.md.
"""

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import sqlite_utils

RAIZ = Path(__file__).resolve().parents[2]
# Datos personales y resultados: fuera del repo. En Docker, un volumen.
DATOS = Path(os.environ.get("JOB_RADAR_DATOS", RAIZ / "data"))
RUTA_DB = DATOS / "job_radar.db"

MIGRACIONES: list[str] = [
    # 1 · entidades de la ingesta
    """
    CREATE TABLE fuente (
        id              TEXT PRIMARY KEY,           -- 'freehire', 'infojobs', 'linkedin', 'indeed', 'ats'
        tipo            TEXT NOT NULL,              -- agregador, portal, api_terceros, ats
        conector        TEXT NOT NULL,              -- versión activa, p. ej. 'linkedin-fantastic-apify/1'
        activa          INTEGER NOT NULL DEFAULT 1,
        actualizada_en  TEXT NOT NULL
    );

    CREATE TABLE busqueda (
        id              TEXT PRIMARY KEY,           -- 'linkedin:malaga-tech'
        fuente_id       TEXT NOT NULL REFERENCES fuente(id),
        parametros      TEXT NOT NULL,              -- JSON
        frecuencia_h    INTEGER NOT NULL
    );

    CREATE TABLE ejecucion (
        id              INTEGER PRIMARY KEY,
        fuente_id       TEXT NOT NULL REFERENCES fuente(id),
        busqueda_id     TEXT REFERENCES busqueda(id),
        conector        TEXT NOT NULL,
        inicio          TEXT NOT NULL,
        fin             TEXT,
        estado          TEXT NOT NULL DEFAULT 'en_curso',   -- en_curso, ok, parcial, error
        recibidos       INTEGER NOT NULL DEFAULT 0,
        nuevos          INTEGER NOT NULL DEFAULT 0,
        actualizados    INTEGER NOT NULL DEFAULT 0,
        errores_norm    INTEGER NOT NULL DEFAULT 0,
        cuota           TEXT,                       -- JSON: lo que diga la fuente de su cuota
        coste_usd       REAL,
        error           TEXT
    );

    CREATE TABLE bruto (
        id              INTEGER PRIMARY KEY,
        ejecucion_id    INTEGER NOT NULL REFERENCES ejecucion(id),
        fuente_id       TEXT NOT NULL REFERENCES fuente(id),
        id_externo      TEXT NOT NULL,
        payload         TEXT NOT NULL,              -- JSON tal cual, sin datos personales
        hash            TEXT NOT NULL,
        eliminados      TEXT,                       -- JSON: campos personales quitados antes de guardar
        recibido_en     TEXT NOT NULL,
        UNIQUE (fuente_id, hash)
    );
    CREATE INDEX bruto_externo ON bruto (fuente_id, id_externo);

    CREATE TABLE empresa (
        id              INTEGER PRIMARY KEY,
        nombre          TEXT NOT NULL,
        clave           TEXT NOT NULL UNIQUE,       -- nombre normalizado
        alias           TEXT,                       -- JSON
        dominio         TEXT,
        linkedin_slug   TEXT,
        sector          TEXT,
        tamano          TEXT,
        es_agencia      INTEGER,
        creada_en       TEXT NOT NULL
    );

    CREATE TABLE puesto (
        id              INTEGER PRIMARY KEY,
        titulo          TEXT NOT NULL,
        empresa_id      INTEGER REFERENCES empresa(id),   -- cliente final, si se sabe
        ciudad          TEXT,
        pais            TEXT,
        modalidad       TEXT,
        fusion          TEXT,                       -- JSON: campo → {valor, oferta_id}
        estado          TEXT NOT NULL DEFAULT 'abierto',
        creado_en       TEXT NOT NULL,
        actualizado_en  TEXT NOT NULL
    );

    CREATE TABLE oferta (
        id              INTEGER PRIMARY KEY,
        fuente_id       TEXT NOT NULL REFERENCES fuente(id),
        id_externo      TEXT NOT NULL,
        bruto_id        INTEGER NOT NULL REFERENCES bruto(id),     -- el último que la actualizó
        conector        TEXT NOT NULL,
        url             TEXT,
        titulo          TEXT NOT NULL,
        empresa         TEXT,
        empresa_id      INTEGER REFERENCES empresa(id),
        ciudad          TEXT,
        region          TEXT,
        pais            TEXT,
        modalidad       TEXT,                       -- presencial, hibrido, remoto
        salario_min     REAL,
        salario_max     REAL,
        salario_moneda  TEXT,
        salario_periodo TEXT,                       -- hora, dia, semana, mes, ano
        descripcion     TEXT,
        publicada_en    TEXT,
        experiencia     TEXT,
        contrato        TEXT,
        skills          TEXT,                       -- JSON
        ingles          TEXT,
        es_agencia      INTEGER,
        derivados       TEXT,                       -- JSON: campos inferidos por un modelo, no dichos por la fuente
        puesto_id       INTEGER REFERENCES puesto(id),
        vista_primera   TEXT NOT NULL,
        vista_ultima    TEXT NOT NULL,
        cerrada_en      TEXT,
        UNIQUE (fuente_id, id_externo)
    );
    CREATE INDEX oferta_puesto ON oferta (puesto_id);
    CREATE INDEX oferta_publicada ON oferta (publicada_en);
    """,
    # 2 · completitud por campo en cada ejecución: detecta cambios de formato silenciosos
    """
    ALTER TABLE ejecucion ADD COLUMN completitud TEXT;   -- JSON: campo → % de ofertas con valor
    CREATE INDEX ejecucion_fuente ON ejecucion (fuente_id, inicio);
    """,
    # 3 · etiquetas de Rubén por puesto: la vara de medir de la puntuación (Fase 4)
    """
    CREATE TABLE etiqueta (
        puesto_id       INTEGER PRIMARY KEY REFERENCES puesto(id),
        valor           TEXT NOT NULL CHECK (valor IN ('top', 'no_top')),
        motivo          TEXT,
        creada_en       TEXT NOT NULL,
        actualizada_en  TEXT NOT NULL
    );
    """,
    # 4 · evaluaciones: el encaje de un puesto con el perfil, por versión de rúbrica (Fase 4)
    """
    CREATE TABLE evaluacion (
        id              INTEGER PRIMARY KEY,
        puesto_id       INTEGER NOT NULL REFERENCES puesto(id),
        rubrica         TEXT NOT NULL,              -- 'rubrica/1'
        perfil          TEXT NOT NULL,              -- huella del perfil y las preferencias usados
        motor           TEXT NOT NULL,
        modelo          TEXT NOT NULL,
        resultado       TEXT NOT NULL,              -- JSON: veredictos del modelo + verificación de citas
        nota            INTEGER NOT NULL,           -- 0-100, calculada en Python
        vetado          INTEGER NOT NULL DEFAULT 0,
        motivo_veto     TEXT,
        marcas          TEXT,                       -- JSON: avisos que no vetan (p. ej. inglés C1)
        coste_usd       REAL,
        tokens_entrada  INTEGER,
        tokens_salida   INTEGER,
        duracion_ms     INTEGER,
        creada_en       TEXT NOT NULL
    );
    CREATE INDEX evaluacion_puesto ON evaluacion (puesto_id, rubrica, creada_en);
    """,
]


def ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def abrir(ruta: Path | str = RUTA_DB) -> sqlite_utils.Database:
    """Abre (o crea) la base y aplica las migraciones pendientes."""
    if str(ruta) != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite_utils.Database(ruta)
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")  # la web leerá mientras la ingesta escribe
    migrar(db)
    return db


def version(db: sqlite_utils.Database) -> int:
    if "_migracion" not in db.table_names():
        return 0
    return db.execute("SELECT COALESCE(MAX(version), 0) FROM _migracion").fetchone()[0]


def migrar(db: sqlite_utils.Database) -> int:
    db.execute("CREATE TABLE IF NOT EXISTS _migracion (version INTEGER PRIMARY KEY, aplicada_en TEXT NOT NULL)")
    actual = version(db)
    for n, sql in enumerate(MIGRACIONES[actual:], start=actual + 1):
        with db.conn:
            db.conn.executescript(f"BEGIN;\n{sql}\nINSERT INTO _migracion VALUES ({n}, '{ahora()}');\nCOMMIT;")
    return version(db)


# --- operaciones de la ingesta -------------------------------------------------

def registrar_fuente(db, id: str, tipo: str, conector: str, activa: bool = True) -> None:
    db["fuente"].upsert({"id": id, "tipo": tipo, "conector": conector, "activa": int(activa),
                         "actualizada_en": ahora()}, pk="id")


def guardar_busqueda(db, id: str, fuente_id: str, parametros: dict, frecuencia_h: int) -> None:
    db["busqueda"].upsert({"id": id, "fuente_id": fuente_id, "frecuencia_h": frecuencia_h,
                           "parametros": json.dumps(parametros, ensure_ascii=False, sort_keys=True)}, pk="id")


def iniciar_ejecucion(db, fuente_id: str, conector: str, busqueda_id: str | None = None) -> int:
    return db["ejecucion"].insert({"fuente_id": fuente_id, "busqueda_id": busqueda_id,
                                   "conector": conector, "inicio": ahora()}).last_pk


def cerrar_ejecucion(db, ejecucion_id: int, estado: str, **metricas) -> None:
    for campo in ("cuota", "completitud"):
        if campo in metricas and not isinstance(metricas[campo], str | None):
            metricas[campo] = json.dumps(metricas[campo], ensure_ascii=False)
    db["ejecucion"].update(ejecucion_id, {"fin": ahora(), "estado": estado, **metricas})


def hash_payload(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def guardar_bruto(db, ejecucion_id: int, fuente_id: str, id_externo: str, payload: dict,
                  eliminados: list[str] | None = None) -> tuple[int, bool]:
    """Guarda la respuesta tal cual. Devuelve (bruto_id, nuevo). Mismo contenido → mismo bruto."""
    h = hash_payload(payload)
    existente = db.execute("SELECT id FROM bruto WHERE fuente_id = ? AND hash = ?", [fuente_id, h]).fetchone()
    if existente:
        return existente[0], False
    return db["bruto"].insert({
        "ejecucion_id": ejecucion_id, "fuente_id": fuente_id, "id_externo": id_externo,
        "payload": json.dumps(payload, ensure_ascii=False), "hash": h,
        "eliminados": json.dumps(eliminados) if eliminados else None, "recibido_en": ahora(),
    }).last_pk, True


CAMPOS_JSON = ("skills", "derivados")


def guardar_oferta(db, oferta: dict, bruto_id: int, conector: str) -> tuple[int, bool]:
    """Inserta o actualiza una oferta normalizada. Devuelve (oferta_id, nueva).

    Conserva `vista_primera` y la asignación a puesto; actualiza el resto y
    `vista_ultima`, y la reabre si estaba cerrada.
    """
    fila = {k: (json.dumps(v, ensure_ascii=False) if k in CAMPOS_JSON and v is not None else v)
            for k, v in oferta.items()}
    fila |= {"bruto_id": bruto_id, "conector": conector, "vista_ultima": ahora(), "cerrada_en": None}
    previa = db.execute("SELECT id FROM oferta WHERE fuente_id = ? AND id_externo = ?",
                        [oferta["fuente_id"], oferta["id_externo"]]).fetchone()
    if previa:
        db["oferta"].update(previa[0], fila)
        return previa[0], False
    return db["oferta"].insert(fila | {"vista_primera": fila["vista_ultima"]}).last_pk, True
