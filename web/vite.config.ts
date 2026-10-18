import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
    // Instalable en el móvil. La API nunca se sirve desde la caché ni cae en index.html.
    VitePWA({
      // Se registra desde main.tsx (registerSW): con autoUpdate, la página se recarga al activarse una versión nueva.
      registerType: 'autoUpdate',
      injectRegister: false,
      includeAssets: ['images/favicon.svg'],
      manifest: {
        name: 'job-radar',
        short_name: 'job-radar',
        description: 'Radar personal de empleo',
        lang: 'es',
        theme_color: '#0a0a0a',
        background_color: '#0a0a0a',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
        // urlPattern recibe la URL completa: se compara la ruta, no el texto («http://…/api/» no empieza por «/api/»).
        runtimeCaching: [
          { urlPattern: ({ url }) => url.pathname.startsWith('/api/'), handler: 'NetworkOnly' },
        ],
      },
    }),
  ],
  server: {
    // En desarrollo, la API de FastAPI (uv run uvicorn job_radar.api:crear --factory).
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
