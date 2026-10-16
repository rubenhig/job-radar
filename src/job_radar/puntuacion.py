"""Puntuación: ¿encaja este puesto con el perfil?

Claude no da la nota: da veredictos por criterio, cada uno con valores cerrados
y una cita literal de la oferta. Python comprueba que cada cita existe en la
oferta y calcula la nota con pesos fijos. Lo que no se puede comprobar se
marca, no se cree: una compuerta que no pasa sin cita verificada no veta.

Rúbrica v1, sobre las de career-ops y ai-job-search (ver docs/repositorios.md):
  - Compuertas (pasa / no pasa / marca): modalidad, elegibilidad, idioma.
    Cualquier "no pasa" con evidencia anula la nota; "marca" solo avisa.
  - Función: si el puesto no consiste en construir software (entrenar modelos
    como profesor o lingüista, consultoría de gobierno, ventas), se anula.
  - Dimensiones: encaje del rol de IA (40 %), cobertura de requisitos (30 %),
    función técnica (10 %), seniority (10 %) y fuente (10 %).
  - Requisitos en dos pasadas: primero qué pide la oferta y cuánto importa;
    después, con qué competencia del perfil se cubre. Lo inferido nunca es crítico.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from job_radar import almacen
from job_radar.llm import MotorLLM, Uso
from job_radar.perfil import verificar_cita
from job_radar.preferencias import Preferencias

RUBRICA = "rubrica/1"
MAX_DESCRIPCION = 12_000

# --- lo que devuelve el modelo --------------------------------------------------

Veredicto = Literal["pasa", "no_pasa", "marca", "sin_datos"]
CITA = "Frase LITERAL de la oferta que lo justifica, copiada carácter a carácter; null si la oferta no dice nada"


class Compuerta(BaseModel):
    veredicto: Veredicto
    cita: str | None = Field(None, description=CITA)
    motivo: str = Field(description="Una frase en español")


class Requisito(BaseModel):
    requisito: str = Field(description="El requisito tal como lo dice la oferta (literal y corto)")
    importancia: Literal["critico", "alto", "deseable"]
    origen: Literal["dicho", "inferido"] = Field(
        description="'dicho' si la oferta lo pide expresamente; 'inferido' si lo deduces tú. Lo inferido nunca es crítico")
    competencia: str | None = Field(None, description="Nombre EXACTO de la competencia del perfil que lo cubre, o null")
    cobertura: Literal["fuerte", "parcial", "falta"]


class Funcion(BaseModel):
    valor: Literal["ingenieria", "tecnica_adyacente", "no_construye_software"] = Field(
        description="ingenieria: diseñar y construir software o sistemas (incluido IA); tecnica_adyacente: QA, datos, "
                    "DevOps, consultoría con manos en el código; no_construye_software: entrenar o evaluar modelos como "
                    "experto (profesor, lingüista, finanzas…), consultoría de gobierno o normativa, ventas, docencia")
    cita: str | None = Field(None, description=CITA)
    motivo: str


class RolIA(BaseModel):
    valor: Literal["ia_principal", "software_con_ia", "software_sin_ia", "ninguno"] = Field(
        description="ia_principal: el puesto ES de IA/LLM (AI/LLM/GenAI Engineer, agentes en producción, arquitecto o "
                    "tech lead de IA, MLOps/plataforma LLM); software_con_ia: ingeniería de software donde la IA aparece "
                    "en las tareas; software_sin_ia: ingeniería de software sin IA, o ML clásico sin LLM; ninguno. "
                    "No fuerces un encaje que no hay")
    cita: str | None = Field(None, description=CITA)
    motivo: str


class Seniority(BaseModel):
    valor: Literal["por_debajo", "encaja", "reto", "muy_por_encima"] = Field(
        description="Respecto a la experiencia del candidato: por_debajo (junior/prácticas para él), encaja, "
                    "reto (algo por encima, alcanzable), muy_por_encima (director, principal, 10+ años)")
    cita: str | None = Field(None, description=CITA)
    motivo: str


class Fuente(BaseModel):
    valor: Literal["directa", "intermediario", "dudosa"] = Field(
        description="directa: publica la empresa que contrata; intermediario: consultora o agencia ('nuestro cliente', "
                    "empresa oculta); dudosa: oferta genérica, plataforma de microtareas o sin empleador claro")
    cita: str | None = Field(None, description=CITA)
    motivo: str


class Veredictos(BaseModel):
    resumen: str = Field(description="Qué es el puesto, en una frase en español")
    requisitos: list[Requisito] = Field(description="Hasta 10, los que más pesan; primero los críticos")
    modalidad: Compuerta = Field(description="¿Puede hacerlo el candidato? pasa: en sus ciudades (presencial/híbrido) "
                                             "o en remoto desde su país; no_pasa: presencial/híbrido en otra ciudad sin "
                                             "remoto, o remoto restringido a otros países; sin_datos")
    elegibilidad: Compuerta = Field(description="no_pasa: exige nacionalidad o permiso que no tiene (fuera de la UE), "
                                                "habilitación de seguridad; pasa; sin_datos")
    idioma: Compuerta = Field(description="marca: pide un nivel de inglés por encima del suyo (C1, nativo, 'fluent'); "
                                          "no_pasa: exige un idioma que no habla; pasa; sin_datos")
    funcion: Funcion
    rol_ia: RolIA
    seniority: Seniority
    fuente: Fuente


SISTEMA = """Evalúas si un puesto de trabajo encaja con un candidato concreto. Tu salida no es una nota:
son veredictos por criterio, con valores cerrados, que luego se combinan con reglas fijas.

