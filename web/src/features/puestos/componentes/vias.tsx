import type { Via } from '@/api'
import { FUENTES } from '@/lib/formato'
import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'

const COLOR: Record<string, string> = {
  infojobs: 'bg-sky-500/15 text-sky-700 dark:text-sky-300',
  linkedin: 'bg-blue-600/15 text-blue-700 dark:text-blue-300',
  freehire: 'bg-violet-500/15 text-violet-700 dark:text-violet-300',
  indeed: 'bg-amber-500/15 text-amber-700 dark:text-amber-300',
}

/** Por qué fuentes llega un puesto; al pasar por encima, quién lo publica en cada una. */
export function Vias({ vias }: { vias: Via[] }) {
  const porFuente = new Map<string, string[]>()
  for (const v of vias)
    porFuente.set(v.fuente, [
      ...(porFuente.get(v.fuente) ?? []),
      v.empresa ?? '?',
    ])
  return (
    <div className='flex flex-wrap gap-1'>
      {[...porFuente].map(([fuente, empresas]) => (
        <Tooltip key={fuente}>
          <TooltipTrigger asChild>
            <Badge
              variant='outline'
              className={`border-transparent font-normal ${COLOR[fuente] ?? ''}`}
            >
              {FUENTES[fuente] ?? fuente}
              {empresas.length > 1 && (
                <span className='opacity-70'>×{empresas.length}</span>
              )}
            </Badge>
          </TooltipTrigger>
          <TooltipContent>{[...new Set(empresas)].join(' · ')}</TooltipContent>
        </Tooltip>
      ))}
    </div>
  )
}
