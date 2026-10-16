import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { Check, X } from 'lucide-react'
import { puntuacionAcuerdoOptions } from '@/api/@tanstack/react-query.gen'
import { Badge } from '@/components/ui/badge'
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
import { Nota } from '@/features/puestos/componentes/nota'

const pct = (x?: number | null) =>
  x == null ? '—' : `${Math.round(x * 100)} %`

/** ¿Piensa la puntuación como tú? Sus notas frente a tus etiquetas. */
export function Puntuacion() {
  const { data: a, isLoading } = useQuery(puntuacionAcuerdoOptions())
  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Puntuación</h2>
          <p className='text-muted-foreground'>
            ¿Piensa como tú? Las notas de Claude frente a tus etiquetas (
            {a?.rubrica ?? '…'}).
          </p>
        </div>
        <div className='grid grid-cols-2 gap-4 lg:grid-cols-4'>
          <Cifra
            titulo='Acuerdo'
            valor={pct(a?.acuerdo)}
            detalle={a?.umbral != null ? `top desde ${a.umbral}` : ''}
          />
          <Cifra
            titulo='Dejando uno fuera'
            valor={pct(a?.dejando_uno_fuera)}
            detalle='la cifra honesta'
          />
          <Cifra
            titulo='κ de Cohen'
            valor={a?.kappa != null ? a.kappa.toFixed(2) : '—'}
            detalle='descontando el azar'
          />
          <Cifra
            titulo='Puestos'
            valor={a ? String(a.casos.length) : ''}
            detalle={a ? `${(a.coste_usd ?? 0).toFixed(2)} $ en API` : ''}
          />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Caso a caso</CardTitle>
            <CardDescription>
              De mayor a menor nota. ✗ = no coincide con tu etiqueta.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading && <Skeleton className='h-64' />}
            <ul className='flex flex-col divide-y'>
              {a?.casos.map((c) => (
                <li
                  key={c.puesto_id}
                  className='flex items-center gap-3 py-2.5'
                >
                  {c.acierto ? (
                    <Check className='size-4 shrink-0 text-emerald-600' />
                  ) : (
                    <X className='size-4 shrink-0 text-rose-600' />
                  )}
                  <Nota
                    valoracion={{
                      nota: c.nota,
                      vetado: c.vetado,
                      motivo_veto: c.explicacion,
                    }}
                  />
                  <div className='min-w-0 flex-1'>
                    <Link
                      to='/puestos/$puestoId'
                      params={{ puestoId: String(c.puesto_id) }}
                      className='block truncate text-sm font-medium hover:underline'
                    >
                      {c.titulo}
                    </Link>
                    <div className='truncate text-xs text-muted-foreground'>
                      {c.explicacion}
                    </div>
                  </div>
                  <Badge
                    variant={c.etiqueta === 'top' ? 'default' : 'outline'}
                    className='shrink-0'
                  >
                    {c.etiqueta === 'top' ? 'Tú: top' : 'Tú: no top'}
                  </Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}

function Cifra({
  titulo,
  valor,
  detalle,
}: {
  titulo: string
  valor: string
  detalle: string
}) {
  return (
    <Card className='gap-1'>
      <CardHeader>
        <CardTitle className='text-sm font-medium'>{titulo}</CardTitle>
      </CardHeader>
      <CardContent>
        {valor ? (
          <div className='text-2xl font-bold tabular-nums'>{valor}</div>
        ) : (
          <Skeleton className='h-8 w-16' />
        )}
        <p className='text-xs text-muted-foreground'>{detalle || ' '}</p>
      </CardContent>
    </Card>
  )
}
