"""Imprime el esquema OpenAPI de la API, del que la web genera su cliente tipado.

    uv run python -m job_radar.api.openapi > web/openapi.json   # o, desde web/: npm run gen:api
"""

import json
import tempfile
from pathlib import Path

from job_radar.api import crear

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:  # sin tocar la base de datos real
        app = crear(Path(tmp) / "esquema.db", Path(tmp), web=Path(tmp) / "sin-web")
        print(json.dumps(app.openapi(), ensure_ascii=False, indent=1))
