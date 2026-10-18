import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import type { Pedido, Tarea } from '@/api'
import { CheckCircle2, Loader2, Play, Search, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import {
  tareasBuscarMutation,
  tareasListarOptions,
} from '@/api/@tanstack/react-query.gen'
import { FUENTES, haceCuanto } from '@/lib/formato'
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
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Cabecera } from '@/components/layout/cabecera'
import { Main } from '@/components/layout/main'
import { ListaEditable } from '@/components/lista-editable'

/** Qué cuesta o arriesga cada fuente: las de pago o delicadas se eligen a propósito. */
const NOTA_FUENTE: Record<string, string> = {
  freehire: 'gratis',
  indeed: 'gratis',
  linkedin: 'de pago: ~0,10 $ por búsqueda en una ciudad, hasta ~1 $ en remoto',
  infojobs: 'se bloquea si se le pide mucho (máx. ~4 al día)',
}
const PAISES: Record<string, string> = {
  ES: 'España',
  PT: 'Portugal',
  FR: 'Francia',
  DE: 'Alemania',
  IT: 'Italia',
  IE: 'Irlanda',
  NL: 'Países Bajos',
  GB: 'Reino Unido',
  US: 'Estados Unidos',
  AE: 'Emiratos',
  SA: 'Arabia Saudí',
  QA: 'Catar',
}

export function Buscar() {
  const qc = useQueryClient()
  const { data: tareas } = useQuery({
    ...tareasListarOptions(),
    // mientras haya una en marcha, se mira el progreso cada 2 s
    refetchInterval: (q) =>
      q.state.data?.some(
        (t) => t.estado === 'en_cola' || t.estado === 'en_curso'
      )
        ? 2000
        : false,
  })
  const enMarcha = tareas?.some(
    (t) => t.estado === 'en_cola' || t.estado === 'en_curso'
  )
  const lanzar = useMutation({
    ...tareasBuscarMutation(),
    onSuccess: () => {
      toast.success('Búsqueda lanzada')
      qc.invalidateQueries({
        predicate: (q) =>
          (q.queryKey[0] as { _id?: string })?._id === 'tareasListar',
      })
    },
  })
  const enviar = (body: Pedido) => lanzar.mutate({ body })

  return (
    <>
      <Cabecera />
      <Main className='mx-auto flex w-full max-w-4xl flex-col gap-6'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Buscar</h2>
          <p className='text-muted-foreground'>
            Lanza una búsqueda ya, sin esperar a la de cada mañana. Lo que
            encuentre se agrupa, se criba y se puntúa como siempre.
          </p>
        </div>

        <Tabs defaultValue='habitual'>
          <TabsList>
            <TabsTrigger value='habitual'>Buscar ahora</TabsTrigger>
            <TabsTrigger value='puntual'>Búsqueda puntual</TabsTrigger>
          </TabsList>
          <TabsContent value='habitual'>
            <Habitual
              ocupado={lanzar.isPending || Boolean(enMarcha)}
              onEnviar={enviar}
            />
          </TabsContent>
          <TabsContent value='puntual'>
            <Puntual
              ocupado={lanzar.isPending || Boolean(enMarcha)}
              onEnviar={enviar}
            />
          </TabsContent>
        </Tabs>

        <div className='flex flex-col gap-3'>
          <h3 className='text-lg font-semibold'>Últimas búsquedas</h3>
          {tareas && !tareas.length && (
            <p className='text-sm text-muted-foreground'>
              Aún no has lanzado ninguna.
            </p>
          )}
          {tareas?.map((t) => (
            <TarjetaTarea key={t.id} tarea={t} />
          ))}
        </div>
      </Main>
    </>
  )
}

function Fuentes({
  valores,
  onChange,
  sin = [],
}: {
  valores: string[]
  onChange: (v: string[]) => void
  sin?: string[]
}) {
  return (
    <div className='flex flex-col gap-2'>
      <span className='text-sm font-medium'>Fuentes</span>
      {Object.keys(NOTA_FUENTE).map((f) => {
        const fuera = sin.includes(f)
        return (
          <Label
            key={f}
            className={cn(
              'flex items-start gap-2 font-normal',
              fuera && 'opacity-50'
            )}
          >
            <Checkbox
              checked={valores.includes(f)}
              disabled={fuera}
              onCheckedChange={(c) =>
                onChange(c ? [...valores, f] : valores.filter((x) => x !== f))
              }
            />
            <span>
              {FUENTES[f]}{' '}
              <span className='text-muted-foreground'>
                · {fuera ? 'no busca por términos' : NOTA_FUENTE[f]}
              </span>
            </span>
          </Label>
        )
      })}
    </div>
  )
}

function Puntuar({
  valor,
  onChange,
}: {
  valor: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <Label className='flex items-center justify-between gap-2 font-normal'>
      Puntuar lo nuevo al terminar (con tu suscripción de Claude)
      <Switch checked={valor} onCheckedChange={onChange} />
    </Label>
  )
}

function Habitual({
  ocupado,
  onEnviar,
}: {
  ocupado: boolean
  onEnviar: (p: Pedido) => void
}) {
  const [fuentes, setFuentes] = useState(['freehire', 'indeed'])
  const [puntuar, setPuntuar] = useState(true)
  return (
    <Card>
      <CardHeader>
        <CardTitle>Las búsquedas de siempre, ahora</CardTitle>
        <CardDescription>
          Las de tus preferencias (Perfil): tus ciudades, el remoto y sus
          términos. Cada fuente pide desde la última vez que buscó.
        </CardDescription>
      </CardHeader>
      <CardContent className='flex flex-col gap-4'>
        <Fuentes valores={fuentes} onChange={setFuentes} />
        <Puntuar valor={puntuar} onChange={setPuntuar} />
        <Button
          className='w-fit'
          disabled={ocupado || !fuentes.length}
          onClick={() => onEnviar({ modo: 'habitual', fuentes, puntuar })}
        >
          <Play /> Buscar ahora
        </Button>
      </CardContent>
    </Card>
  )
}

