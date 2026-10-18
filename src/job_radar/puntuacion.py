"""Puntuación: ¿encaja este puesto con el perfil?

Claude no da la nota: da veredictos por criterio, cada uno con valores cerrados
y una cita literal de la oferta. Python comprueba que cada cita existe en la
oferta y calcula la nota con pesos fijos. Lo que no se puede comprobar se
marca, no se cree: una compuerta que no pasa sin cita verificada no veta.

Rúbrica v2 (18-oct-2026), sobre las de career-ops y ai-job-search (ver docs/repositorios.md):
  - Compuertas (pasa / no pasa / marca): modalidad, elegibilidad, idioma.
    Cualquier "no pasa" con evidencia anula la nota; "marca" solo avisa.
  - Función: si el puesto no consiste en construir software (entrenar modelos
    como profesor o lingüista, consultoría de gobierno, ventas), se anula.
  - Dimensiones: encaje del rol de IA (40 %), cobertura de requisitos (30 %),
    función técnica (10 %), seniority (10 %) y fuente (10 %).
  - Requisitos en dos pasadas: primero qué pide la oferta y cuánto importa;
    después, con qué competencia del perfil se cubre. Lo inferido nunca es crítico.
  - Salario: si la oferta da cifras en el texto, el modelo las extrae con su cita. Cuenta en
    Python frente al salario actual y el objetivo (ver «el salario, en Python»).

Cambios de la v2 tras medir contra las etiquetas de Rubén: el ML clásico y la visión por
computador tienen categoría propia (no son «sin IA»); un título que nombra IA es como mínimo
«software con IA»; una compuerta solo dice «no pasa» con certeza; el salario del texto.
"""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from job_radar import almacen
from job_radar.llm import MotorLLM, Uso
from job_radar.perfil import verificar_cita
from job_radar.preferencias import Preferencias

RUBRICA = "rubrica/2"
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
    valor: Literal["ia_principal", "software_con_ia", "ml_clasico", "software_sin_ia", "ninguno"] = Field(
        description="ia_principal: el puesto ES de IA/LLM (AI/LLM/GenAI Engineer, agentes en producción, arquitecto o "
                    "tech lead de IA, MLOps/plataforma LLM); software_con_ia: ingeniería de software donde la IA aparece "
                    "en el título o en las tareas (un título que nombra AI/IA/LLM/ML es como mínimo esto); ml_clasico: "
                    "machine learning, visión por computador o ciencia de datos con modelos, sin LLM; software_sin_ia: "
                    "ingeniería de software sin IA en el título ni en las tareas; ninguno. No fuerces un encaje que no hay")
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


class SalarioDicho(BaseModel):
    minimo: float | None = Field(None, description="Cifra tal cual (35000, no 35)")
    maximo: float | None = None
    moneda: str | None = Field(None, description="ISO 4217: EUR, USD, GBP")
    periodo: Literal["ano", "mes", "dia", "hora"] | None = None
    cita: str = Field(description="La frase LITERAL de la oferta con las cifras")


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
    salario: SalarioDicho | None = Field(None, description="Solo si el texto de la oferta da cifras de salario; "
                                                           "si no, null. No lo estimes")


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
- Compuertas: 'no_pasa' solo si la oferta deja claro que el candidato NO puede. Si dudas o es
  probable que pueda, 'pasa' o 'sin_datos'. El motivo tiene que decir lo mismo que el veredicto.
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


def huella_texto(texto_oferta: str) -> str:
    return hashlib.sha256(texto_oferta.encode()).hexdigest()[:12]


def huella_perfil(perfil_cv: dict, prefs: Preferencias) -> str:
    """Cambia solo si cambia lo que ve el modelo: tocar la criba o los términos de búsqueda no obliga a repuntuar."""
    base = json.dumps([perfil_cv["meta"].get("cv_sha256"), texto_perfil(perfil_cv, prefs)])
    return hashlib.sha256(base.encode()).hexdigest()[:12]


# --- la nota, en Python ----------------------------------------------------------

