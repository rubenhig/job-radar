import json
import stat
from pathlib import Path

import pytest
from pydantic import BaseModel

from job_radar.llm import ClaudeCLI, ErrorLLM
from job_radar.perfil import verificar_cita

CV = """Ingeniero de software con +4 años de experiencia profesional: sistemas de control en tiempo real.
  * Liderazgo de las iniciativas de IA generativa del departamento; herramientas internas
    adoptadas por los equipos de Desarrollo, Testing y Calidad (decenas de usuarios)."""


def test_cita_literal():
    assert verificar_cita("sistemas de control en tiempo real", CV)


def test_cita_con_saltos_de_linea_y_mayusculas_distintas():
    assert verificar_cita("Herramientas internas adoptadas por los equipos de Desarrollo", CV)


def test_cita_inventada():
    assert not verificar_cita("Experto en Kubernetes y Terraform en producción", CV)


def test_cita_vacia():
    assert not verificar_cita("   ", CV)


# --- conector ClaudeCLI con un `claude` falso -----------------------------------

class Saludo(BaseModel):
    texto: str


def claude_falso(tmp_path: Path, respuesta: dict | list, codigo: int = 0) -> str:
    """Script que imita `claude -p`: guarda sus argumentos y entorno, y responde JSON."""
    traza = tmp_path / "traza.json"
    script = tmp_path / "claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"json.dump({{'args': sys.argv[1:], 'cwd': os.getcwd(), 'stdin': sys.stdin.read(),"
        f" 'tiene_api_key': 'ANTHROPIC_API_KEY' in os.environ}}, open({str(traza)!r}, 'w'))\n"
        f"print({json.dumps(json.dumps(respuesta))})\n"
        f"sys.exit({codigo})\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_claude_cli_valida_y_aisla(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "no-debe-llegar")
    binario = claude_falso(tmp_path, {"structured_output": {"texto": "hola"}, "total_cost_usd": 0.01})

    resultado, uso = ClaudeCLI(modelo="haiku", binario=binario).extraer("di hola", Saludo, sistema="sé breve")

    assert resultado == Saludo(texto="hola")
    assert uso.coste_usd == 0.01 and uso.modelo == "haiku"
    traza = json.loads((tmp_path / "traza.json").read_text())
    assert traza["stdin"] == "di hola"
    assert not traza["tiene_api_key"]  # usaría la API y facturaría por token
    assert "job-radar-llm-" in traza["cwd"]  # carpeta vacía, no el proyecto
    assert traza["args"][traza["args"].index("--tools") + 1] == ""
    assert "--json-schema" in traza["args"]


def test_claude_cli_error(tmp_path):
    binario = claude_falso(tmp_path, {"is_error": True, "result": "límite de uso alcanzado"}, codigo=1)
    with pytest.raises(ErrorLLM, match="límite de uso"):
        ClaudeCLI(binario=binario).extraer("x", Saludo)


def test_claude_cli_salida_en_lista_de_mensajes(tmp_path):
    """Versiones recientes devuelven todos los mensajes de la sesión; el resultado es el último."""
    mensajes = [
        {"type": "system", "subtype": "init"},
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}},
        {"type": "result", "subtype": "success", "is_error": False, "structured_output": {"texto": "hola"}},
    ]
    respuesta, uso = ClaudeCLI(binario=claude_falso(tmp_path, mensajes)).extraer("x", Saludo)
    assert respuesta.texto == "hola"
    assert uso.limites == {"status": "allowed"}