function Puntual({
  ocupado,
  onEnviar,
}: {
  ocupado: boolean
  onEnviar: (p: Pedido) => void
}) {
  const [terminos, setTerminos] = useState<string[]>([])
  const [remoto, setRemoto] = useState(false)
  const [ciudad, setCiudad] = useState('')
  const [pais, setPais] = useState('ES')
  const [fuentes, setFuentes] = useState(['freehire', 'indeed'])
  const [puntuar, setPuntuar] = useState(true)
  const listo =
    terminos.length > 0 && (remoto || ciudad.trim()) && fuentes.length
  return (
    <Card>
      <CardHeader>
        <CardTitle>Tus términos, tu lugar</CardTitle>
        <CardDescription>
          Mira la última semana sin tocar tus preferencias. La nota sigue usando
          tu perfil: un presencial fuera de tus ciudades saldrá vetado por
          modalidad.
        </CardDescription>
      </CardHeader>
      <CardContent className='flex flex-col gap-4'>
        <div className='flex flex-col gap-1.5'>
          <span className='text-sm font-medium'>Términos</span>
          <ListaEditable
            valores={terminos}
            onChange={setTerminos}
            placeholder='p. ej. LLM Engineer (Enter)'
          />
        </div>
        <div className='flex flex-wrap items-end gap-3'>
          <Label className='flex items-center gap-2 font-normal'>
            <Switch checked={remoto} onCheckedChange={setRemoto} /> En remoto
          </Label>
          {!remoto && (
            <Input
              aria-label='Ciudad'
              value={ciudad}
              onChange={(e) => setCiudad(e.target.value)}
              placeholder='Ciudad (p. ej. Barcelona)'
              className='h-9 w-56'
            />
          )}
          <Select value={pais} onValueChange={setPais}>
            <SelectTrigger aria-label='País' className='h-9 w-44'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(PAISES).map(([k, v]) => (
                <SelectItem key={k} value={k}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Fuentes
          valores={fuentes.filter((f) => f !== 'infojobs')}
          onChange={setFuentes}
          sin={['infojobs']}
        />
        <Puntuar valor={puntuar} onChange={setPuntuar} />
        <Button
          className='w-fit'
          disabled={ocupado || !listo}
          onClick={() =>
            onEnviar({
              modo: 'puntual',
              terminos,
              remoto,
              ciudad: remoto ? null : ciudad.trim(),
              pais,
              fuentes: fuentes.filter((f) => f !== 'infojobs'),
              puntuar,
            })
          }
        >
          <Search /> Buscar
        </Button>
      </CardContent>
    </Card>
  )
}

function descripcion(t: Tarea) {
  const p = t.parametros as Partial<Pedido>
  const fuentes = (p.fuentes ?? []).map((f) => FUENTES[f] ?? f).join(', ')
  if (p.modo === 'puntual')
    return `«${(p.terminos ?? []).join(', ')}» · ${p.remoto ? `remoto (${p.pais})` : p.ciudad} · ${fuentes}`
  return `Las de siempre · ${fuentes}`
}

function TarjetaTarea({ tarea: t }: { tarea: Tarea }) {
  const enMarcha = t.estado === 'en_cola' || t.estado === 'en_curso'
  const r = t.resumen as
    { recibidas?: number; nuevas?: number; puestos?: number } | null | undefined
  return (
    <Card className='gap-2 py-4'>
      <CardContent className='flex flex-col gap-2 px-4'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <div className='flex items-center gap-2'>
            {enMarcha ? (
              <Loader2 className='size-4 animate-spin text-sky-600' />
            ) : t.estado === 'ok' ? (
              <CheckCircle2 className='size-4 text-emerald-600' />
            ) : (
              <XCircle className='size-4 text-destructive' />
            )}
            <span className='font-medium'>{descripcion(t)}</span>
          </div>
          <span className='text-xs text-muted-foreground'>
            {haceCuanto(t.creada_en)}
          </span>
        </div>
        {enMarcha && (
          <div className='flex flex-wrap gap-1.5'>
            {t.estado === 'en_cola' && (
              <Badge variant='secondary'>Arrancando…</Badge>
            )}
            {(t.ejecuciones ?? []).map((e) => (
              <Badge
                key={e.busqueda_id}
                variant='outline'
                className='font-normal'
              >
                {FUENTES[e.fuente_id] ?? e.fuente_id}: {e.recibidos}
                {e.estado === 'en_curso' ? '…' : ''}
              </Badge>
            ))}
            {t.estado === 'en_curso' && (
              <Badge variant='secondary'>
                después: agrupar, cribar y puntuar
              </Badge>
            )}
          </div>
        )}
        {t.error && <p className='text-sm text-destructive'>{t.error}</p>}
        {t.estado === 'ok' && r && (
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <span className='text-sm text-muted-foreground'>
              {r.recibidas ?? 0} ofertas ({r.nuevas ?? 0} nuevas) en{' '}
              {r.puestos ?? 0} puestos
            </span>
            <Button asChild size='sm' variant='outline'>
              <Link to='/puestos' search={{ tarea: t.id, orden: 'nota' }}>
                Ver resultados
              </Link>
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