PESOS = {"rol_ia": 0.40, "requisitos": 0.30, "funcion": 0.10, "seniority": 0.10, "fuente": 0.10}
VALORES = {
    "funcion": {"ingenieria": 1.0, "tecnica_adyacente": 0.5, "no_construye_software": 0.0},
    "rol_ia": {"ia_principal": 1.0, "software_con_ia": 0.67, "ml_clasico": 0.67, "software_sin_ia": 0.33,
               "ninguno": 0.0},
    "seniority": {"encaja": 1.0, "reto": 0.6, "por_debajo": 0.6, "muy_por_encima": 0.0},
    "fuente": {"directa": 1.0, "intermediario": 0.6, "dudosa": 0.2},
}
PESO_IMPORTANCIA = {"critico": 2.0, "alto": 1.0}
COBERTURA = {"fuerte": 1.0, "parcial": 0.5, "falta": 0.0}


class AjusteSalario(BaseModel):
    """Lo que el salario de la oferta suma o limita, frente al actual y el objetivo de Rubén."""

    anual_eur: int                    # lo máximo que ofrece, en bruto anual y euros
    estimado: bool                    # el salario lo infirió un modelo de la fuente, no lo dice la oferta
    puntos: float                     # se suman a la nota
    techo: int | None = None          # la nota no pasa de aquí (rebaja de sueldo)
    marca: str


class Resultado(BaseModel):
    """La evaluación ya calculada: veredictos, citas comprobadas, nota y avisos."""

    veredictos: Veredictos
    citas_falsas: list[str]           # criterios cuya cita no aparece en la oferta
    nota: int
    vetado: bool
    motivo_veto: str | None
    marcas: list[str]
    parciales: dict[str, float]
    salario: AjusteSalario | None = None


# --- el salario, en Python: no lo ve el modelo, así que se recalcula gratis ----------

# Aproximado (oct-2026): basta para comparar con el salario deseado. AED, SAR y QAR van ligados al dólar.
CAMBIO_EUR = {"EUR": 1.0, "USD": 0.92, "GBP": 1.17, "CHF": 1.06, "PLN": 0.235, "AED": 0.242, "SAR": 0.237,
              "QAR": 0.243}
POR_HORAS = ("hora", "dia")  # tarifas de freelance o de plataforma: no son un sueldo anual comparable
AL_ANO = {"ano": 1, "mes": 12, "semana": 46, "dia": 220, "hora": 1760}
BONUS_SALARIO = 10      # puntos al llegar al objetivo
TECHO_REBAJA = 45       # una rebaja no llega al corte de top (50)
TECHO_SIN_IA = 45       # software sin IA: se ve, pero no es top (Rubén, 18-oct)
CASTIGO_ESTIMADO = 15   # rebaja según un salario estimado: resta, pero no pone techo


def salario_anual(s: dict | None) -> int | None:
    """El máximo de la horquilla en bruto anual y euros; None si falta o no es creíble."""
    if not s:
        return None
    tope = s.get("salario_max") or s.get("salario_min")
    cambio = CAMBIO_EUR.get((s.get("salario_moneda") or "EUR").upper())
    periodo = s.get("salario_periodo") or "ano"
    if periodo == "mes" and tope and tope >= 10_000:  # JobSpy lee «24.600 €» anuales como mensuales
        periodo = "ano"
    al_ano = AL_ANO.get(periodo)
    if not (tope and cambio and al_ano):
        return None
    anual = round(tope * cambio * al_ano)
    return anual if 8_000 <= anual <= 1_000_000 else None


