import { StrictMode } from 'react'
import ReactDOM from 'react-dom/client'
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { toast } from 'sonner'
import { client } from './api/client.gen'
import { DirectionProvider } from './context/direction-provider'
import { FontProvider } from './context/font-provider'
import { ThemeProvider } from './context/theme-provider'
import { routeTree } from './routeTree.gen'
import './styles/index.css'

// La API está en el mismo origen (/api): FastAPI sirve la app; en desarrollo, el proxy de Vite.
client.setConfig({ baseUrl: '', throwOnError: true })

function mensaje(error: unknown) {
  if (error && typeof error === 'object' && 'detail' in error) {
    const d = (error as { detail: unknown }).detail
    return typeof d === 'string' ? d : 'Datos no válidos'
  }
  return error instanceof Error ? error.message : 'Error de la API'
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: import.meta.env.PROD ? 2 : false,
      refetchOnWindowFocus: import.meta.env.PROD,
      staleTime: 30 * 1000,
    },
  },
  queryCache: new QueryCache({ onError: (e) => toast.error(mensaje(e)) }),
  mutationCache: new MutationCache({ onError: (e) => toast.error(mensaje(e)) }),
})

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 0,
  scrollRestoration: true,
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

const rootElement = document.getElementById('root')!
if (!rootElement.innerHTML) {
  ReactDOM.createRoot(rootElement).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          <FontProvider>
            <DirectionProvider>
              <RouterProvider router={router} />
            </DirectionProvider>
          </FontProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </StrictMode>
  )
}
