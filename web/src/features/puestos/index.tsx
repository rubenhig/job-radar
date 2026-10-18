import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Link, getRouteApi } from '@tanstack/react-router'
import type { PuestoResumen } from '@/api'
import { ChevronLeft, ChevronRight, Filter, Trash2, X } from 'lucide-react'
import {
  puestosListarOptions,
  sistemaResumenOptions,
} from '@/api/@tanstack/react-query.gen'
import { FUENTES, MODALIDADES, haceCuanto, lugar, salario } from '@/lib/formato'
import { DESTACADO, TOP } from '@/lib/puntuacion'
import { esNuevo, useVisita } from '@/lib/visita'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
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
import { InsigniaEtiqueta } from './componentes/etiqueta'
import { Nota } from './componentes/nota'
import { Vias } from './componentes/vias'

const ruta = getRouteApi('/_app/puestos/')
const POR_PAGINA = 25

const ETIQUETAS = {
  todas: 'Cualquier etiqueta',
  sin: 'Sin etiquetar',
  top: 'Top',
  no_top: 'No top',
} as const
const NOTAS = {
  todas: 'Cualquier nota',
  destacados: `Desde ${DESTACADO}`,
  top: `Desde ${TOP}`,
  sin: 'Sin puntuar',
} as const
const ORDENES = {
  nota: 'Orden: mejor nota',
  recientes: 'Orden: más recientes',
  publicadas: 'Fecha de publicación',
  vias: 'Más vías',
} as const