def ajuste_salario(s: dict | None, estimado: bool, deseado) -> AjusteSalario | None:
    anual = salario_anual(s)
    if anual is None or not deseado.actual:
        return None
    if s.get("salario_periodo") in POR_HORAS:  # «$20-100/h» × 1760 no es un sueldo: se avisa, no puntúa
        tope = s.get("salario_max") or s.get("salario_min")
        unidad = "h" if s["salario_periodo"] == "hora" else "día"
        return AjusteSalario(anual_eur=anual, estimado=estimado, puntos=0,
                             marca=f"salario: tarifa de {tope:g} {s.get('salario_moneda') or ''}/{unidad}".replace(" /", "/"))
    objetivo = deseado.objetivo or deseado.actual
    k = f"{anual / 1000:.0f}k" + (" estimado" if estimado else "")
    if anual < deseado.actual:
        if estimado:
            return AjusteSalario(anual_eur=anual, estimado=True, puntos=-CASTIGO_ESTIMADO,
                                 marca=f"salario: {k}, por debajo de tu actual")
        return AjusteSalario(anual_eur=anual, estimado=False, puntos=0, techo=TECHO_REBAJA,
                             marca=f"salario: {k}, por debajo de tu actual (rebaja)")
    tramo = 1.0 if anual >= objetivo else (anual - deseado.actual) / max(1, objetivo - deseado.actual)
    return AjusteSalario(anual_eur=anual, estimado=estimado, puntos=round(BONUS_SALARIO * tramo, 1),
                         marca=f"salario: {k}" + (", llega a tu objetivo" if anual >= objetivo else ""))


def nota_final(parciales: dict[str, float], vetado: bool, salario: AjusteSalario | None, rol_ia: str) -> int:
    """La suma ponderada, más el salario; los techos (rebaja, sin IA) se aplican al final."""
    if vetado:
        return 0
    nota = 100 * sum(PESOS[k] * parciales[k] for k in PESOS) + (salario.puntos if salario else 0)
    techos = [100]
    if salario and salario.techo is not None:
        techos.append(salario.techo)
    if rol_ia in ("software_sin_ia", "ninguno"):
        techos.append(TECHO_SIN_IA)
    return round(max(0.0, min(nota, *techos)))


def _cifra_en_texto(valor: float, texto: str) -> bool:
    """¿Dice el anuncio esta cifra? 35000 → «35.000», «35,000», «35 000», «35000» o «35k»."""
    n = int(valor)
    formas = {str(n), f"{n:,}", f"{n:,}".replace(",", "."), f"{n:,}".replace(",", " ")}
    if n % 1000 == 0:
        formas |= {f"{n // 1000}k", f"{n // 1000} k"}
    t = texto.lower()
    return any(re.search(rf"(?<![\d.,]){re.escape(f)}(?![\d])", t) for f in formas)


def salario_de(db, puesto_id: int) -> tuple[dict | None, str | None]:
    """El salario fusionado del puesto y de dónde sale: «fuente» (dato de la fuente), «texto» (lo infirió
    el modelo de la fuente y la cifra está en el anuncio) o «estimado» (inferido y no está en el anuncio)."""
    fusion = json.loads(db["puesto"].get(puesto_id)["fusion"] or "{}").get("salario")
    if not fusion:
        return None, None
    oferta = db.execute("SELECT derivados, descripcion FROM oferta WHERE id = ?", [fusion.get("oferta_id")]).fetchone()
    derivados = json.loads(oferta[0]) if oferta and oferta[0] else []
    if not any(c.startswith("salario") for c in derivados):
        return fusion["valor"], "fuente"
    tope = fusion["valor"].get("salario_max") or fusion["valor"].get("salario_min")
    en_texto = tope and oferta and oferta[1] and _cifra_en_texto(tope, oferta[1])
    return fusion["valor"], "texto" if en_texto else "estimado"


def cobertura(requisitos: list[Requisito]) -> float:
    """Fracción cubierta de lo crítico y lo alto. Lo inferido cuenta como deseable. Sin requisitos claros, 0,5."""
    pesados = [(PESO_IMPORTANCIA[r.importancia], COBERTURA[r.cobertura]) for r in requisitos
               if r.importancia in PESO_IMPORTANCIA and r.origen == "dicho"]
    total = sum(p for p, _ in pesados)
    return round(sum(p * c for p, c in pesados) / total, 3) if total else 0.5


