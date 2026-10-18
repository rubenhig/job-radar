"""Conector LLM: un contrato, varios motores. Igual que las fuentes, el modelo
de lenguaje es una dependencia externa y tiene que poder cambiarse sin tocar
el resto del sistema.

Motores:
  - ClaudeCLI: `claude -p` con la suscripción del usuario (Pro/Max). Sin coste
    por token, pero comparte los límites de uso con el uso interactivo.
    Es el motor de la puntuación diaria (`ingesta --puntuar`).
  - (Pendiente, #44) Dentro de Docker en la Pi: `claude -p` con un token de la
    suscripción (CLAUDE_CODE_OAUTH_TOKEN) o la API de Anthropic con clave.
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class ErrorLLM(RuntimeError):
    pass


@dataclass
class Uso:
    """Lo que costó una llamada: para trazabilidad y para vigilar el gasto."""

    motor: str
    modelo: str
    coste_usd: float | None = None
    tokens_entrada: int | None = None
    tokens_salida: int | None = None
    duracion_ms: int | None = None
    limites: dict | None = None  # estado de los límites de la suscripción, si el motor lo da


class MotorLLM(Protocol):
    nombre: str

    def extraer(self, prompt: str, esquema: type[T], *, sistema: str | None = None) -> tuple[T, Uso]:
        """Devuelve una instancia de `esquema` validada, y el uso de la llamada."""
        ...


class ClaudeCLI:
    """`claude -p` en modo no interactivo con salida estructurada.

    - Sin herramientas (`--tools ""`): solo genera texto.
    - Desde una carpeta temporal vacía: no carga CLAUDE.md, hooks ni MCP del proyecto.
    - Sin ANTHROPIC_API_KEY en el entorno: si estuviera, `claude -p` la usaría y
      facturaría por token en vez de usar la suscripción.
    """

    nombre = "claude-cli"

    def __init__(self, modelo: str = "opus", timeout_s: int = 900, binario: str = "claude"):
        self.modelo = modelo
        self.timeout_s = timeout_s
        self.binario = binario

    def extraer(self, prompt: str, esquema: type[T], *, sistema: str | None = None) -> tuple[T, Uso]:
        cmd = [
            self.binario, "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(esquema.model_json_schema()),
            "--model", self.modelo,
            "--tools", "",
            "--no-session-persistence",
        ]
        if sistema:
            cmd += ["--system-prompt", sistema]
        entorno = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with tempfile.TemporaryDirectory(prefix="job-radar-llm-") as vacia:
            r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                               cwd=vacia, env=entorno, timeout=self.timeout_s)
        try:
            salida = json.loads(r.stdout)
        except json.JSONDecodeError as e:
            raise ErrorLLM(f"`claude -p` salió con {r.returncode} y sin JSON: {(r.stderr or r.stdout)[:500]}") from e
        # Según la versión, la salida es el mensaje final o la lista de mensajes de la sesión.
        mensajes = salida if isinstance(salida, list) else [salida]
        datos = next((m for m in reversed(mensajes) if m.get("type", "result") == "result"), {})
        limites = next((m.get("rate_limit_info") for m in mensajes if m.get("type") == "rate_limit_event"), None)
        if r.returncode != 0 or datos.get("is_error") or "structured_output" not in datos:
            raise ErrorLLM(f"`claude -p` falló ({r.returncode}): {str(datos.get('result') or r.stderr)[:500]}")

        uso = datos.get("usage") or {}
        return esquema.model_validate(datos["structured_output"]), Uso(
            motor=self.nombre,
            modelo=self.modelo,
            coste_usd=datos.get("total_cost_usd"),
            tokens_entrada=uso.get("input_tokens"),
            tokens_salida=uso.get("output_tokens"),
            duracion_ms=datos.get("duration_ms"),
            limites=limites,
        )
