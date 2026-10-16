import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { Etiqueta } from '@/api'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { toast } from 'sonner'
import { puestosEtiquetarMutation } from '@/api/@tanstack/react-query.gen'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

/** Motivos frecuentes: un toque y listo. El texto libre queda para lo demás. */
const MOTIVOS = {
  top: [
    'IA / LLM',
    'Agentes',
    'Málaga',
    'Remoto viable',
    'Buena empresa',
    'Buen salario',
  ],
  no_top: [
    'Sin IA',
    'Muy senior',
    'Muy junior',
    'Lejos',
    'Inglés nativo',
    'Consultora',
    'No es mi perfil',
  ],
} as const

type Props = {
  puestoId: number
  actual?: Etiqueta | null
  onEtiquetado?: (e: Etiqueta) => void
  conMotivos?: boolean
  className?: string
}

export function BotonesEtiqueta({
  puestoId,
  actual,
  onEtiquetado,
  conMotivos = false,
  className,
}: Props) {
  const qc = useQueryClient()
  const [valor, setValor] = useState<Etiqueta['valor'] | null>(
    actual?.valor ?? null
  )
  const [motivo, setMotivo] = useState(actual?.motivo ?? '')
  const guardar = useMutation({
    ...puestosEtiquetarMutation(),
    onSuccess: (e) => {
      qc.invalidateQueries({
        predicate: (q) =>
          ['puestosListar', 'puestosFicha', 'sistemaResumen'].includes(
            (q.queryKey[0] as { _id?: string })?._id ?? ''
          ),
      })
      toast.success(
        e.valor === 'top' ? 'Marcado como top' : 'Marcado como no top'
      )
      onEtiquetado?.(e)
    },
  })

  const enviar = (v: Etiqueta['valor'], m: string) =>
    guardar.mutate({
      path: { puesto_id: puestoId },
      body: { valor: v, motivo: m || null },
    })

  const elegir = (v: Etiqueta['valor']) => {
    setValor(v)
    if (!conMotivos) enviar(v, motivo)
  }

  return (
    <div className={cn('flex flex-col gap-3', className)}>
      <div className='flex gap-2'>
        <Button
          variant={valor === 'top' ? 'default' : 'outline'}
          className={cn(
            'flex-1',
            valor === 'top' &&
              'bg-emerald-600 hover:bg-emerald-600/90 dark:bg-emerald-500'
          )}
          onClick={() => elegir('top')}
          disabled={guardar.isPending}
        >
          <ThumbsUp /> Top
        </Button>
        <Button
          variant={valor === 'no_top' ? 'default' : 'outline'}
          className={cn(
            'flex-1',
            valor === 'no_top' &&
              'bg-rose-600 hover:bg-rose-600/90 dark:bg-rose-500'
          )}
          onClick={() => elegir('no_top')}
          disabled={guardar.isPending}
        >
          <ThumbsDown /> No top
        </Button>
      </div>
      {conMotivos && valor && (
        <>
          <div className='flex flex-wrap gap-1.5'>
            {MOTIVOS[valor].map((m) => {
              const elegidos = motivo
                .split(',')
                .map((x) => x.trim())
                .filter(Boolean)
              const activo = elegidos.includes(m)
              return (
                <Button
                  key={m}
                  size='sm'
                  variant={activo ? 'secondary' : 'ghost'}
                  className='h-7 rounded-full border px-3 text-xs'
                  onClick={() =>
                    setMotivo(
                      (activo
                        ? elegidos.filter((x) => x !== m)
                        : [...elegidos, m]
                      ).join(', ')
                    )
                  }
                >
                  {m}
                </Button>
              )
            })}
          </div>
          <div className='flex gap-2'>
            <Input
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder='Motivo (opcional)'
              onKeyDown={(e) => e.key === 'Enter' && enviar(valor, motivo)}
            />
            <Button
              onClick={() => enviar(valor, motivo)}
              disabled={guardar.isPending}
            >
              Guardar
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export function InsigniaEtiqueta({ etiqueta }: { etiqueta?: Etiqueta | null }) {
  if (!etiqueta) return null
  return etiqueta.valor === 'top' ? (
    <span className='inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:text-emerald-400'>
      <ThumbsUp className='size-3' /> Top
    </span>
  ) : (
    <span className='inline-flex items-center gap-1 rounded-full bg-rose-500/15 px-2 py-0.5 text-xs font-medium text-rose-700 dark:text-rose-400'>
      <ThumbsDown className='size-3' /> No top
    </span>
  )
}