def elegir_salario(fuente: tuple[dict | None, str | None], v: Veredictos) -> tuple[dict | None, bool]:
    """(salario, estimado). Primero el dato real de la fuente; después el que el modelo citó del texto
    (lee el de la ubicación del puesto: un anuncio puede dar la horquilla de Londres y la de Madrid); y si
    no, el inferido por la fuente, dicho si la cifra está en el anuncio y estimado si no."""
    datos, origen = fuente
    if datos and origen == "fuente":
        return datos, False
    if v.salario and (v.salario.maximo or v.salario.minimo):
        return {"salario_min": v.salario.minimo, "salario_max": v.salario.maximo,
                "salario_moneda": v.salario.moneda, "salario_periodo": v.salario.periodo}, False
    return (datos, origen == "estimado") if datos else (None, False)


NUMEROS = re.compile(r"\d+")
# Un veto exige certeza (SISTEMA): si el motivo expresa duda, el «no pasa» solo marca.
DUDA = re.compile(r"no indica|no consta|no aclara|no queda claro|no est[aá] (claro|claramente)|no especifica|"
                  r"no dice|sin indicar|indicios|probablemente|posiblemente|podr[ií]a|parece|garantizad", re.I)


def cita_valida(cita: str, texto: str) -> bool:
    """Como `verificar_cita`, pero sin tolerar cifras cambiadas: «55.000» no vale si el anuncio dice «35.000»."""
    return verificar_cita(cita, texto) and set(NUMEROS.findall(cita)) <= set(NUMEROS.findall(texto))


def calcular(v: Veredictos, texto_oferta: str, fuente_salario: tuple[dict | None, str | None] = (None, None),
             deseado=None) -> Resultado:
    falsas = []
    for nombre in ("modalidad", "elegibilidad", "idioma", "funcion", "rol_ia", "seniority", "fuente"):
        criterio = getattr(v, nombre)
        if criterio.cita and not cita_valida(criterio.cita, texto_oferta):
            falsas.append(nombre)
            criterio.cita = None  # no cuenta como evidencia
    if v.salario and not (cita_valida(v.salario.cita, texto_oferta) and all(
            _cifra_en_texto(x, v.salario.cita) for x in (v.salario.minimo, v.salario.maximo) if x)):
        falsas.append("salario")  # la cita no está en el anuncio, o sus cifras no son las que dice el modelo
        v.salario = None
    requisitos = [r for r in v.requisitos if cita_valida(r.requisito, texto_oferta) or r.origen == "inferido"]
    if len(requisitos) < len(v.requisitos):
        falsas.append(f"requisitos ({len(v.requisitos) - len(requisitos)})")

    marcas, veto = [], None
    for nombre in ("modalidad", "elegibilidad", "idioma"):
        g: Compuerta = getattr(v, nombre)
        if g.veredicto == "no_pasa" and g.cita and not DUDA.search(g.motivo):
            veto = veto or f"{nombre}: {g.motivo}"
        elif g.veredicto in ("no_pasa", "marca"):  # sin cita comprobada, o con duda, un "no pasa" solo marca
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
    salario = ajuste_salario(*elegir_salario(fuente_salario, v), deseado) if deseado else None
    if salario and not veto:
        marcas.append(salario.marca)
    return Resultado(veredictos=v.model_copy(update={"requisitos": requisitos}), citas_falsas=falsas,
                     nota=nota_final(parciales, bool(veto), salario, v.rol_ia.valor), vetado=bool(veto), motivo_veto=veto,
                     marcas=marcas, parciales=parciales, salario=salario)


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
    r = calcular(veredictos, oferta, salario_de(db, puesto_id), prefs.salario)
    return guardar(db, puesto_id, r, uso, huella_perfil(perfil_cv, prefs), oferta)


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
            try:  # un puesto que falla (el modelo, o guardar con la base ocupada) no para los demás
                veredictos, uso = f.result()
                r = calcular(veredictos, preparados[pid][1], salario_de(db, pid), prefs.salario)
                ev = guardar(db, pid, r, uso, huella, preparados[pid][1])
            except Exception as e:  # noqa: BLE001
                if al_terminar:
                    al_terminar(pid, None, e)
                continue
            hechos.append(ev)
            if al_terminar:
                al_terminar(pid, ev, None)
    return hechos


