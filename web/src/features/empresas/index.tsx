import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import type { EmpresaResumen } from '@/api'
import { ChevronLeft, ChevronRight, X } from 'lucide-react'
import { empresasListarOptions } from '@/api/@tanstack/react-query.gen'
import { COLOR_EMPRESA, ESTADOS_EMPRESA } from '@/lib/empresas'
import { haceCuanto } from '@/lib/formato'
import { colorNota } from '@/lib/puntuacion'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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

const ruta = getRouteApi('/_app/empresas/')
const POR_PAGINA = 30
const FILTRO_ESTADO = {
  todas: 'Cualquier estado',
  sin_revisar: 'Sin revisar',
  seguida: 'Seguidas',
  pendiente: 'Pendientes',
  descartada: 'Descartadas',
} as const
const ORDENES = {
  nota: 'Orden: mejor nota',
  puestos: 'Orden: más puestos',
  recientes: 'Orden: recientes',
  nombre: 'Orden: nombre',
} as const

export function Empresas() {
  const busqueda = ruta.useSearch()
  const navegar = ruta.useNavigate()
  const cambiar = (c: Partial<typeof busqueda>) =>
    navegar({
      search: (prev) => ({ ...prev, pagina: 1, ...c }),
      replace: true,
    })
  const [texto, setTexto] = useState(busqueda.q ?? '')
  const [qVista, setQVista] = useState(busqueda.q)
  if (busqueda.q !== qVista) {
    setQVista(busqueda.q)
    setTexto(busqueda.q ?? '')
  }
  useEffect(() => {
    if (texto === (busqueda.q ?? '')) return
    const t = setTimeout(() => cambiar({ q: texto || undefined }), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto])

  const pagina = busqueda.pagina ?? 1
  const { data, isLoading } = useQuery({
    ...empresasListarOptions({
      query: {
        q: busqueda.q,
        estado:
          busqueda.estado && busqueda.estado !== 'todas'
            ? [busqueda.estado]
            : undefined,
        consultoras: busqueda.consultoras ? undefined : false,
        orden: busqueda.orden ?? 'nota',
        limite: POR_PAGINA,
        desde: (pagina - 1) * POR_PAGINA,
      },
    }),
    placeholderData: keepPreviousData,
  })
  const paginas = Math.max(1, Math.ceil((data?.total ?? 0) / POR_PAGINA))

  return (
    <>
      <Cabecera />
      <Main className='flex flex-1 flex-col gap-4'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Empresas</h2>
          <p className='text-muted-foreground'>
            {data ? `${data.total} empresas` : 'Cargando…'} con puestos
            abiertos. Síguelas o descártalas: sus puestos se marcan o se
            descartan solos.
          </p>
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <Input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder='Buscar empresa…'
            className='h-9 w-full sm:w-64'
          />
          <Select
            value={busqueda.estado ?? 'todas'}
            onValueChange={(v) =>
              cambiar({ estado: v as keyof typeof FILTRO_ESTADO })
            }
          >
            <SelectTrigger aria-label='Estado' className='h-9 w-44'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(FILTRO_ESTADO).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={busqueda.orden ?? 'nota'}
            onValueChange={(v) => cambiar({ orden: v as keyof typeof ORDENES })}
          >
            <SelectTrigger aria-label='Orden' className='h-9 w-48'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(ORDENES).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size='sm'
            variant={busqueda.consultoras ? 'secondary' : 'ghost'}
            onClick={() =>
              cambiar({ consultoras: busqueda.consultoras ? undefined : true })
            }
          >
            {busqueda.consultoras ? 'Ocultar consultoras' : 'Ver consultoras'}
          </Button>
          {(busqueda.q || busqueda.estado || busqueda.consultoras) && (
            <Button
              variant='ghost'
              size='sm'
              onClick={() => {
                setTexto('')
                navegar({ search: {} })
              }}
            >
              Quitar filtros <X />
            </Button>
          )}
        </div>

        <div className='hidden overflow-hidden rounded-md border md:block'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Empresa</TableHead>
                <TableHead className='text-center'>Mejor nota</TableHead>
                <TableHead className='text-end'>Abiertos</TableHead>
                <TableHead className='text-end'>Top</TableHead>
                <TableHead className='text-end'>Con IA</TableHead>
                <TableHead className='text-end'>Remotos</TableHead>
                <TableHead className='text-end'>Visto</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                [...Array(8)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className='h-8' />
                    </TableCell>
                  </TableRow>
                ))}
              {data?.items.map((e) => (
                <FilaEmpresa key={e.id} empresa={e} />
              ))}
              {data && !data.items.length && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className='h-24 text-center text-muted-foreground'
                  >
                    Ninguna empresa con estos filtros.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className='flex flex-col gap-2 md:hidden'>
          {isLoading &&
            [...Array(5)].map((_, i) => <Skeleton key={i} className='h-20' />)}
          {data?.items.map((e) => (
            <TarjetaEmpresa key={e.id} empresa={e} />
          ))}
          {data && !data.items.length && (
            <p className='py-10 text-center text-muted-foreground'>
              Ninguna empresa con estos filtros.
            </p>
          )}
        </div>

        <div className='flex items-center justify-between gap-2'>
          <span className='text-sm text-muted-foreground'>
            Página {pagina} de {paginas}
          </span>
          <div className='flex gap-2'>
            <Button
              variant='outline'
              size='sm'
              disabled={pagina <= 1}
              onClick={() =>
                navegar({ search: (prev) => ({ ...prev, pagina: pagina - 1 }) })
              }
            >
              <ChevronLeft /> Anterior
            </Button>
            <Button
              variant='outline'
              size='sm'
              disabled={pagina >= paginas}
              onClick={() =>
                navegar({ search: (prev) => ({ ...prev, pagina: pagina + 1 }) })
              }
            >
              Siguiente <ChevronRight />
            </Button>
          </div>
        </div>
      </Main>
    </>
  )
}

