import { useQuery } from '@tanstack/react-query'
import { sistemaVisita } from '@/api'

/**
 * La visita anterior (servidor): «nuevo» es lo visto por primera vez después.
 * Se pide una vez por carga de la app; dentro de una sesión no cambia.
 */
export function useVisita() {
  const { data } = useQuery({
    queryKey: ['visita'],
    queryFn: async () => (await sistemaVisita({ throwOnError: true })).data,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  return data
}

export const esNuevo = (vistaPrimera: string, desde?: string | null) =>
  Boolean(desde && vistaPrimera > desde)