def guardar(db, puesto_id: int, r: Resultado, uso: Uso, perfil: str, texto_oferta: str | None = None) -> int:
    return db["evaluacion"].insert({
        "puesto_id": puesto_id, "rubrica": RUBRICA, "perfil": perfil, "motor": uso.motor, "modelo": uso.modelo,
        "texto_sha": huella_texto(texto_oferta) if texto_oferta is not None else None,
        "resultado": r.model_dump_json(), "nota": r.nota, "vetado": int(r.vetado), "motivo_veto": r.motivo_veto,
        "marcas": json.dumps(r.marcas, ensure_ascii=False) if r.marcas else None,
        "coste_usd": uso.coste_usd, "tokens_entrada": uso.tokens_entrada, "tokens_salida": uso.tokens_salida,
        "duracion_ms": uso.duracion_ms, "creada_en": datetime.now(UTC).isoformat(timespec="seconds"),
    }).last_pk


def recalcular(db, prefs: Preferencias) -> int:
    """Rehace toda la parte en Python de la última evaluación de cada puesto (verificación de citas, vetos,
    salario, techos) con los veredictos guardados y el texto actual, sin llamar al modelo: cambiar las
    reglas, el salario deseado o que una oferta publique su salario no cuesta nada. Devuelve cuántas cambian."""
    cambios = 0
    for ev in db.query("""SELECT * FROM evaluacion WHERE id IN (SELECT MAX(id) FROM evaluacion
                          WHERE rubrica = ? GROUP BY puesto_id)""", [RUBRICA]):
        r = Resultado.model_validate_json(ev["resultado"])
        nueva = calcular(r.veredictos.model_copy(deep=True), _texto(db, ev["puesto_id"]),
                         salario_de(db, ev["puesto_id"]), prefs.salario)
        nueva.citas_falsas = list(dict.fromkeys(r.citas_falsas + nueva.citas_falsas))
        if nueva != r:
            db["evaluacion"].update(ev["id"], {
                "resultado": nueva.model_dump_json(), "nota": nueva.nota, "vetado": int(nueva.vetado),
                "motivo_veto": nueva.motivo_veto,
                "marcas": json.dumps(nueva.marcas, ensure_ascii=False) if nueva.marcas else None})
            cambios += 1
    db.conn.commit()
    return cambios


def pendientes(db, perfil_cv: dict, prefs: Preferencias, etiquetados: bool = False) -> list[int]:
    """Los puestos que hay que (re)puntuar, los más nuevos primero: sin evaluación con esta rúbrica y este
    perfil, o con una evaluación de un texto que ya no es el suyo (otra descripción tras reagrupar).
    Lo que la criba descarta no se paga, salvo que se pidan los etiquetados (para medir)."""
    huella = huella_perfil(perfil_cv, prefs)
    filtro = "p.id IN (SELECT puesto_id FROM etiqueta)" if etiquetados else "p.descarte IS NULL"
    filas = db.execute(f"""
        SELECT p.id, ev.texto_sha FROM puesto p
        LEFT JOIN evaluacion ev ON ev.id = (SELECT MAX(x.id) FROM evaluacion x WHERE x.puesto_id = p.id
                                            AND x.rubrica = ? AND x.perfil = ?)
        WHERE p.estado = 'abierto' AND {filtro}
        ORDER BY (SELECT MIN(o.vista_primera) FROM oferta o WHERE o.puesto_id = p.id) DESC""",
                       [RUBRICA, huella]).fetchall()
    salida = []
    for pid, sha in filas:
        if sha is None and db.execute("SELECT 1 FROM evaluacion WHERE puesto_id = ? AND rubrica = ? AND perfil = ?",
                                      [pid, RUBRICA, huella]).fetchone():
            continue  # evaluaciones de antes de guardar la huella del texto: se dan por buenas
        if sha is None or sha != huella_texto(_texto(db, pid)):
            salida.append(pid)
    return salida


def _texto(db, puesto_id: int) -> str:
    ofertas = list(db.query("SELECT * FROM oferta WHERE puesto_id = ? ORDER BY vista_primera", [puesto_id]))
    return texto_puesto(db["puesto"].get(puesto_id), ofertas)