export function InsigniasEmpresa({ empresa: e }: { empresa: EmpresaResumen }) {
  return (
    <>
      {e.estado && (
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-xs font-medium',
            COLOR_EMPRESA[e.estado]
          )}
        >
          {ESTADOS_EMPRESA[e.estado]}
        </span>
      )}
      {e.consultora && (
        <Badge variant='outline' className='font-normal'>
          Consultora
        </Badge>
      )}
    </>
  )
}

function NotaEmpresa({ nota }: { nota?: number | null }) {
  if (nota == null) return <span className='text-muted-foreground'>—</span>
  return (
    <span
      className={cn(
        'inline-flex min-w-10 justify-center rounded-full px-2 py-0.5 text-sm font-semibold tabular-nums',
        colorNota(nota)
      )}
    >
      {nota}
    </span>
  )
}

function FilaEmpresa({ empresa: e }: { empresa: EmpresaResumen }) {
  return (
    <TableRow className='relative'>
      <TableCell className='max-w-md whitespace-normal'>
        <Link
          to='/empresas/$empresaId'
          params={{ empresaId: String(e.id) }}
          className='font-medium after:absolute after:inset-0 hover:underline'
        >
          {e.nombre}
        </Link>
        <div className='flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground'>
          <InsigniasEmpresa empresa={e} />
          {(e.ciudades ?? []).join(', ')}
        </div>
      </TableCell>
      <TableCell className='text-center'>
        <NotaEmpresa nota={e.mejor_nota} />
      </TableCell>
      <TableCell className='text-end tabular-nums'>
        {e.puestos_abiertos}
      </TableCell>
      <TableCell className='text-end tabular-nums'>
        {e.puestos_buenos}
      </TableCell>
      <TableCell className='text-end tabular-nums'>{e.puestos_ia}</TableCell>
      <TableCell className='text-end tabular-nums'>
        {e.puestos_remotos}
      </TableCell>
      <TableCell className='text-end text-sm whitespace-nowrap text-muted-foreground'>
        {e.vista_ultima ? haceCuanto(e.vista_ultima) : '—'}
      </TableCell>
    </TableRow>
  )
}

function TarjetaEmpresa({ empresa: e }: { empresa: EmpresaResumen }) {
  return (
    <Link
      to='/empresas/$empresaId'
      params={{ empresaId: String(e.id) }}
      className='flex flex-col gap-1.5 rounded-lg border p-3 active:bg-accent'
    >
      <div className='flex items-start justify-between gap-2'>
        <span className='font-medium'>{e.nombre}</span>
        <NotaEmpresa nota={e.mejor_nota} />
      </div>
      <div className='flex flex-wrap items-center gap-1.5'>
        <InsigniasEmpresa empresa={e} />
      </div>
      <div className='text-sm text-muted-foreground'>
        {e.puestos_abiertos} abiertos · {e.puestos_buenos} top · {e.puestos_ia}{' '}
        con IA · {e.puestos_remotos} remotos
      </div>
    </Link>
  )
}
