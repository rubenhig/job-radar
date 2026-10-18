import type { Guardado } from '@/api'

export type EstadoLista = Guardado['estado']

/** Los pasos de Mi lista, en orden: así se pintan las columnas del tablero. */
export const ESTADOS: Record<EstadoLista, string> = {
  interesante: 'Interesante',
  voy_a_aplicar: 'Voy a aplicar',
  aplicado: 'Aplicado',
  entrevista: 'Entrevista',
  oferta: 'Oferta',
  descartado: 'Descartado',
}

export const COLOR_ESTADO: Record<EstadoLista, string> = {
  interesante: 'bg-sky-500/15 text-sky-700 dark:text-sky-400',
  voy_a_aplicar: 'bg-violet-500/15 text-violet-700 dark:text-violet-400',
  aplicado: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  entrevista: 'bg-orange-500/15 text-orange-700 dark:text-orange-400',
  oferta: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  descartado: 'bg-muted text-muted-foreground',
}
