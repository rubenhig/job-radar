"""Criba: descarta sin coste lo que no puede ser un puesto para Rubén, antes de puntuar.

Reglas deterministas y explicables, en este orden:
  1. País: un puesto presencial o híbrido en un país que no es el de las ubicaciones.
     Los remotos no se descartan por país (decisión de Rubén, 18-oct): muchos «remoto en
     Alemania» admiten toda la UE, y eso solo se sabe leyendo el anuncio. Lo decide la
     compuerta de modalidad de la puntuación.
     Sin país, no se descarta: la puntuación (compuerta de elegibilidad) lo decide leyendo el anuncio.
  2. Título excluido: contiene un término de `roles.excluir` («sales», «ai training»...).
  3. Título no técnico: no contiene ninguna palabra técnica (`roles.terminos`: principales,
     amplios y técnicos). Las búsquedas amplias en Málaga traen «Limpiador/a» o «Electricista».

Lo descartado no se borra: queda en `puesto.descarte` con su motivo y se puede consultar.
Un puesto que Rubén ha etiquetado como top nunca se descarta.
"""

import re
from collections import Counter

from job_radar.preferencias import Preferencias
from job_radar.puestos import _plano


def _patron(terminos: list[str]) -> re.Pattern | None:
    """Palabra completa si es corta («ai» no casa con «aide»); prefijo si es larga («ingenier» → «ingeniera»)."""
    alternativas = [re.escape(_plano(t).strip()) + (r"\b" if len(t.strip()) <= 3 else "") for t in terminos
                    if t.strip()]
    return re.compile(r"(?<![a-z0-9])(" + "|".join(alternativas) + ")") if alternativas else None


class Criba:
    def __init__(self, prefs: Preferencias):
        self.paises = {u.pais for u in prefs.ubicaciones} | ({prefs.remoto.desde_pais} if prefs.remoto else set())
        t = prefs.roles.terminos
        self.excluir = _patron(prefs.roles.excluir)
        self.tecnico = _patron(t.principales + t.amplios + t.tecnicos) if t.tecnicos else None

    def motivo(self, puesto: dict) -> str | None:
        if puesto.get("modalidad") != "remoto" and puesto.get("pais") and puesto["pais"] not in self.paises:
            return f"fuera de tus países ({puesto['pais']})"
        titulo = _plano(puesto["titulo"])
        if self.excluir and (m := self.excluir.search(titulo)):
            return f"título excluido: «{m.group(1)}»"
        if self.tecnico and not self.tecnico.search(titulo):
            return "título no técnico"
        return None


def aplicar(db, prefs: Preferencias) -> Counter:
    """Recalcula el descarte de todos los puestos abiertos. Devuelve cuántos quedan por motivo."""
    criba = Criba(prefs)
    cuenta, cambios = Counter(), []
    for p in db.query("""SELECT p.id, p.titulo, p.pais, p.modalidad, p.descarte, e.valor AS etiqueta FROM puesto p
                         LEFT JOIN etiqueta e ON e.puesto_id = p.id WHERE p.estado = 'abierto'"""):
        motivo = None if p["etiqueta"] == "top" else criba.motivo(p)
        cuenta[motivo.split(" (")[0].split(":")[0] if motivo else "pasan"] += 1
        if motivo != p["descarte"]:
            cambios.append((motivo, p["id"]))
    db.conn.executemany("UPDATE puesto SET descarte = ? WHERE id = ?", cambios)
    db.conn.commit()
    return cuenta
