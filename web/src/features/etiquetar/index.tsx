import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { PartyPopper, SkipForward } from 'lucide-react'
import {
  puestosFichaOptions,
  puestosListarOptions,
  sistemaResumenOptions,
} from '@/api/@tanstack/react-query.gen'
import { MODALIDADES, haceCuanto, lugar, salario } from '@/lib/formato'
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
import { BotonesEtiqueta } from '@/features/puestos/componentes/etiqueta'
import { Vias } from '@/features/puestos/componentes/vias'

/** Puestos que hay que etiquetar para poder medir la puntuación de la Fase 4. */
export const OBJETIVO = 30

export function Etiquetar() {
  const [saltados, setSaltados] = useState(0)
  const { data: resumen } = useQuery(sistemaResumenOptions())
  const { data: lista, isLoading } = useQuery(
    puestosListarOptions({
      query: {
        etiqueta: 'sin',
        orden: 'recientes',
        limite: 1,
        desde: saltados,
      },
    })
  )
  const siguiente = lista?.items[0]
  const { data: p } = useQuery({
    ...puestosFichaOptions({ path: { puesto_id: siguiente?.id ?? 0 } }),
    enabled: Boolean(siguiente),
  })
  const hechos = resumen?.etiquetados ?? 0
  const oferta =
    p &&
    (p.lista_ofertas.find((o) => o.id === p.fusion.descripcion?.oferta_id) ??
      p.lista_ofertas[0])
  const [entera, setEntera] = useState(false)

  return (
    <>
      <Cabecera />
      <Main className='mx-auto flex w-full max-w-3xl flex-col gap-4'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Etiquetar</h2>
          <p className='text-muted-foreground'>
            ¿Te presentarías? Con {OBJETIVO} etiquetas mediremos si la
            puntuación automática acierta.
          </p>
        </div>

        <div className='flex flex-col gap-1.5'>
          <div className='flex justify-between text-sm'>
            <span>
              {hechos} de {OBJETIVO}
            </span>
            <span className='text-muted-foreground'>
              {resumen?.etiquetados_top ?? 0} top
            </span>
          </div>
          <div className='h-2 overflow-hidden rounded-full bg-muted'>
            <div
              className='h-full rounded-full bg-primary transition-all'
              style={{ width: `${Math.min(100, (100 * hechos) / OBJETIVO)}%` }}
            />
          </div>
        </div>

        {isLoading && <Skeleton className='h-96' />}
        {lista && !siguiente && (
          <Card className='items-center py-12 text-center'>
            <PartyPopper className='size-10 text-primary' />
            <CardTitle>No queda nada sin etiquetar</CardTitle>
            <CardDescription>
              Vuelve cuando la ingesta traiga puestos nuevos.
            </CardDescription>
          </Card>
        )}
        {siguiente && (
          <Card>
            <CardHeader>
              <CardTitle className='text-xl leading-snug'>
                <Link
                  to='/puestos/$puestoId'
                  params={{ puestoId: String(siguiente.id) }}
                  className='hover:underline'
                >
                  {siguiente.titulo}
                </Link>
              </CardTitle>
              <CardDescription>
                {siguiente.empresa ?? 'Empresa sin indicar'}
              </CardDescription>
              <div className='flex flex-wrap gap-1.5 pt-1'>
                {[
                  lugar(siguiente.ciudad, siguiente.pais),
                  siguiente.modalidad && MODALIDADES[siguiente.modalidad],
                  salario(siguiente.salario),
                  `visto ${haceCuanto(siguiente.vista_primera)}`,
                ]
                  .filter(Boolean)
                  .map((d) => (
                    <Badge
                      key={d as string}
                      variant='secondary'
                      className='font-normal'
                    >
                      {d}
                    </Badge>
                  ))}
              </div>
              <div className='pt-1'>
                <Vias vias={siguiente.vias} />
              </div>
            </CardHeader>
            <CardContent className='flex flex-col gap-4'>
              {!oferta ? (
                <Skeleton className='h-48' />
              ) : (
                <button
                  type='button'
                  onClick={() => setEntera(!entera)}
                  className={cn(
                    'text-start text-sm leading-relaxed whitespace-pre-line text-muted-foreground',
                    !entera && 'line-clamp-[12]'
                  )}
                >
                  {oferta.descripcion ?? 'Sin descripción.'}
                </button>
              )}
              <div className='sticky bottom-2 flex flex-col gap-2 rounded-lg border bg-background/95 p-3 shadow-sm backdrop-blur'>
                <BotonesEtiqueta
                  key={siguiente.id}
                  puestoId={siguiente.id}
                  conMotivos
                  onEtiquetado={() => setEntera(false)}
                />
                <Button
                  variant='ghost'
                  size='sm'
                  className='self-end'
                  onClick={() => {
                    setSaltados(saltados + 1)
                    setEntera(false)
                  }}
                >
                  Saltar <SkipForward />
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </Main>
    </>
  )
}
