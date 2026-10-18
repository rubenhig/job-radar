import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { sistemaVisita } from '@/api'

/**
 * La visita anterior (servidor): «nuevo» es lo visto por primera vez después.
 * Se pide una vez por carga de la app; dentro de una sesión no cambia.
 */
const SESION_MS = 30 * 60 * 1000 // como SESION_MIN en la API

export function useVisita() {
  const qc = useQueryClient()
  // La PWA instalada se reanuda sin recargar: al volver tras una sesión larga, es otra visita.
  useEffect(() => {
    const alVolver = () => {
      const estado = qc.getQueryState(['visita'])
      if (
        document.visibilityState === 'visible' &&
        estado &&
        Date.now() - estado.dataUpdatedAt > SESION_MS
      )
        qc.invalidateQueries({ queryKey: ['visita'] })
    }
    document.addEventListener('visibilitychange', alVolver)
    return () => document.removeEventListener('visibilitychange', alVolver)
  }, [qc])
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
