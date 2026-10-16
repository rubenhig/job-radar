# job-radar

Radar personal de empleo **guiado por el CV**. Extrae del CV las competencias, las cruza con las preferencias de la persona (ubicación, modalidad, roles) y vigila **fuentes de calidad**:
- los ATS de las propias empresas,
- InfoJobs, Indeed y LinkedIn,
- portales de remoto.

Puntúa empresas y ofertas con Claude y avisa por Telegram solo de lo que merece la pena.

Tiene un núcleo y varias formas de usarlo, todas sobre los mismos datos:
- **El motor**, automático: corre solo y avisa.
- **La web**, la puerta principal: todo el sistema desde el móvil y el ordenador.
- **La mesa de trabajo**: los comandos de [ai-job-search](https://github.com/MadsLorentzen/ai-job-search) integrados, para preparar candidaturas y entrevistas y analizar qué skills faltan; se lanzan desde la web o desde Claude Code.
- **Telegram**, para avisar al momento.

Pensado para correr en una Raspberry Pi 5. Primer caso de uso: un AI/LLM Engineer que busca trabajo en Málaga o en remoto desde España.

> **Estado:** fase 3 (ingesta). Roadmap en el [tablero del proyecto](https://github.com/users/rubenhig/projects/1) y en [Milestones](../../milestones) (una por fase). Arquitectura en [`docs/arquitectura.md`](docs/arquitectura.md); entidades y conectores de fuentes en [`docs/modelo.md`](docs/modelo.md).

```mermaid
flowchart LR
    CV[CV + preferencias] --> P[Perfil]
    F["Fuentes<br/>ATS · portales · alertas"] --> I["Ingesta<br/>bruto → normalizar → deduplicar"]
    I --> DB[(SQLite)]
    P & DB --> M["Matching<br/>empresa + oferta<br/>(Claude con evidencias)"]
    M --> T[Telegram]
    T --> W["Web (móvil y ordenador)<br/>+ mesa de trabajo"]
    DB -.-> W
```

## Roadmap

| Fase | Estado |
|---|---|
| 0 · Exploración y estado del arte | ✅ |
| 1 · Fuentes | ✅ |
| 2 · Perfil desde el CV | ✅ |
| 3 · Ingesta | 🔄 en curso |
| 4 · Puntuación | ⬜ |
| 5 · Avisos → **MVP** | ⬜ |
| 6 · Raspberry Pi | ⬜ |
| 7 · Empresas | ⬜ |
| 8 · Mesa de trabajo (`/upskill` tras la ingesta; `/apply`, `/interview`, `/outcome` tras el MVP) | ⬜ |
| 9 · Vivienda | ⬜ |

## Principios

- **Las fuentes de calidad primero.** La ingesta es la parte más cuidada.
- **Integrar, no crear.** Cada bloque usa una herramienta open source existente que ha pasado una prueba verificable. Por ejemplo, [JobSpy](https://github.com/speedyapply/JobSpy) y [ats-scrapers](https://github.com/kalil0321/ats-scrapers).
- **Poco a poco.** Cada fase termina con algo comprobable.

## Web

```sh
uv run uvicorn job_radar.api:crear --factory --reload   # API en http://127.0.0.1:8000 (docs en /api/docs)
cd web && npm install && npm run dev                     # web en desarrollo, en http://localhost:5173
docker compose up -d --build                             # o todo junto, como irá en la Pi, en http://127.0.0.1:8000
```

Pantallas: inicio, puestos, ficha de puesto, etiquetar, fuentes y perfil. Ver [`web/`](web/README.md).

## Ingesta

```sh
uv run job-radar ingesta     # lanza las búsquedas que tocan según su frecuencia (config/fuentes.yaml)
uv run job-radar resumen     # ofertas y puestos por fuente, exclusividad y salud
uv run job-radar salud       # alertas de las fuentes
uv run datasette data/job_radar.db --metadata config/datasette.yaml   # panel: fuentes, ejecuciones, puestos, trazas
```

- Las fuentes y su conector se declaran en `config/fuentes.yaml`; las búsquedas salen de las preferencias.
- Las claves van en `.env` (`APIFY_TOKEN` para LinkedIn; `RAPIDAPI_KEY` como plan B).
- En el Mac corre a diario con launchd: ver [`deploy/launchd/`](deploy/launchd/com.rubenhig.job-radar.plist).

## Pruebas de fuentes (Fase 1)

```sh
uv run spikes/fuentes_empleo.py   # JobSpy + Tecnoempleo + ATS detectados → data/spike/*.csv
uv run spikes/analisis.py         # resumen por fuente
uv run spikes/prueba_ats.py       # ATS de empresas (Greenhouse, Workday, Teamtailor)
uv run spikes/prueba_infojobs.py  # InfoJobs con búsquedas acotadas
```

## Perfil

```sh
uv run python -m job_radar.perfil --cv ruta/al/cv.pdf   # competencias con evidencias → data/perfil/perfil_cv.yaml
uv run pytest                                           # tests
```

Las preferencias (ubicación, modalidad, roles…) se configuran copiando `config/preferencias.ejemplo.yaml` a `data/perfil/preferencias.yaml`.

Los datos personales y los resultados (`data/`, `.env`) nunca entran en el repositorio.
