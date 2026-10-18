import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, getRouteApi, useRouter } from '@tanstack/react-router'
import type { Oferta } from '@/api'
import { ArrowLeft, ExternalLink } from 'lucide-react'
import { puestosFichaOptions } from '@/api/@tanstack/react-query.gen'
import {
  CONTRATOS,
  FUENTES,
  MODALIDADES,
  haceCuanto,
  lugar,
  salario,
} from '@/lib/formato'
import { citasDe, tramosCitados } from '@/lib/puntuacion'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Cabecera } from '@/components/layout/cabecera'
import { Main } from '@/components/layout/main'
import { TarjetaGuardado } from '@/features/lista/componentes/guardado'
import { BotonesEtiqueta } from './componentes/etiqueta'
import { TarjetaPuntuacion } from './componentes/puntuacion'
import { Vias } from './componentes/vias'

const ruta = getRouteApi('/_app/puestos/$puestoId')

const NOMBRES: Record<string, string> = {
  titulo: 'Título',
  empresa: 'Empresa',
  ciudad: 'Ciudad',
  region: 'Región',
  pais: 'País',
  modalidad: 'Modalidad',
  salario: 'Salario',
  experiencia: 'Experiencia',
  contrato: 'Contrato',
  skills: 'Skills',
  ingles: 'Inglés',
  url: 'Enlace',
  descripcion: 'Descripción',
}

