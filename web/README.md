# job-radar · web

La puerta principal del sistema, para el móvil y el ordenador. Usa React, Vite, shadcn/ui y TanStack Router/Query. Parte de la plantilla [shadcn-admin](https://github.com/satnaing/shadcn-admin) (MIT, © Sat Naing, ver `LICENSE`), sin su autenticación ni sus pantallas de ejemplo. El stack se decidió en la #29 y está documentado en `docs/repositorios.md`.

```sh
npm install
npm run dev        # http://localhost:5173; /api va a la API (uv run uvicorn job_radar.api:crear --factory)
npm run gen:api    # regenera el cliente tipado (src/api) desde el OpenAPI de FastAPI
npm run build      # dist/, que sirve FastAPI en el mismo origen
```

- `src/api/` se genera con `@hey-api/openapi-ts`; no se edita a mano.
- Las pantallas están en `src/features/`, y las rutas, en `src/routes/`.
- Cada fase añade la suya: empresas, candidaturas… (los avisos están aparcados).

| Pantalla | Qué hace |
|---|---|
| Inicio | «Desde tu última visita» (la visita se apunta en el servidor con `POST /api/visita`: vale igual en el móvil y en el ordenador), «Para ti» (nota 50 o más) y «¿Piensa como tú?» (acuerdo con tus etiquetas) |
| Puestos | Lista ordenada por nota, con filtros en la URL, «Solo nuevos» y los descartados por la criba aparte |
| Ficha de puesto | Ofertas y procedencia de cada campo; la nota explicada, con las citas resaltadas en la descripción |
| Etiquetar | Top / no top con motivo; sin ver la nota, a propósito |
| Puntuación | Acuerdo de la nota con las etiquetas, caso a caso |
| Fuentes | Salud, ejecuciones, cuota y gasto de cada fuente |
| Perfil | Competencias del CV y preferencias: ubicaciones, mercados en remoto, roles, términos de la criba, inglés y salario |

Es una PWA instalable: al desplegar una versión nueva, se recarga sola.
