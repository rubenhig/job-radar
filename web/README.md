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
- Cada fase añade la suya: avisos, empresas, candidaturas…