Reglas:
- Basa cada veredicto en la oferta. Las citas son frases LITERALES de la oferta (título incluido),
  copiadas carácter a carácter, en su idioma original. Se comprueban automáticamente: una cita
  inventada o parafraseada invalida el criterio.
- Si la oferta no dice algo, usa sin_datos o null. No lo supongas.
- Requisitos, en dos pasadas: primero lee la oferta y anota qué pide y cuánto importa SIN mirar el
  perfil; después decide con qué competencia del perfil se cubre cada uno (nombre exacto o null).
- Lo que deduces tú es 'inferido' y nunca 'critico'.
- Los motivos y el resumen, en español y breves."""


# --- entradas: perfil y puesto como texto ---------------------------------------


def texto_perfil(perfil_cv: dict, prefs: Preferencias) -> str:
    p = perfil_cv["perfil"]
    lineas = [f"# Candidato: {p['titular']}", p["resumen"], "", "## Competencias (nombre · nivel · años)"]
    lineas += [f"- {c['nombre']} · {c['nivel']}" + (f" · {c['anos']:g}" if c.get("anos") else "")
               for c in p["competencias"]]
    lineas += ["", "## Experiencia"]
    lineas += [f"- {x['puesto']} en {x['empresa']} ({x['inicio']} – {x.get('fin') or 'actualidad'}): {x['resumen']}"
               for x in p["experiencias"]]
    lineas += ["", "## Idiomas"] + [f"- {i['idioma']}: {i['nivel']}" for i in p.get("idiomas", [])]
    lineas += ["", "## Lo que busca"]
    lineas += [f"- Roles principales: {', '.join(prefs.roles.principales)}",
               f"- Roles secundarios (puntúan más si tienen IA): {', '.join(prefs.roles.secundarios) or '—'}"]
    for u in prefs.ubicaciones:
        lineas.append(f"- En persona: {u.ciudad} ({u.pais}), {' o '.join(m.value for m in u.modalidades)}")
    if prefs.remoto and prefs.remoto.acepta:
        quien = [q for q, si in (("empresa local", prefs.remoto.empresa_local),
                                 ("empresa extranjera que contrate en su país", prefs.remoto.empresa_extranjera)) if si]
        lineas.append(f"- Remoto desde {prefs.remoto.desde_pais}: {', '.join(quien)}")
    for idioma, i in prefs.idiomas.items():
        lineas.append(f"- Nivel de {idioma}: {i.nivel}")
    return "\n".join(lineas)


def texto_puesto(puesto: dict, ofertas: list[dict]) -> str:
    """El texto de la oferta que se evalúa y contra el que se verifican las citas."""
    fusion = json.loads(puesto["fusion"] or "{}")
    id_desc = (fusion.get("descripcion") or {}).get("oferta_id")
    oferta = next((o for o in ofertas if o["id"] == id_desc), ofertas[0])
    vias = sorted({f"{o['fuente_id']}: {o['empresa'] or '?'}" for o in ofertas})
    datos = {
        "Título": puesto["titulo"],
        "Empresa": (fusion.get("empresa") or {}).get("valor"),
        "Publicada por": "; ".join(vias),
        "Ubicación": ", ".join(filter(None, [puesto.get("ciudad"), puesto.get("pais")])) or None,
        "Modalidad": puesto.get("modalidad"),
    }
    cabecera = "\n".join(f"{k}: {v}" for k, v in datos.items() if v)
    return f"{cabecera}\n\nDescripción:\n{(oferta.get('descripcion') or '')[:MAX_DESCRIPCION]}"


def huella_perfil(perfil_cv: dict, prefs: Preferencias) -> str:
    base = json.dumps([perfil_cv["meta"].get("cv_sha256"), prefs.model_dump(mode="json")], sort_keys=True)
    return hashlib.sha256(base.encode()).hexdigest()[:12]


# --- la nota, en Python ----------------------------------------------------------

PESOS = {"rol_ia": 0.40, "requisitos": 0.30, "funcion": 0.10, "seniority": 0.10, "fuente": 0.10}
VALORES = {
    "funcion": {"ingenieria": 1.0, "tecnica_adyacente": 0.5, "no_construye_software": 0.0},
    "rol_ia": {"ia_principal": 1.0, "software_con_ia": 0.67, "software_sin_ia": 0.33, "ninguno": 0.0},
    "seniority": {"encaja": 1.0, "reto": 0.6, "por_debajo": 0.6, "muy_por_encima": 0.0},
    "fuente": {"directa": 1.0, "intermediario": 0.6, "dudosa": 0.2},
}
PESO_IMPORTANCIA = {"critico": 2.0, "alto": 1.0}
COBERTURA = {"fuerte": 1.0, "parcial": 0.5, "falta": 0.0}


class Resultado(BaseModel):
    """La evaluación ya calculada: veredictos, citas comprobadas, nota y avisos."""

    veredictos: Veredictos
    citas_falsas: list[str]           # criterios cuya cita no aparece en la oferta
    nota: int
    vetado: bool
    motivo_veto: str | None
    marcas: list[str]
    parciales: dict[str, float]


def cobertura(requisitos: list[Requisito]) -> float:
    """Fracción cubierta de lo crítico y lo alto. Lo inferido cuenta como deseable. Sin requisitos claros, 0,5."""
    pesados = [(PESO_IMPORTANCIA[r.importancia], COBERTURA[r.cobertura]) for r in requisitos
               if r.importancia in PESO_IMPORTANCIA and r.origen == "dicho"]
    total = sum(p for p, _ in pesados)
    return round(sum(p * c for p, c in pesados) / total, 3) if total else 0.5


def calcular(v: Veredictos, texto_oferta: str) -> Resultado:
    falsas = []
    for nombre in ("modalidad", "elegibilidad", "idioma", "funcion", "rol_ia", "seniority", "fuente"):
        criterio = getattr(v, nombre)
        if criterio.cita and not verificar_cita(criterio.cita, texto_oferta):
            falsas.append(nombre)
            criterio.cita = None  # no cuenta como evidencia
    requisitos = [r for r in v.requisitos if verificar_cita(r.requisito, texto_oferta) or r.origen == "inferido"]
    if len(requisitos) < len(v.requisitos):
        falsas.append(f"requisitos ({len(v.requisitos) - len(requisitos)})")

    marcas, veto = [], None
    for nombre in ("modalidad", "elegibilidad", "idioma"):
        g: Compuerta = getattr(v, nombre)
        if g.veredicto == "no_pasa" and g.cita:
            veto = veto or f"{nombre}: {g.motivo}"
        elif g.veredicto in ("no_pasa", "marca"):  # sin cita comprobada, un "no pasa" solo marca
            marcas.append(f"{nombre}: {g.motivo}")
    if v.funcion.valor == "no_construye_software":
        veto = veto or f"función: {v.funcion.motivo}"

    parciales = {
        "rol_ia": VALORES["rol_ia"][v.rol_ia.valor],
        "requisitos": cobertura(requisitos),
        "funcion": VALORES["funcion"][v.funcion.valor],
        "seniority": VALORES["seniority"][v.seniority.valor],
        "fuente": VALORES["fuente"][v.fuente.valor],
    }
    nota = 0 if veto else round(100 * sum(PESOS[k] * x for k, x in parciales.items()))
    return Resultado(veredictos=v.model_copy(update={"requisitos": requisitos}), citas_falsas=falsas, nota=nota,
                     vetado=bool(veto), motivo_veto=veto, marcas=marcas, parciales=parciales)


# --- evaluar y guardar ------------------------------------------------------------


def cargar_perfil(datos: Path = almacen.DATOS) -> tuple[dict, Preferencias]:
    from job_radar.preferencias import cargar
    perfil_cv = yaml.safe_load((datos / "perfil" / "perfil_cv.yaml").read_text(encoding="utf-8"))
    return perfil_cv, cargar(datos / "perfil" / "preferencias.yaml")


def preparar(db, puesto_id: int, perfil_cv: dict, prefs: Preferencias) -> tuple[str, str]:
    """(prompt, texto de la oferta). El texto es contra el que se verifican las citas."""
    puesto = db["puesto"].get(puesto_id)
    ofertas = list(db.query("SELECT * FROM oferta WHERE puesto_id = ? ORDER BY vista_primera", [puesto_id]))
    oferta = texto_puesto(puesto, ofertas)
    return f"{texto_perfil(perfil_cv, prefs)}\n\n---\n\n# Oferta\n\n{oferta}", oferta


def evaluar(db, puesto_id: int, motor: MotorLLM, perfil_cv: dict, prefs: Preferencias) -> int:
    """Evalúa un puesto, guarda la evaluación y devuelve su id."""
    prompt, oferta = preparar(db, puesto_id, perfil_cv, prefs)
    veredictos, uso = motor.extraer(prompt, Veredictos, sistema=SISTEMA)
    return guardar(db, puesto_id, calcular(veredictos, oferta), uso, huella_perfil(perfil_cv, prefs))


def evaluar_varios(db, ids: list[int], motor: MotorLLM, perfil_cv: dict, prefs: Preferencias,
                   paralelo: int = 3, al_terminar=None) -> list[int]:
    """Las llamadas al modelo van en paralelo; las escrituras en la base, en este hilo."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    preparados = {pid: preparar(db, pid, perfil_cv, prefs) for pid in ids}
    huella, hechos = huella_perfil(perfil_cv, prefs), []
    with ThreadPoolExecutor(paralelo) as pool:
        futuros = {pool.submit(motor.extraer, prompt, Veredictos, sistema=SISTEMA): pid
                   for pid, (prompt, _) in preparados.items()}
        for f in as_completed(futuros):
            pid = futuros[f]
            try:
                veredictos, uso = f.result()
            except Exception as e:  # noqa: BLE001 — un puesto que falla no para los demás
                if al_terminar:
                    al_terminar(pid, None, e)
                continue
            ev = guardar(db, pid, calcular(veredictos, preparados[pid][1]), uso, huella)
            hechos.append(ev)
            if al_terminar:
                al_terminar(pid, ev, None)
    return hechos


def guardar(db, puesto_id: int, r: Resultado, uso: Uso, perfil: str) -> int:
    return db["evaluacion"].insert({
        "puesto_id": puesto_id, "rubrica": RUBRICA, "perfil": perfil, "motor": uso.motor, "modelo": uso.modelo,
        "resultado": r.model_dump_json(), "nota": r.nota, "vetado": int(r.vetado), "motivo_veto": r.motivo_veto,
        "marcas": json.dumps(r.marcas, ensure_ascii=False) if r.marcas else None,
        "coste_usd": uso.coste_usd, "tokens_entrada": uso.tokens_entrada, "tokens_salida": uso.tokens_salida,
        "duracion_ms": uso.duracion_ms, "creada_en": datetime.now(UTC).isoformat(timespec="seconds"),
    }).last_pk
