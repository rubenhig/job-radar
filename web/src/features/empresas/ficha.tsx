import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, getRouteApi, useRouter } from '@tanstack/react-router'
import { ArrowLeft, Ban, Clock, Eye } from 'lucide-react'
import { toast } from 'sonner'
import {
  empresasDecidirMutation,
  empresasFichaOptions,
  puestosListarOptions,
} from '@/api/@tanstack/react-query.gen'
import { type EstadoEmpresa } from '@/lib/empresas'
import { MODALIDADES, haceCuanto, lugar } from '@/lib/formato'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { Cabecera } from '@/components/layout/cabecera'
import { Main } from '@/components/layout/main'
import { InsigniaGuardado } from '@/features/lista/componentes/guardado'
import { Nota } from '@/features/puestos/componentes/nota'
import { InsigniasEmpresa } from './index'

const ruta = getRouteApi('/_app/empresas/$empresaId')

const BOTONES: { estado: EstadoEmpresa; texto: string; icono: typeof Eye }[] = [
  { estado: 'seguida', texto: 'Seguir', icono: Eye },
  { estado: 'pendiente', texto: 'Pendiente', icono: Clock },
  { estado: 'descartada', texto: 'Descartar', icono: Ban },
]

export function FichaEmpresa() {
  const { empresaId } = ruta.useParams()
  const id = Number(empresaId)
  const router = useRouter()
  const qc = useQueryClient()
  const { data: e, isError } = useQuery({
    ...empresasFichaOptions({ path: { empresa_id: id } }),
    enabled: Number.isInteger(id),
  })
  const { data: puestos } = useQuery({
    ...puestosListarOptions({
      query: { empresa_id: id, orden: 'nota', limite: 200 },
    }),
    enabled: Number.isInteger(id),
  })
  const decidir = useMutation({
    ...empresasDecidirMutation(),
    onSuccess: () => {
      // descartar o seguir cambia la criba y las marcas de sus puestos en todas las pantallas
      qc.invalidateQueries({
        predicate: (q) =>
          [
            'empresasListar',
            'empresasFicha',
            'puestosListar',
            'puestosFicha',
            'sistemaResumen',
          ].includes((q.queryKey[0] as { _id?: string })?._id ?? ''),
      })
    },
  })
  const [notas, setNotas] = useState<string | null>(null)

  if (isError || !Number.isInteger(id)) {
    return (
      <>
        <Cabecera />
        <Main className='flex flex-col items-start gap-3'>
          <h1 className='text-xl font-semibold'>No existe esa empresa</h1>
          <Button asChild variant='outline'>
            <Link to='/empresas'>
              <ArrowLeft /> Ir a Empresas
            </Link>
          </Button>
        </Main>
      </>
    )
  }
  if (!e) {
    return (
      <>
        <Cabecera />
        <Main className='flex flex-col gap-4'>
          <Skeleton className='h-10 w-2/3' />
          <Skeleton className='h-40' />
        </Main>
      </>
    )
  }

  const cambiar = (estado: EstadoEmpresa | null) =>
    decidir.mutate(
      { path: { empresa_id: id }, body: { estado } },
      {
        onSuccess: () =>
          toast.success(
            estado === 'descartada'
              ? 'Empresa descartada: sus puestos pasan a Descartados'
              : estado === 'seguida'
                ? 'Siguiendo la empresa'
                : estado
                  ? 'Marcada como pendiente'
                  : 'Sin revisar'
          ),
      }
    )
  const texto = notas ?? e.notas ?? ''
  const cifras = [
    ['Abiertos', e.puestos_abiertos],
    ['Top (≥ 50)', e.puestos_buenos],
    ['Con IA', e.puestos_ia],
    ['Remotos', e.puestos_remotos],
    ['Mejor nota', e.mejor_nota ?? '—'],
  ] as const

  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div className='flex flex-col gap-2'>
          <button
            type='button'
            onClick={() =>
              router.history.canGoBack()
                ? router.history.back()
                : router.navigate({ to: '/empresas' })
            }
            className='flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground'
          >
            <ArrowLeft className='size-4' /> Empresas
          </button>
          <h1 className='text-2xl font-bold tracking-tight break-words'>
            {e.nombre}
          </h1>
          <div className='flex flex-wrap items-center gap-1.5 text-sm text-muted-foreground'>
            <InsigniasEmpresa empresa={e} />
            {(e.alias ?? []).length > 1 && (
              <span>También como: {(e.alias ?? []).join(', ')}</span>
            )}
          </div>
        </div>

        <div className='grid grid-cols-2 gap-3 sm:grid-cols-5'>
          {cifras.map(([k, v]) => (
            <Card key={k} className='gap-1 py-4'>
              <CardContent className='px-4'>
                <div className='text-2xl font-bold tabular-nums'>{v}</div>
                <p className='text-xs text-muted-foreground'>{k}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className='grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]'>
          <Card className='min-w-0 lg:order-1'>
            <CardHeader>
              <CardTitle>Puestos ({puestos?.total ?? '…'})</CardTitle>
              <CardDescription>
                Abiertos y cerrados, de mejor a peor nota.
              </CardDescription>
            </CardHeader>
            <CardContent className='flex flex-col divide-y'>
              {!puestos && <Skeleton className='h-32' />}
              {puestos?.items.map((p) => (
                <Link
                  key={p.id}
                  to='/puestos/$puestoId'
                  params={{ puestoId: String(p.id) }}
                  className={cn(
                    '-mx-2 flex items-center gap-3 rounded-md px-2 py-2 hover:bg-accent',
                    (p.estado === 'cerrado' || p.descarte) && 'opacity-60'
                  )}
                >
                  <Nota valoracion={p.valoracion} />
                  <div className='min-w-0 flex-1'>
                    <div className='truncate font-medium'>{p.titulo}</div>
                    <div className='truncate text-xs text-muted-foreground'>
                      {[
                        lugar(p.ciudad, p.pais),
                        p.modalidad && MODALIDADES[p.modalidad],
                        p.estado === 'cerrado'
                          ? 'cerrado'
                          : `visto ${haceCuanto(p.vista_primera)}`,
                        p.descarte && `descartado: ${p.descarte}`,
                      ]
                        .filter(Boolean)
                        .join(' · ')}
                    </div>
                  </div>
                  <InsigniaGuardado guardado={p.guardado} />
                </Link>
              ))}
            </CardContent>
          </Card>

          <div className='flex flex-col gap-6 lg:order-2'>
            <Card>
              <CardHeader>
                <CardTitle>¿Te interesa?</CardTitle>
                <CardDescription>
                  Si la descartas, sus puestos pasan a Descartados. Si la
                  sigues, se marcan en la lista.
                </CardDescription>
              </CardHeader>
              <CardContent className='flex flex-col gap-2'>
                <div className='grid grid-cols-3 gap-2'>
                  {BOTONES.map(({ estado, texto, icono: Icono }) => (
                    <Button
                      key={estado}
                      variant={e.estado === estado ? 'default' : 'outline'}
                      disabled={decidir.isPending}
                      onClick={() => cambiar(estado)}
                    >
                      <Icono /> {texto}
                    </Button>
                  ))}
                </div>
                {e.estado && (
                  <Button
                    variant='ghost'
                    size='sm'
                    className='w-fit text-muted-foreground'
                    disabled={decidir.isPending}
                    onClick={() => cambiar(null)}
                  >
                    Dejar sin revisar
                  </Button>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Notas</CardTitle>
              </CardHeader>
              <CardContent className='flex flex-col gap-2'>
                <Textarea
                  value={texto}
                  onChange={(ev) => setNotas(ev.target.value)}
                  placeholder='Qué hacen, a quién conoces allí, cultura, salarios…'
                />
                {texto !== (e.notas ?? '') && (
                  <Button
                    size='sm'
                    className='w-fit'
                    disabled={decidir.isPending}
                    onClick={() =>
                      decidir.mutate(
                        { path: { empresa_id: id }, body: { notas: texto } },
                        {
                          onSuccess: () => {
                            setNotas(null)
                            toast.success('Notas guardadas')
                          },
                        }
                      )
                    }
                  >
                    Guardar notas
                  </Button>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </Main>
    </>
  )
}
