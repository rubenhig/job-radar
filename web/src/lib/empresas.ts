import type { EmpresaResumen } from '@/api'

export type EstadoEmpresa = NonNullable<EmpresaResumen['estado']>

export const ESTADOS_EMPRESA: Record<EstadoEmpresa, string> = {
  seguida: 'Seguida',
  pendiente: 'Pendiente',
  descartada: 'Descartada',
}

export const COLOR_EMPRESA: Record<EstadoEmpresa, string> = {
  seguida: 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  pendiente: 'bg-amber-500/15 text-amber-700 dark:text-amber-400',
  descartada: 'bg-muted text-muted-foreground line-through',
}
