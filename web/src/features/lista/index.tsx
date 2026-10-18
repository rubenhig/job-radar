import { useQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import type { PuestoResumen } from '@/api'
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Rows3,
} from 'lucide-react'
import {
  listaMisEtiquetasOptions,
  puestosListarOptions,
} from '@/api/@tanstack/react-query.gen'
import { MODALIDADES, haceCuanto, lugar } from '@/lib/formato'
import { COLOR_ESTADO, ESTADOS, type EstadoLista } from '@/lib/lista'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Cabecera } from '@/components/layout/cabecera'
import { Main } from '@/components/layout/main'
import { Nota } from '@/features/puestos/componentes/nota'
import { Estrellas, SelectorEstado } from './componentes/guardado'
import { useGuardar } from './usar-guardado'

const ruta = getRouteApi('/_app/lista')
const ORDEN = Object.keys(ESTADOS) as EstadoLista[]

export function MiLista() {
  const busqueda = ruta.useSearch()
  const navegar = ruta.useNavigate()
  const cambiar = (c: Partial<typeof busqueda>) =>
    navegar({ search: (prev) => ({ ...prev, ...c }), replace: true })
  const vista = busqueda.vista ?? 'tablero'

  const { data, isLoading } = useQuery(
    puestosListarOptions({
      query: {
        guardado: true,
        orden: 'prioridad',
        limite: 200,
        mi_etiqueta: busqueda.etiqueta,
      },
    })
  )
  const { data: etiquetas } = useQuery(listaMisEtiquetasOptions())
  const items = (data?.items ?? []).filter(
    (p) => busqueda.descartados || p.guardado?.estado !== 'descartado'
  )
  const estados = busqueda.descartados
    ? ORDEN
    : ORDEN.filter((e) => e !== 'descartado')

  return (
    <>
      <Cabecera />
      <Main className='flex flex-1 flex-col gap-4'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Mi lista</h2>
          <p className='text-muted-foreground'>
            Los puestos que has guardado y en qué punto está cada uno.
          </p>
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <div className='flex rounded-md border p-0.5'>
            <Button
              size='sm'
              variant={vista === 'tablero' ? 'secondary' : 'ghost'}
              onClick={() => cambiar({ vista: 'tablero' })}
            >
              <Columns3 /> Tablero
            </Button>
            <Button
              size='sm'
              variant={vista === 'tabla' ? 'secondary' : 'ghost'}
              onClick={() => cambiar({ vista: 'tabla' })}
            >
              <Rows3 /> Tabla
            </Button>
          </div>
          <Select
            value={busqueda.etiqueta ?? '__todas'}
            onValueChange={(v) =>
              cambiar({ etiqueta: v === '__todas' ? undefined : v })
            }
          >
            <SelectTrigger aria-label='Mis etiquetas' className='h-9 w-48'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='__todas'>Todas mis etiquetas</SelectItem>
              {Object.entries(etiquetas ?? {}).map(([t, n]) => (
                <SelectItem key={t} value={t}>
                  {t} ({n})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size='sm'
            variant={busqueda.descartados ? 'secondary' : 'ghost'}
            onClick={() =>
              cambiar({ descartados: busqueda.descartados ? undefined : true })
            }
          >
            {busqueda.descartados ? 'Ocultar descartados' : 'Ver descartados'}
          </Button>
        </div>

        {isLoading && <Skeleton className='h-64' />}
        {data && !data.items.length && (
          <div className='flex flex-col items-center gap-3 rounded-lg border border-dashed py-16 text-center'>
            <Bookmark className='size-8 text-muted-foreground' />
            <p className='text-muted-foreground'>
              Aún no has guardado nada. En cualquier puesto, «Guardar en Mi
              lista».
            </p>
            <Button asChild variant='outline'>
              <Link to='/puestos'>Ir a Puestos</Link>
            </Button>
          </div>
        )}
        {data && data.items.length > 0 && vista === 'tablero' && (
          // En el móvil las columnas se desplazan dentro del tablero, no la página.
          <div className='-mx-1 overflow-x-auto pb-2'>
            <div className='flex min-w-max gap-3 px-1'>
              {estados.map((e) => {
                const columna = items.filter((p) => p.guardado?.estado === e)
                return (
                  <div
                    key={e}
                    className='flex w-72 flex-col gap-2 rounded-lg bg-muted/40 p-2'
                  >
                    <div className='flex items-center justify-between px-1'>
                      <span
                        className={cn(
                          'rounded-full px-2 py-0.5 text-xs font-medium',
                          COLOR_ESTADO[e]
                        )}
                      >
                        {ESTADOS[e]}
                      </span>
                      <span className='text-xs text-muted-foreground tabular-nums'>
                        {columna.length}
                      </span>
                    </div>
                    {columna.map((p) => (
                      <TarjetaTablero key={p.id} puesto={p} />
                    ))}
                  </div>
                )
              })}
            </div>
          </div>
        )}
        {data && data.items.length > 0 && vista === 'tabla' && (
          <div className='overflow-x-auto rounded-md border'>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Prioridad</TableHead>
                  <TableHead>Puesto</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className='text-center'>Nota</TableHead>
                  <TableHead>Mis etiquetas</TableHead>
                  <TableHead className='text-end'>Cambiado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((p) => (
                  <FilaTabla key={p.id} puesto={p} />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Main>
    </>
  )
}

function Titulo({ puesto: p }: { puesto: PuestoResumen }) {
  return (
    <div className='min-w-0'>
      <Link
        to='/puestos/$puestoId'
        params={{ puestoId: String(p.id) }}
        className='line-clamp-2 font-medium hover:underline'
      >
        {p.titulo}
      </Link>
      <div className='truncate text-xs text-muted-foreground'>
        {[
          p.empresa,
          lugar(p.ciudad, p.pais),
          p.modalidad && MODALIDADES[p.modalidad],
          p.estado === 'cerrado' && 'cerrado',
        ]
          .filter(Boolean)
          .join(' · ')}
      </div>
    </div>
  )
}

function TarjetaTablero({ puesto: p }: { puesto: PuestoResumen }) {
  const { guardar, ocupado } = useGuardar(p.id)
  const g = p.guardado!
  const i = ORDEN.indexOf(g.estado)
  const mover = (d: number) => guardar({ estado: ORDEN[i + d] })
  return (
    <div className='flex flex-col gap-2 rounded-md border bg-card p-3 shadow-xs'>
      <div className='flex items-start justify-between gap-2'>
        <Titulo puesto={p} />
        {p.valoracion && <Nota valoracion={p.valoracion} />}
      </div>
      {(g.etiquetas ?? []).length > 0 && (
        <div className='flex flex-wrap gap-1'>
          {(g.etiquetas ?? []).map((t) => (
            <Badge key={t} variant='secondary' className='font-normal'>
              {t}
            </Badge>
          ))}
        </div>
      )}
      <div className='flex items-center justify-between'>
        <Estrellas
          valor={g.prioridad ?? 0}
          onChange={(prioridad) => guardar({ prioridad })}
          tamano='size-3.5'
        />
        <div className='flex gap-0.5'>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            aria-label={i > 0 ? `Mover a ${ESTADOS[ORDEN[i - 1]]}` : undefined}
            disabled={ocupado || i === 0}
            onClick={() => mover(-1)}
          >
            <ChevronLeft />
          </Button>
          <Button
            size='icon'
            variant='ghost'
            className='size-7'
            aria-label={
              i < ORDEN.length - 1
                ? `Mover a ${ESTADOS[ORDEN[i + 1]]}`
                : undefined
            }
            disabled={ocupado || i === ORDEN.length - 1}
            onClick={() => mover(1)}
          >
            <ChevronRight />
          </Button>
        </div>
      </div>
    </div>
  )
}

function FilaTabla({ puesto: p }: { puesto: PuestoResumen }) {
  const { guardar } = useGuardar(p.id)
  const g = p.guardado!
  return (
    <TableRow>
      <TableCell>
        <Estrellas
          valor={g.prioridad ?? 0}
          onChange={(prioridad) => guardar({ prioridad })}
        />
      </TableCell>
      <TableCell className='max-w-sm whitespace-normal'>
        <Titulo puesto={p} />
      </TableCell>
      <TableCell>
        <SelectorEstado
          valor={g.estado}
          onChange={(estado) => guardar({ estado })}
          className='w-40'
        />
      </TableCell>
      <TableCell className='text-center'>
        <Nota valoracion={p.valoracion} />
      </TableCell>
      <TableCell className='whitespace-normal'>
        <div className='flex flex-wrap gap-1'>
          {(g.etiquetas ?? []).map((t) => (
            <Badge key={t} variant='secondary' className='font-normal'>
              {t}
            </Badge>
          ))}
        </div>
      </TableCell>
      <TableCell className='text-end text-sm whitespace-nowrap text-muted-foreground'>
        {haceCuanto(g.actualizado_en)}
      </TableCell>
    </TableRow>
  )
}
