import type { Valoracion } from '@/api'
import { Ban } from 'lucide-react'
import { colorNota } from '@/lib/puntuacion'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

/** La nota en una píldora; si está descartado, el motivo al pasar por encima. */
export function Nota({
  valoracion,
  grande = false,
}: {
  valoracion?: Valoracion | null
  grande?: boolean
}) {
  if (!valoracion)
    return <span className='text-xs text-muted-foreground'>—</span>
  const { nota, vetado, motivo_veto, resumen } = valoracion
  const pildora = (
    <span
      className={cn(
        'inline-flex items-center justify-center gap-1 rounded-full font-semibold tabular-nums',
        grande ? 'h-14 min-w-14 px-3 text-2xl' : 'h-7 min-w-9 px-2 text-sm',
        colorNota(nota, vetado)
      )}
    >
      {vetado ? <Ban className={grande ? 'size-6' : 'size-3.5'} /> : nota}
    </span>
  )
  const texto = vetado ? `Descartado: ${motivo_veto}` : resumen
  if (!texto) return pildora
  return (
    <Tooltip>
      <TooltipTrigger asChild>{pildora}</TooltipTrigger>
      <TooltipContent className='max-w-xs'>{texto}</TooltipContent>
    </Tooltip>
  )
}
