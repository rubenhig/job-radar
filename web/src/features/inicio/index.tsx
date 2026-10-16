import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import {
  AlertTriangle,
  ArrowRight,
  BriefcaseBusiness,
  GitMerge,
  Sparkles,
  Tags,
} from 'lucide-react'
import { sistemaResumenOptions } from '@/api/@tanstack/react-query.gen'
import { FUENTES } from '@/lib/formato'
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
import { OBJETIVO } from '@/features/etiquetar'

export function Inicio() {
  const { data: r } = useQuery({
    ...sistemaResumenOptions(),
    refetchInterval: 60_000,
  })
  const maximo = Math.max(1, ...Object.values(r?.por_fuente ?? {}))

  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Inicio</h2>
          <p className='text-muted-foreground'>
            Lo que ha encontrado el radar y lo que queda por hacer.
          </p>
        </div>

        {r && r.alertas > 0 && (
          <Link
            to='/fuentes'
            className='flex items-center gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-sm'
          >
            <AlertTriangle className='size-5 shrink-0 text-amber-600' />
            <span className='flex-1'>
              {r.alertas === 1
                ? 'Una fuente necesita'
                : `${r.alertas} avisos de fuentes necesitan`}{' '}
              atención.
            </span>
            <ArrowRight className='size-4' />
          </Link>
        )}

        <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
          <Kpi
            titulo='Puestos'
            valor={r?.puestos}
            detalle={r && `${r.ofertas} ofertas`}
            icono={BriefcaseBusiness}
          />
          <Kpi
            titulo='Nuevos (24 h)'
            valor={r?.puestos_nuevos_24h}
            detalle={r && `${r.puestos_nuevos_7d} en 7 días`}
            icono={Sparkles}
          />
          <Kpi
            titulo='Por varias vías'
            valor={r?.varias_vias}
            detalle='fuentes o consultoras'
            icono={GitMerge}
          />
          <Kpi
            titulo='Etiquetados'
            valor={r && `${r.etiquetados}/${OBJETIVO}`}
            detalle={r && `${r.etiquetados_top} top`}
            icono={Tags}
          />
        </div>

        <div className='grid gap-4 lg:grid-cols-2'>
          <Card>
            <CardHeader>
              <CardTitle>Ofertas por fuente</CardTitle>
              <CardDescription>Todo lo guardado hasta ahora.</CardDescription>
            </CardHeader>
            <CardContent className='flex flex-col gap-3'>
              {!r && <Skeleton className='h-32' />}
              {r &&
                Object.entries(r.por_fuente)
                  .sort((a, b) => b[1] - a[1])
                  .map(([f, n]) => (
                    <div
                      key={f}
                      className='grid grid-cols-[6rem_1fr_3rem] items-center gap-3 text-sm'
                    >
                      <span>{FUENTES[f] ?? f}</span>
                      <div className='h-2.5 overflow-hidden rounded-full bg-muted'>
                        <div
                          className='h-full rounded-full bg-primary'
                          style={{ width: `${(100 * n) / maximo}%` }}
                        />
                      </div>
                      <span className='text-end text-muted-foreground tabular-nums'>
                        {n}
                      </span>
                    </div>
                  ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Siguiente paso</CardTitle>
              <CardDescription>
                Etiqueta {OBJETIVO} puestos como top o no top. Con eso se mide
                si la puntuación automática de la Fase 4 piensa como tú.
              </CardDescription>
            </CardHeader>
            <CardContent className='flex flex-wrap gap-2'>
              <Button asChild>
                <Link to='/etiquetar'>
                  <Tags /> Etiquetar
                </Link>
              </Button>
              <Button asChild variant='outline'>
                <Link to='/puestos' search={{ dias: 1 }}>
                  Ver lo nuevo
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </Main>
    </>
  )
}

function Kpi({
  titulo,
  valor,
  detalle,
  icono: Icono,
}: {
  titulo: string
  valor?: number | string
  detalle?: string | false
  icono: React.ElementType
}) {
  return (
    <Card className='gap-2'>
      <CardHeader className='flex flex-row items-center justify-between'>
        <CardTitle className='text-sm font-medium'>{titulo}</CardTitle>
        <Icono className='size-4 text-muted-foreground' />
      </CardHeader>
      <CardContent>
        {valor === undefined ? (
          <Skeleton className='h-8 w-16' />
        ) : (
          <div className='text-2xl font-bold tabular-nums'>{valor}</div>
        )}
        <p className='text-xs text-muted-foreground'>{detalle || ' '}</p>
      </CardContent>
    </Card>
  )
}
