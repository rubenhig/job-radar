import type { Criterio, Evaluacion } from '@/api'
import {
  AlertTriangle,
  Ban,
  Check,
  CircleHelp,
  Minus,
  Quote,
  Sparkles,
  X,
} from 'lucide-react'
import { haceCuanto } from '@/lib/formato'
import { NOMBRES_CRITERIO, VALORES } from '@/lib/puntuacion'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Nota } from './nota'

const PESOS: Record<string, number> = {
  rol_ia: 40,
  requisitos: 30,
  funcion: 10,
  seniority: 10,
  fuente: 10,
}

/** Por qué un puesto es top o no: compuertas, dimensiones con sus citas y requisitos. */
export function TarjetaPuntuacion({
  evaluacion: e,
}: {
  evaluacion?: Evaluacion | null
}) {
  if (!e) {
    return (
      <Card className='border-dashed'>
        <CardHeader>
          <CardTitle className='flex items-center gap-2'>
            <Sparkles className='size-4' /> Puntuación
          </CardTitle>
          <CardDescription>
            Aún sin puntuar: se puntúa en la próxima ingesta.
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }
  return (
    <Card>
      <CardHeader className='flex flex-row items-start gap-4'>
        <Nota valoracion={e} grande />
        <div className='flex flex-col gap-1'>
          <CardTitle>
            {e.vetado ? 'Descartado' : 'Encaje con tu perfil'}
          </CardTitle>
          <CardDescription>
            {e.vetado ? e.motivo_veto : e.resumen}
          </CardDescription>
          <span className='text-xs text-muted-foreground'>
            {e.rubrica} · {e.modelo} · {haceCuanto(e.creada_en)}
          </span>
        </div>
      </CardHeader>
      <CardContent className='flex flex-col gap-5'>
        {((e.marcas ?? []).length > 0 || e.citas_falsas.length > 0) && (
          <div className='flex flex-col gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm'>
            {(e.marcas ?? []).map((m) => (
              <div key={m} className='flex gap-2'>
                <AlertTriangle className='size-4 shrink-0 text-amber-600' />
                {m}
              </div>
            ))}
            {e.citas_falsas.length > 0 && (
              <div className='flex gap-2 text-muted-foreground'>
                <CircleHelp className='size-4 shrink-0' />
                Citas que no aparecen en la oferta, descartadas:{' '}
                {e.citas_falsas.join(', ')}
              </div>
            )}
          </div>
        )}

        <Seccion titulo='Compuertas'>
          <div className='grid gap-2 sm:grid-cols-3'>
            {Object.entries(e.compuertas).map(([k, c]) => (
              <Compuerta key={k} nombre={k} criterio={c} />
            ))}
          </div>
        </Seccion>

        <Seccion titulo='Criterios'>
          <div className='flex flex-col divide-y'>
            {Object.entries(e.dimensiones).map(([k, c]) => (
              <Dimension
                key={k}
                nombre={k}
                criterio={c}
                parcial={e.parciales[k]}
              />
            ))}
            <div className='flex items-center justify-between gap-2 py-2 text-sm'>
              <span className='font-medium'>{NOMBRES_CRITERIO.requisitos}</span>
              <Barra valor={e.parciales.requisitos} peso={PESOS.requisitos} />
            </div>
          </div>
        </Seccion>

        <Seccion titulo={`Requisitos (${e.requisitos.length})`}>
          <ul className='flex flex-col gap-2 text-sm'>
            {e.requisitos.map((q) => (
              <li key={q.requisito} className='flex items-start gap-2'>
                <Cobertura valor={q.cobertura} />
                <div className='min-w-0 flex-1'>
                  <div className='break-words'>{q.requisito}</div>
                  <div className='flex flex-wrap gap-1 pt-0.5 text-xs text-muted-foreground'>
                    <Badge
                      variant='outline'
                      className={cn(
                        'h-5 font-normal',
                        q.importancia === 'critico' && 'border-foreground/40'
                      )}
                    >
                      {VALORES[q.importancia]}
                    </Badge>
                    {q.origen === 'inferido' && (
                      <Badge variant='outline' className='h-5 font-normal'>
                        inferido
                      </Badge>
                    )}
                    {q.competencia && <span>· tu {q.competencia}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Seccion>
      </CardContent>
    </Card>
  )
}

function Seccion({
  titulo,
  children,
}: {
  titulo: string
  children: React.ReactNode
}) {
  return (
    <div className='flex flex-col gap-2'>
      <span className='text-xs font-medium tracking-wide text-muted-foreground uppercase'>
        {titulo}
      </span>
      {children}
    </div>
  )
}

function Cita({ texto }: { texto?: string | null }) {
  if (!texto) return null
  return (
    <div className='flex gap-1.5 pt-1 text-xs text-muted-foreground italic'>
      <Quote className='size-3 shrink-0' /> {texto}
    </div>
  )
}

function Compuerta({
  nombre,
  criterio: c,
}: {
  nombre: string
  criterio: Criterio
}) {
  const estilo = {
    pasa: ['text-emerald-600', Check],
    no_pasa: ['text-rose-600', Ban],
    marca: ['text-amber-600', AlertTriangle],
    sin_datos: ['text-muted-foreground', Minus],
  }[c.valor] ?? ['text-muted-foreground', Minus]
  const [color, Icono] = estilo as [string, React.ElementType]
  return (
    <div className='rounded-md border p-2.5 text-sm'>
      <div className='flex items-center justify-between'>
        <span className='font-medium'>
          {NOMBRES_CRITERIO[nombre] ?? nombre}
        </span>
        <span className={cn('flex items-center gap-1 text-xs', color)}>
          <Icono className='size-3.5' />
          {VALORES[c.valor]}
        </span>
      </div>
      <p className='pt-1 text-xs text-muted-foreground'>{c.motivo}</p>
      <Cita texto={c.cita} />
    </div>
  )
}

function Dimension({
  nombre,
  criterio: c,
  parcial,
}: {
  nombre: string
  criterio: Criterio
  parcial?: number
}) {
  return (
    <div className='flex flex-col gap-0.5 py-2 text-sm'>
      <div className='flex items-center justify-between gap-2'>
        <span className='font-medium'>
          {NOMBRES_CRITERIO[nombre] ?? nombre}
          <span className='ms-2 font-normal text-muted-foreground'>
            {VALORES[c.valor] ?? c.valor}
          </span>
        </span>
        {parcial !== undefined && (
          <Barra valor={parcial} peso={PESOS[nombre]} />
        )}
      </div>
      <p className='text-xs text-muted-foreground'>{c.motivo}</p>
      <Cita texto={c.cita} />
    </div>
  )
}

function Barra({ valor, peso }: { valor: number; peso: number }) {
  return (
    <div
      className='flex shrink-0 items-center gap-2'
      title={`${Math.round(valor * peso)} de ${peso} puntos`}
    >
      <div className='h-1.5 w-20 overflow-hidden rounded-full bg-muted'>
        <div
          className='h-full rounded-full bg-primary'
          style={{ width: `${valor * 100}%` }}
        />
      </div>
      <span className='w-12 text-end text-xs text-muted-foreground tabular-nums'>
        {Math.round(valor * peso)}/{peso}
      </span>
    </div>
  )
}

function Cobertura({ valor }: { valor: string }) {
  if (valor === 'fuerte')
    return <Check className='mt-0.5 size-4 shrink-0 text-emerald-600' />
  if (valor === 'parcial')
    return <Minus className='mt-0.5 size-4 shrink-0 text-amber-600' />
  return <X className='mt-0.5 size-4 shrink-0 text-rose-600' />
}