export function FichaPuesto() {
  const { puestoId } = ruta.useParams()
  const id = Number(puestoId)
  const { data: p, isError } = useQuery({
    ...puestosFichaOptions({ path: { puesto_id: id } }),
    enabled: Number.isInteger(id),
  })
  const [elegida, setElegida] = useState<number | null>(null)
  const router = useRouter()
  const volver = () =>
    router.history.canGoBack()
      ? router.history.back()
      : router.navigate({ to: '/puestos' })

  if (isError || !Number.isInteger(id)) {
    return (
      <>
        <Cabecera />
        <Main className='flex flex-col items-start gap-3'>
          <h1 className='text-xl font-semibold'>No existe ese puesto</h1>
          <p className='text-muted-foreground'>
            Puede que se haya fusionado con otro o que el enlace esté mal.
          </p>
          <Button asChild variant='outline'>
            <Link to='/puestos'>
              <ArrowLeft /> Ir a Puestos
            </Link>
          </Button>
        </Main>
      </>
    )
  }

  if (!p) {
    return (
      <>
        <Cabecera />
        <Main className='flex flex-col gap-4'>
          <Skeleton className='h-10 w-2/3' />
          <Skeleton className='h-40' />
          <Skeleton className='h-96' />
        </Main>
      </>
    )
  }

  const idDescripcion =
    (p.fusion.descripcion?.oferta_id as number | undefined) ??
    p.lista_ofertas[0]?.id
  const oferta =
    p.lista_ofertas.find((o) => o.id === (elegida ?? idDescripcion)) ??
    p.lista_ofertas[0]
  const datos = [
    lugar(p.ciudad, p.pais),
    p.modalidad && MODALIDADES[p.modalidad],
    salario(p.salario),
    p.publicada_en && `publicado ${haceCuanto(p.publicada_en)}`,
  ].filter((d) => d && d !== '—')

  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div className='flex flex-col gap-2'>
          <button
            type='button'
            onClick={volver}
            className='flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground'
          >
            <ArrowLeft className='size-4' /> Puestos
          </button>
          <h1 className='text-2xl font-bold tracking-tight break-words'>
            {p.titulo}
          </h1>
          <div className='text-muted-foreground'>
            {p.empresa ?? 'Empresa sin indicar'}
          </div>
          <div className='flex flex-wrap gap-2'>
            {datos.map((d) => (
              <Badge
                key={d as string}
                variant='secondary'
                className='font-normal'
              >
                {d}
              </Badge>
            ))}
          </div>
          {p.estado === 'cerrado' && (
            <p className='text-sm text-muted-foreground'>
              Cerrado: la oferta ha caducado o ya no se publica.
            </p>
          )}
          {p.descarte && (
            <p className='text-sm text-destructive'>
              Descartado sin puntuar: {p.descarte}. Si es un error, márcalo como
              top y volverá a la lista.
            </p>
          )}
        </div>

        <div className='grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]'>
          <div className='flex min-w-0 flex-col gap-6 break-words lg:order-1'>
            <TarjetaPuntuacion evaluacion={p.evaluacion} />
            <Card>
              <CardHeader>
                <CardTitle>Descripción</CardTitle>
                {p.lista_ofertas.length > 1 && (
                  <CardDescription>
                    Cada vía publica su versión del anuncio.
                  </CardDescription>
                )}
                {p.lista_ofertas.length > 1 && (
                  <div className='flex flex-wrap gap-1.5 pt-2'>
                    {p.lista_ofertas.map((o) => (
                      <Button
                        key={o.id}
                        size='sm'
                        variant={o.id === oferta.id ? 'secondary' : 'ghost'}
                        className='h-7 border text-xs'
                        onClick={() => setElegida(o.id)}
                      >
                        {FUENTES[o.fuente_id] ?? o.fuente_id} ·{' '}
                        {o.empresa ?? '?'}
                      </Button>
                    ))}
                  </div>
                )}
              </CardHeader>
              <CardContent>
                <Descripcion
                  oferta={oferta}
                  citas={
                    oferta.id === idDescripcion ? citasDe(p.evaluacion) : []
                  }
                />
              </CardContent>
            </Card>
          </div>

          <div className='flex flex-col gap-6 lg:order-2'>
            <TarjetaGuardado
              key={`${p.id}-${p.guardado?.actualizado_en ?? ''}`}
              puestoId={p.id}
              guardado={p.guardado}
            />
            <Card>
              <CardHeader>
                <CardTitle>¿Es top para ti?</CardTitle>
                <CardDescription>
                  Tus etiquetas son la vara de medir de la puntuación
                  automática.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <BotonesEtiqueta
                  key={p.id}
                  puestoId={p.id}
                  actual={p.etiqueta}
                  conMotivos
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Vías ({p.ofertas})</CardTitle>
                <CardDescription>Por dónde llega este puesto.</CardDescription>
              </CardHeader>
              <CardContent className='flex flex-col gap-3'>
                <Vias vias={p.vias} />
                <ul className='flex flex-col divide-y text-sm'>
                  {p.lista_ofertas.map((o) => (
                    <li
                      key={o.id}
                      className='flex items-center justify-between gap-2 py-2'
                    >
                      <div className='min-w-0'>
                        <div className='truncate font-medium'>
                          {o.empresa ?? '?'}
                        </div>
                        <div className='text-xs text-muted-foreground'>
                          {FUENTES[o.fuente_id] ?? o.fuente_id} · visto{' '}
                          {haceCuanto(o.vista_primera)}
                        </div>
                      </div>
                      {o.url && (
                        <Button
                          asChild
                          size='icon'
                          variant='ghost'
                          className='shrink-0'
                        >
                          <a
                            href={o.url}
                            target='_blank'
                            rel='noreferrer'
                            aria-label='Abrir la oferta original'
                          >
                            <ExternalLink />
                          </a>
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Datos y procedencia</CardTitle>
                <CardDescription>
                  Cada dato, de qué fuente sale. ✦ = inferido por un modelo de
                  la fuente.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <dl className='grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm'>
                  {Object.entries(p.fusion)
                    .filter(
                      ([k]) =>
                        NOMBRES[k] &&
                        !['descripcion', 'url', 'titulo'].includes(k)
                    )
                    .map(([k, c]) => {
                      const origen = p.lista_ofertas.find(
                        (o) => o.id === c.oferta_id
                      )
                      const inferido = origen?.derivados?.some(
                        (d) => d === k || d.startsWith(`${k}_`)
                      )
                      return (
                        <div key={k} className='contents'>
                          <dt className='text-muted-foreground'>
                            {NOMBRES[k]}
                          </dt>
                          <dd className='min-w-0'>
                            <span className='break-words'>
                              {valor(k, c.valor)}
                            </span>
                            {c.fuente && (
                              <span className='ms-1 text-xs text-muted-foreground'>
                                · {FUENTES[c.fuente] ?? c.fuente}
                                {inferido && ' ✦'}
                              </span>
                            )}
                          </dd>
                        </div>
                      )
                    })}
                </dl>
              </CardContent>
            </Card>
          </div>
        </div>
      </Main>
    </>
  )
}

function valor(campo: string, v: unknown): string {
  if (v == null) return '—'
  if (campo === 'salario')
    return salario(v as Parameters<typeof salario>[0]) ?? '—'
  if (campo === 'modalidad') return MODALIDADES[v as string] ?? String(v)
  if (campo === 'contrato') return CONTRATOS[v as string] ?? String(v)
  if (campo === 'skills') {
    const lista =
      typeof v === 'string' ? (JSON.parse(v) as string[]) : (v as string[])
    return lista.join(', ')
  }
  return String(v)
}

function Descripcion({ oferta, citas }: { oferta: Oferta; citas: string[] }) {
  const [entera, setEntera] = useState(false)
  const texto = oferta.descripcion ?? 'Esta vía no trae descripción.'
  const larga = texto.length > 1600
  // Las frases en las que se apoya la puntuación, resaltadas.
  const trozos: React.ReactNode[] = []
  let desde = 0
  for (const [a, b] of tramosCitados(texto, citas)) {
    trozos.push(texto.slice(desde, a))
    trozos.push(
      <mark
        key={a}
        className='rounded-sm bg-amber-300/40 px-0.5 text-inherit dark:bg-amber-400/25'
      >
        {texto.slice(a, b)}
      </mark>
    )
    desde = b
  }
  trozos.push(texto.slice(desde))
  return (
    <div className='flex flex-col gap-2'>
      <div
        className={cn(
          'text-sm leading-relaxed whitespace-pre-line',
          !entera && larga && 'line-clamp-[18]'
        )}
      >
        {trozos}
      </div>
      {larga && (
        <Button
          variant='link'
          className='w-fit px-0'
          onClick={() => setEntera(!entera)}
        >
          {entera ? 'Ver menos' : 'Ver todo'}
        </Button>
      )}
    </div>
  )
}
