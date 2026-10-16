import { defineConfig } from '@hey-api/openapi-ts'

// Cliente tipado generado desde el OpenAPI de FastAPI: `npm run gen:api`.
// openapi-ts es 0.x y rompe en las versiones menores: va fijada sin ^ en package.json.
export default defineConfig({
  input: './openapi.json',
  output: 'src/api',
  plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk', '@tanstack/react-query'],
})