export function Puestos() {
  const busqueda = ruta.useSearch()
  const navegar = ruta.useNavigate()
  const cambiar = (cambios: Partial<typeof busqueda>) =>
    navegar({
      search: (prev) => ({ ...prev, pagina: 1, ...cambios }),
      replace: true,
    })

  // El texto se busca al dejar de escribir; si la URL cambia por fuera (el menú, «Quitar filtros»), manda la URL.
  const [texto, setTexto] = useState(busqueda.q ?? '')
  const [qVista, setQVista] = useState(busqueda.q)
  if (busqueda.q !== qVista) {
    // ajustar el estado al cambiar la URL, durante el render (sin un efecto que repinte dos veces)
    setQVista(busqueda.q)
    setTexto(busqueda.q ?? '')
  }
  useEffect(() => {
    if (texto === (busqueda.q ?? '')) return
    const t = setTimeout(() => cambiar({ q: texto || undefined }), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [texto])

  const visita = useVisita()
  const pagina = busqueda.pagina ?? 1
  const { data, isLoading } = useQuery({
    ...puestosListarOptions({
      query: {
        q: busqueda.q,
        fuente: busqueda.fuente,
        modalidad: busqueda.modalidad,
        etiqueta: busqueda.etiqueta === 'todas' ? undefined : busqueda.etiqueta,
        dias: busqueda.dias,
        orden: busqueda.orden ?? 'nota',
        nota_min:
          busqueda.nota === 'destacados'
            ? DESTACADO
            : busqueda.nota === 'top'
              ? TOP
              : undefined,
        puntuado: busqueda.nota === 'sin' ? false : undefined,
        descartados: busqueda.descartados,
        nuevos_desde: busqueda.nuevos
          ? (visita?.desde ?? undefined)
          : undefined,
        limite: POR_PAGINA,
        desde: (pagina - 1) * POR_PAGINA,
      },
    }),
    placeholderData: keepPreviousData,
    enabled: !busqueda.nuevos || visita !== undefined,
  })
  const { data: resumen } = useQuery(sistemaResumenOptions())
  const paginas = Math.max(1, Math.ceil((data?.total ?? 0) / POR_PAGINA))
  const filtrado = Boolean(
    busqueda.q ||
    busqueda.fuente?.length ||
    busqueda.modalidad?.length ||
    (busqueda.etiqueta && busqueda.etiqueta !== 'todas') ||
    busqueda.dias ||
    (busqueda.nota && busqueda.nota !== 'todas') ||
    busqueda.descartados ||
    busqueda.nuevos
  )

  return (
    <>
      <Cabecera />
      <Main className='flex flex-1 flex-col gap-4'>
        <div className='flex flex-wrap items-end justify-between gap-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>
              {busqueda.descartados ? 'Descartados' : 'Puestos'}
            </h2>
            <p className='text-muted-foreground'>
              {busqueda.descartados
                ? `${data?.total ?? '…'} puestos que la criba deja fuera sin puntuarlos: otro país o un título que no es técnico. Se ajusta en Perfil.`
                : `${data ? `${data.total} puestos` : 'Cargando…'}: la misma vacante, venga de la fuente o la consultora que venga.`}
            </p>
          </div>
          <Button
            variant={busqueda.descartados ? 'secondary' : 'ghost'}
            size='sm'
            onClick={() =>
              cambiar({ descartados: busqueda.descartados ? undefined : true })
            }
          >
            <Trash2 />
            {busqueda.descartados
              ? 'Volver a los puestos'
              : `Descartados (${resumen?.descartados ?? '…'})`}
          </Button>
        </div>

        <div className='flex flex-wrap items-center gap-2'>
          <Input
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            placeholder='Buscar en título, empresa o descripción…'
            className='h-9 w-full sm:w-72'
          />
          <Multiple
            titulo='Fuente'
            opciones={FUENTES}
            valores={busqueda.fuente ?? []}
            onChange={(v) => cambiar({ fuente: v.length ? v : undefined })}
          />
          <Multiple
            titulo='Modalidad'
            opciones={MODALIDADES}
            valores={busqueda.modalidad ?? []}
            onChange={(v) => cambiar({ modalidad: v.length ? v : undefined })}
          />
          <Select
            value={busqueda.etiqueta ?? 'todas'}
            onValueChange={(v) =>
              cambiar({ etiqueta: v as keyof typeof ETIQUETAS })
            }
          >
            <SelectTrigger aria-label='Etiqueta' className='h-9 w-36'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(ETIQUETAS).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={String(busqueda.dias ?? 0)}
            onValueChange={(v) => cambiar({ dias: Number(v) || undefined })}
          >
            <SelectTrigger aria-label='Fecha' className='h-9 w-40'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='0'>Cualquier fecha</SelectItem>
              <SelectItem value='1'>Últimas 24 h</SelectItem>
              <SelectItem value='7'>Última semana</SelectItem>
              <SelectItem value='30'>Último mes</SelectItem>
            </SelectContent>
          </Select>
          <Select
            value={busqueda.nota ?? 'todas'}
            onValueChange={(v) => cambiar({ nota: v as keyof typeof NOTAS })}
          >
            <SelectTrigger aria-label='Nota' className='h-9 w-40'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(NOTAS).map(([k, v]) => (
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
            <SelectTrigger aria-label='Orden' className='h-9 w-44'>
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
          {visita?.desde && (
            <Button
              variant={busqueda.nuevos ? 'secondary' : 'outline'}
              size='sm'
              className='h-9'
              onClick={() =>
                cambiar({ nuevos: busqueda.nuevos ? undefined : true })
              }
            >
              Solo nuevos
            </Button>
          )}
          {filtrado && (
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

        {/* Ordenador: tabla. Móvil: tarjetas. */}
        <div className='hidden overflow-hidden rounded-md border md:block'>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className='w-14 text-center'>Nota</TableHead>
                <TableHead>Puesto</TableHead>
                <TableHead>Lugar</TableHead>
                <TableHead>Salario</TableHead>
                <TableHead>Vías</TableHead>
                <TableHead className='text-end'>Visto</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                [...Array(8)].map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={6}>
                      <Skeleton className='h-8' />
                    </TableCell>
                  </TableRow>
                ))}
              {data?.items.map((p) => (
                <Fila key={p.id} puesto={p} desde={visita?.desde} />
              ))}
              {data && !data.items.length && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className='h-24 text-center text-muted-foreground'
                  >
                    Ningún puesto con estos filtros.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className='flex flex-col gap-2 md:hidden'>
          {isLoading &&
            [...Array(5)].map((_, i) => <Skeleton key={i} className='h-24' />)}
          {data?.items.map((p) => (
            <Tarjeta key={p.id} puesto={p} desde={visita?.desde} />
          ))}
          {data && !data.items.length && (
            <p className='py-10 text-center text-muted-foreground'>
              Ningún puesto con estos filtros.
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

function Multiple({
  titulo,
  opciones,
  valores,
  onChange,
}: {
  titulo: string
  opciones: Record<string, string>
  valores: string[]
  onChange: (v: string[]) => void
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant='outline' size='sm' className='h-9 border-dashed'>
          <Filter /> {titulo}
          {valores.length > 0 && (
            <Badge variant='secondary' className='rounded-sm px-1'>
              {valores.length}
            </Badge>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align='start'>
        <DropdownMenuLabel>{titulo}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {Object.entries(opciones).map(([k, v]) => (
          <DropdownMenuCheckboxItem
            key={k}
            checked={valores.includes(k)}
            onSelect={(e) => e.preventDefault()}
            onCheckedChange={(c) =>
              onChange(c ? [...valores, k] : valores.filter((x) => x !== k))
            }
          >
            {v}
          </DropdownMenuCheckboxItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Nuevo() {
  return (
    <Badge className='bg-sky-600 px-1.5 text-[10px] text-white hover:bg-sky-600'>
      Nuevo
    </Badge>
  )
}

function Fila({
  puesto: p,
  desde,
}: {
  puesto: PuestoResumen
  desde?: string | null
}) {
  return (
    <TableRow className='relative'>
      <TableCell className='text-center'>
        <Nota valoracion={p.valoracion} />
      </TableCell>
      <TableCell className='max-w-md whitespace-normal'>
        <Link
          to='/puestos/$puestoId'
          params={{ puestoId: String(p.id) }}
          className='font-medium after:absolute after:inset-0 hover:underline'
        >
          {p.titulo}
        </Link>
        <div className='flex items-center gap-2 text-sm text-muted-foreground'>
          {p.empresa ?? '—'} <InsigniaEtiqueta etiqueta={p.etiqueta} />
          {esNuevo(p.vista_primera, desde) && <Nuevo />}
        </div>
        {p.descarte && (
          <div className='text-xs text-destructive'>
            Descartado: {p.descarte}
          </div>
        )}
      </TableCell>
      <TableCell className='text-sm whitespace-normal'>
        {lugar(p.ciudad, p.pais) ?? '—'}
        {p.modalidad && (
          <div className='text-muted-foreground'>
            {MODALIDADES[p.modalidad]}
          </div>
        )}
      </TableCell>
      <TableCell className='text-sm whitespace-nowrap'>
        {salario(p.salario) ?? '—'}
      </TableCell>
      <TableCell>
        <Vias vias={p.vias} />
      </TableCell>
      <TableCell className='text-end text-sm whitespace-nowrap text-muted-foreground'>
        {haceCuanto(p.vista_primera)}
      </TableCell>
    </TableRow>
  )
}

function Tarjeta({
  puesto: p,
  desde,
}: {
  puesto: PuestoResumen
  desde?: string | null
}) {
  return (
    <Link
      to='/puestos/$puestoId'
      params={{ puestoId: String(p.id) }}
      className='flex flex-col gap-2 rounded-lg border p-3 active:bg-accent'
    >
      <div className='flex items-start justify-between gap-2'>
        <span className='leading-snug font-medium'>{p.titulo}</span>
        <div className='flex shrink-0 items-center gap-1.5'>
          {esNuevo(p.vista_primera, desde) && <Nuevo />}
          <InsigniaEtiqueta etiqueta={p.etiqueta} />
          {p.valoracion && <Nota valoracion={p.valoracion} />}
        </div>
      </div>
      <div className='text-sm text-muted-foreground'>
        {[
          p.empresa,
          lugar(p.ciudad, p.pais),
          p.modalidad && MODALIDADES[p.modalidad],
          salario(p.salario),
        ]
          .filter(Boolean)
          .join(' · ')}
      </div>
      {p.descarte && (
        <div className='text-xs text-destructive'>Descartado: {p.descarte}</div>
      )}
      <div className='flex items-center justify-between'>
        <Vias vias={p.vias} />
        <span className='text-xs text-muted-foreground'>
          {haceCuanto(p.vista_primera)}
        </span>
      </div>
    </Link>
  )
}
