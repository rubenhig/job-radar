import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { Guardado } from '@/api'
import { Bookmark, BookmarkCheck, Star } from 'lucide-react'
import { toast } from 'sonner'
import { listaMisEtiquetasOptions } from '@/api/@tanstack/react-query.gen'
import { haceCuanto } from '@/lib/formato'
import { COLOR_ESTADO, ESTADOS, type EstadoLista } from '@/lib/lista'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { ListaEditable } from '@/components/lista-editable'
import { useGuardar } from '../usar-guardado'

export function Estrellas({
  valor,
  onChange,
  tamano = 'size-4',
}: {
  valor: number
  onChange?: (v: number) => void
  tamano?: string
}) {
  return (
    <div className='flex items-center' aria-label={`Prioridad ${valor} de 3`}>
      {[1, 2, 3].map((n) => (
        <button
          key={n}
          type='button'
          disabled={!onChange}
          // otra vez la misma estrella: la quita
          onClick={() => onChange?.(valor === n ? n - 1 : n)}
          className={cn('p-0.5', onChange && 'hover:scale-110')}
          aria-label={`${n} estrella${n > 1 ? 's' : ''}`}
        >
          <Star
            className={cn(
              tamano,
              n <= valor
                ? 'fill-amber-400 text-amber-400'
                : 'text-muted-foreground/40'
            )}
          />
        </button>
      ))}
    </div>
  )
}

export function InsigniaGuardado({ guardado }: { guardado?: Guardado | null }) {
  if (!guardado) return null
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
        COLOR_ESTADO[guardado.estado]
      )}
    >
      <BookmarkCheck className='size-3' /> {ESTADOS[guardado.estado]}
    </span>
  )
}

export function SelectorEstado({
  valor,
  onChange,
  className,
}: {
  valor: EstadoLista
  onChange: (v: EstadoLista) => void
  className?: string
}) {
  return (
    <Select value={valor} onValueChange={(v) => onChange(v as EstadoLista)}>
      <SelectTrigger aria-label='Estado' className={cn('h-9', className)}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {Object.entries(ESTADOS).map(([k, v]) => (
          <SelectItem key={k} value={k}>
            {v}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/** En la ficha: guardar el puesto y llevar su seguimiento. */
export function TarjetaGuardado({
  puestoId,
  guardado,
}: {
  puestoId: number
  guardado?: Guardado | null
}) {
  const { guardar, quitar, ocupado } = useGuardar(puestoId)
  const { data: sugeridas } = useQuery(listaMisEtiquetasOptions())
  const [notas, setNotas] = useState(guardado?.notas ?? '')

  if (!guardado) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Mi lista</CardTitle>
          <CardDescription>
            Guárdalo para seguirlo: estado, prioridad, notas y tus etiquetas.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            className='w-full'
            disabled={ocupado}
            onClick={() => {
              guardar({})
              toast.success('Guardado en Mi lista')
            }}
          >
            <Bookmark /> Guardar en Mi lista
          </Button>
        </CardContent>
      </Card>
    )
  }

  const etiquetas = guardado.etiquetas ?? []
  const historial = guardado.historial ?? []
  const libres = Object.keys(sugeridas ?? {}).filter(
    (t) => !etiquetas.includes(t)
  )
  return (
    <Card>
      <CardHeader>
        <CardTitle className='flex items-center gap-2'>
          <BookmarkCheck className='size-4' /> Mi lista
        </CardTitle>
        <CardDescription>
          Guardado {haceCuanto(guardado.creado_en)}
          {historial.length > 1 &&
            ` · ${ESTADOS[guardado.estado].toLowerCase()} ${haceCuanto(historial[historial.length - 1].en)}`}
        </CardDescription>
      </CardHeader>
      <CardContent className='flex flex-col gap-4'>
        <div className='flex items-center justify-between gap-2'>
          <SelectorEstado
            valor={guardado.estado}
            onChange={(estado) => guardar({ estado })}
            className='w-44'
          />
          <Estrellas
            valor={guardado.prioridad ?? 0}
            onChange={(prioridad) => guardar({ prioridad })}
          />
        </div>
        <div className='flex flex-col gap-1.5'>
          <span className='text-sm font-medium'>Mis etiquetas</span>
          <ListaEditable
            valores={etiquetas}
            onChange={(etiquetas) => guardar({ etiquetas })}
            placeholder='Añadir (Enter)'
          />
          {libres.length > 0 && (
            <div className='flex flex-wrap gap-1'>
              {libres.slice(0, 8).map((t) => (
                <button
                  key={t}
                  type='button'
                  className='rounded-full border px-2 py-0.5 text-xs text-muted-foreground hover:bg-accent'
                  onClick={() => guardar({ etiquetas: [...etiquetas, t] })}
                >
                  + {t}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className='flex flex-col gap-1.5'>
          <span className='text-sm font-medium'>Notas</span>
          <Textarea
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder='Contacto, a quién escribí, qué preguntar…'
          />
          {notas !== (guardado.notas ?? '') && (
            <Button
              size='sm'
              className='w-fit'
              disabled={ocupado}
              onClick={() => guardar({ notas })}
            >
              Guardar notas
            </Button>
          )}
        </div>
        <Button
          variant='ghost'
          size='sm'
          className='w-fit text-muted-foreground'
          disabled={ocupado}
          onClick={quitar}
        >
          Quitar de Mi lista
        </Button>
      </CardContent>
    </Card>
  )
}
