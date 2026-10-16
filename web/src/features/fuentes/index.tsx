import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, CircleSlash, XCircle } from 'lucide-react'
import { sistemaFuentesOptions } from '@/api/@tanstack/react-query.gen'
import { FUENTES, haceCuanto } from '@/lib/formato'
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

const ESTADO = {
  ok: { icono: CheckCircle2, clase: 'text-emerald-600', texto: 'Bien' },
  parcial: { icono: AlertTriangle, clase: 'text-amber-600', texto: 'Parcial' },
  error: { icono: XCircle, clase: 'text-rose-600', texto: 'Error' },
} as const

export function Fuentes() {
  const { data, isLoading } = useQuery({
    ...sistemaFuentesOptions(),
    refetchInterval: 60_000,
  })
  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Fuentes</h2>
          <p className='text-muted-foreground'>
            Estado de cada fuente y avisos de salud: caídas, cambios de formato,
            cuota.
          </p>
        </div>

        {data && data.alertas.length > 0 && (
          <Card className='border-amber-500/40'>
            <CardHeader>
              <CardTitle className='flex items-center gap-2'>
                <AlertTriangle className='size-4 text-amber-600' /> Avisos
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul className='flex flex-col gap-2 text-sm'>
                {data.alertas.map((a, i) => (
                  <li key={i}>
                    <Badge variant='outline' className='me-2'>
                      {FUENTES[a.fuente] ?? a.fuente} · {a.senal}
                    </Badge>
                    <span className='break-words text-muted-foreground'>
                      {a.mensaje}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}

        <div className='grid gap-4 md:grid-cols-2'>
          {isLoading &&
            [...Array(4)].map((_, i) => <Skeleton key={i} className='h-48' />)}
          {data?.fuentes.map((f) => {
            const e = ESTADO[f.ultimo_estado as keyof typeof ESTADO]
            const Icono = f.activa ? (e?.icono ?? CircleSlash) : CircleSlash
            return (
              <Card key={f.id}>
                <CardHeader>
                  <CardTitle className='flex items-center justify-between'>
                    {FUENTES[f.id] ?? f.id}
                    <span
                      className={`flex items-center gap-1 text-sm font-normal ${f.activa ? (e?.clase ?? '') : 'text-muted-foreground'}`}
                    >
                      <Icono className='size-4' />{' '}
                      {f.activa ? (e?.texto ?? 'Sin datos') : 'Pausada'}
                    </span>
                  </CardTitle>
                  <CardDescription className='font-mono text-xs'>
                    {f.conector}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <dl className='grid grid-cols-2 gap-y-1 text-sm'>
                    <dt className='text-muted-foreground'>Última ejecución</dt>
                    <dd>{haceCuanto(f.ultima_ejecucion)}</dd>
                    <dt className='text-muted-foreground'>
                      Recibidas (7 días)
                    </dt>
                    <dd className='tabular-nums'>{f.recibidas_7d}</dd>
                    <dt className='text-muted-foreground'>Nuevas (7 días)</dt>
                    <dd className='tabular-nums'>{f.nuevas_7d}</dd>
                    <dt className='text-muted-foreground'>
                      Oferta más reciente
                    </dt>
                    <dd>{haceCuanto(f.oferta_mas_reciente)}</dd>
                    {f.coste_mes_usd != null && (
                      <>
                        <dt className='text-muted-foreground'>Gasto del mes</dt>
                        <dd className='tabular-nums'>
                          {f.coste_mes_usd.toFixed(2)} $
                        </dd>
                      </>
                    )}
                    {cuota(f.cuota) && (
                      <>
                        <dt className='text-muted-foreground'>Cuota</dt>
                        <dd>{cuota(f.cuota)}</dd>
                      </>
                    )}
                  </dl>
                </CardContent>
              </Card>
            )
          })}
        </div>
      </Main>
    </>
  )
}

/** Cabeceras `<cosa>-remaining` y `<cosa>-limit` → "queda el 40 % de jobs". */
function cuota(c?: Record<string, unknown> | null): string | null {
  if (!c) return null
  const partes = Object.keys(c)
    .filter((k) => k.endsWith('-remaining'))
    .map((k) => {
      const base = k.slice(0, -'-remaining'.length)
      const limite = Number(c[`${base}-limit`])
      if (base === 'usd') return `${Number(c[k]).toFixed(2)} $ de ${limite} $`
      const pct = limite ? Math.round((100 * Number(c[k])) / limite) : null
      const nombre = base
        .replace('x-ratelimit-', '')
        .replace('rapid-free-plans-hard-limit', 'plan')
      return pct == null ? null : `${pct} % de ${nombre}`
    })
    .filter(Boolean)
  return partes.length ? `queda ${partes.join(', ')}` : null
}
