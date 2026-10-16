import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Preferencias } from '@/api'
import { Plus, Quote, Save, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  perfilGuardarPreferenciasMutation,
  perfilLeerPreferenciasOptions,
  perfilPerfilOptions,
} from '@/api/@tanstack/react-query.gen'
import { MODALIDADES } from '@/lib/formato'
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
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Cabecera } from '@/components/layout/cabecera'
import { Main } from '@/components/layout/main'
import { ListaEditable } from '@/components/lista-editable'

type Competencia = {
  nombre: string
  categoria: string
  nivel: string
  anos?: number | null
  evidencias: string[]
}
type PerfilCV = {
  meta: {
    cv?: string
    extraido_en?: string
    aprobado?: boolean
    citas_no_verificadas?: string[]
  }
  perfil: {
    nombre: string
    titular: string
    resumen: string
    anos_experiencia?: number
    competencias: Competencia[]
    experiencias: {
      empresa: string
      puesto: string
      inicio: string
      fin?: string | null
      resumen: string
    }[]
    idiomas: { idioma: string; nivel: string }[]
  }
}

const CATEGORIAS: Record<string, string> = {
  ia_llm: 'IA y LLM',
  lenguaje: 'Lenguajes',
  framework: 'Frameworks',
  datos: 'Datos',
  cloud_devops: 'Cloud y DevOps',
  arquitectura: 'Arquitectura',
  dominio: 'Dominio',
  metodologia: 'Metodología',
  herramienta: 'Herramientas',
  blanda: 'Habilidades',
}
const NIVEL: Record<string, string> = {
  experto: 'Experto',
  avanzado: 'Avanzado',
  intermedio: 'Intermedio',
  basico: 'Básico',
}

export function Perfil() {
  return (
    <>
      <Cabecera />
      <Main className='flex flex-col gap-6'>
        <div>
          <h2 className='text-2xl font-bold tracking-tight'>Perfil</h2>
          <p className='text-muted-foreground'>
            Lo que sale de tu CV y lo que buscas: con esto se buscan y se
            puntúan los puestos.
          </p>
        </div>
        <Tabs defaultValue='preferencias'>
          <TabsList>
            <TabsTrigger value='preferencias'>Preferencias</TabsTrigger>
            <TabsTrigger value='cv'>Del CV</TabsTrigger>
          </TabsList>
          <TabsContent value='preferencias'>
            <EditorPreferencias />
          </TabsContent>
          <TabsContent value='cv'>
            <PerfilDelCV />
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}

function PerfilDelCV() {
  const { data, isLoading } = useQuery(perfilPerfilOptions())
  if (isLoading || !data) return <Skeleton className='h-96' />
  const { perfil: p, meta } = data as unknown as PerfilCV
  const grupos = Object.entries(CATEGORIAS)
    .map(
      ([c, nombre]) =>
        [nombre, p.competencias.filter((x) => x.categoria === c)] as const
    )
    .filter(([, l]) => l.length)

  return (
    <div className='flex flex-col gap-4'>
      <Card>
        <CardHeader>
          <CardTitle>
            {p.nombre} · {p.titular}
          </CardTitle>
          <CardDescription>
            {meta.aprobado ? 'Aprobado' : 'Pendiente de aprobar'} · extraído el{' '}
            {meta.extraido_en?.slice(0, 10)} ·{' '}
            {meta.citas_no_verificadas?.length
              ? `${meta.citas_no_verificadas.length} citas sin verificar`
              : 'todas las citas verificadas en el CV'}
          </CardDescription>
        </CardHeader>
        <CardContent className='text-sm leading-relaxed'>
          {p.resumen}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Competencias ({p.competencias.length})</CardTitle>
          <CardDescription>
            Toca una para ver las frases del CV que la demuestran.
          </CardDescription>
        </CardHeader>
        <CardContent className='flex flex-col gap-4'>
          {grupos.map(([nombre, lista]) => (
            <div key={nombre} className='flex flex-col gap-2'>
              <span className='text-sm font-medium text-muted-foreground'>
                {nombre}
              </span>
              <div className='flex flex-wrap gap-1.5'>
                {lista.map((c) => (
                  <Popover key={c.nombre}>
                    <PopoverTrigger asChild>
                      <button type='button'>
                        <Badge
                          variant={
                            c.nivel === 'experto' || c.nivel === 'avanzado'
                              ? 'default'
                              : 'secondary'
                          }
                          className='cursor-pointer font-normal'
                        >
                          {c.nombre}
                          {c.anos ? ` · ${c.anos} a` : ''}
                        </Badge>
                      </button>
                    </PopoverTrigger>
                    <PopoverContent className='w-80 text-sm'>
                      <div className='mb-2 font-medium'>
                        {c.nombre} · {NIVEL[c.nivel] ?? c.nivel}
                      </div>
                      <ul className='flex flex-col gap-2'>
                        {c.evidencias.map((e) => (
                          <li
                            key={e}
                            className='flex gap-2 text-muted-foreground'
                          >
                            <Quote className='size-3 shrink-0' /> {e}
                          </li>
                        ))}
                      </ul>
                    </PopoverContent>
                  </Popover>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Experiencia</CardTitle>
        </CardHeader>
        <CardContent className='flex flex-col gap-4'>
          {p.experiencias.map((x) => (
            <div
              key={`${x.empresa}${x.inicio}`}
              className='flex flex-col gap-1'
            >
              <div className='font-medium'>
                {x.puesto} · {x.empresa}
              </div>
              <div className='text-xs text-muted-foreground'>
                {x.inicio} – {x.fin ?? 'actualidad'}
              </div>
              <p className='text-sm leading-relaxed text-muted-foreground'>
                {x.resumen}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

function EditorPreferencias() {
  const { data } = useQuery(perfilLeerPreferenciasOptions())
  if (!data) return <Skeleton className='h-96' />
  return <Formulario key={JSON.stringify(data)} data={data} />
}

function Formulario({ data }: { data: Preferencias }) {
  const qc = useQueryClient()
  const [p, setP] = useState<Preferencias>(() => structuredClone(data))
  const guardar = useMutation({
    ...perfilGuardarPreferenciasMutation(),
    onSuccess: () => {
      toast.success(
        'Preferencias guardadas. Las búsquedas cambian en la próxima ingesta.'
      )
      qc.invalidateQueries()
    },
  })

  const set = (cambios: Partial<Preferencias>) => setP({ ...p, ...cambios })
  const roles = p.roles
  const terminos = roles.terminos ?? {}
  const ingles = p.idiomas?.ingles ?? {
    nivel: 'B2' as const,
    efecto: 'marcar' as const,
  }
  const cambiado = JSON.stringify(p) !== JSON.stringify(data)

  return (
    <div className='flex flex-col gap-4'>
      <Card>
        <CardHeader>
          <CardTitle>Dónde</CardTitle>
          <CardDescription>
            Ciudades en las que trabajarías en persona, y si aceptas remoto.
          </CardDescription>
        </CardHeader>
        <CardContent className='flex flex-col gap-4'>
          {(p.ubicaciones ?? []).map((u, i) => (
            <div key={i} className='flex flex-wrap items-center gap-3'>
              <Input
                value={u.ciudad}
                className='h-9 w-40'
                onChange={(e) =>
                  set({
                    ubicaciones: p.ubicaciones!.map((x, j) =>
                      j === i ? { ...x, ciudad: e.target.value } : x
                    ),
                  })
                }
              />
              <Input
                value={u.pais}
                className='h-9 w-16 uppercase'
                maxLength={2}
                onChange={(e) =>
                  set({
                    ubicaciones: p.ubicaciones!.map((x, j) =>
                      j === i ? { ...x, pais: e.target.value.toUpperCase() } : x
                    ),
                  })
                }
              />
              {(['presencial', 'hibrido'] as const).map((m) => (
                <Label
                  key={m}
                  className='flex items-center gap-1.5 font-normal'
                >
                  <Checkbox
                    checked={u.modalidades?.includes(m)}
                    onCheckedChange={(c) =>
                      set({
                        ubicaciones: p.ubicaciones!.map((x, j) =>
                          j === i
                            ? {
                                ...x,
                                modalidades: c
                                  ? [...(x.modalidades ?? []), m]
                                  : (x.modalidades ?? []).filter(
                                      (y) => y !== m
                                    ),
                              }
                            : x
                        ),
                      })
                    }
                  />
                  {MODALIDADES[m]}
                </Label>
              ))}
              <Button
                variant='ghost'
                size='icon'
                aria-label='Quitar ubicación'
                onClick={() =>
                  set({ ubicaciones: p.ubicaciones!.filter((_, j) => j !== i) })
                }
              >
                <Trash2 />
              </Button>
            </div>
          ))}
          <Button
            variant='outline'
            size='sm'
            className='w-fit'
            onClick={() =>
              set({
                ubicaciones: [
                  ...(p.ubicaciones ?? []),
                  {
                    ciudad: '',
                    pais: 'ES',
                    modalidades: ['presencial', 'hibrido'],
                  },
                ],
              })
            }
          >
            <Plus /> Añadir ciudad
          </Button>
          <div className='flex flex-col gap-3 rounded-lg border p-3'>
            <Label className='flex items-center justify-between font-normal'>
              Acepto remoto
              <Switch
                checked={p.remoto?.acepta ?? false}
                onCheckedChange={(c) =>
                  set({ remoto: { desde_pais: 'ES', ...p.remoto, acepta: c } })
                }
              />
            </Label>
            {p.remoto?.acepta && (
              <>
                <Label className='flex items-center justify-between font-normal'>
                  Con empresa española
                  <Switch
                    checked={p.remoto.empresa_local ?? true}
                    onCheckedChange={(c) =>
                      set({ remoto: { ...p.remoto!, empresa_local: c } })
                    }
                  />
                </Label>
                <Label className='flex items-center justify-between font-normal'>
                  Con empresa extranjera que contrate en España
                  <Switch
                    checked={p.remoto.empresa_extranjera ?? true}
                    onCheckedChange={(c) =>
                      set({ remoto: { ...p.remoto!, empresa_extranjera: c } })
                    }
                  />
                </Label>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Qué</CardTitle>
          <CardDescription>
            Los roles orientan la puntuación; los términos son las palabras con
            las que se busca en cada fuente.
          </CardDescription>
        </CardHeader>
        <CardContent className='grid gap-5 md:grid-cols-2'>
          <Campo titulo='Roles principales'>
            <ListaEditable
              valores={roles.principales}
              onChange={(v) => set({ roles: { ...roles, principales: v } })}
            />
          </Campo>
          <Campo titulo='Roles secundarios'>
            <ListaEditable
              valores={roles.secundarios ?? []}
              onChange={(v) => set({ roles: { ...roles, secundarios: v } })}
            />
          </Campo>
          <Campo
            titulo='Términos principales'
            ayuda='Se buscan en todas partes, también en remoto.'
          >
            <ListaEditable
              valores={terminos.principales ?? []}
              onChange={(v) =>
                set({
                  roles: {
                    ...roles,
                    terminos: { ...terminos, principales: v },
                  },
                })
              }
            />
          </Campo>
          <Campo
            titulo='Términos amplios'
            ayuda='Solo en tus ciudades, donde hay menos volumen.'
          >
            <ListaEditable
              valores={terminos.amplios ?? []}
              onChange={(v) =>
                set({
                  roles: { ...roles, terminos: { ...terminos, amplios: v } },
                })
              }
            />
          </Campo>
          <Campo
            titulo='Descartar si aparece'
            ayuda='Términos que eliminan un puesto.'
          >
            <ListaEditable
              valores={roles.excluir ?? []}
              onChange={(v) => set({ roles: { ...roles, excluir: v } })}
            />
          </Campo>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Inglés y avisos</CardTitle>
        </CardHeader>
        <CardContent className='grid gap-5 md:grid-cols-2'>
          <Campo
            titulo='Tu nivel de inglés'
            ayuda='Si un puesto pide más: marcarlo o descartarlo.'
          >
            <div className='flex gap-2'>
              <Select
                value={ingles.nivel}
                onValueChange={(v) =>
                  set({
                    idiomas: {
                      ...p.idiomas,
                      ingles: { ...ingles, nivel: v as typeof ingles.nivel },
                    },
                  })
                }
              >
                <SelectTrigger className='w-28'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {['A2', 'B1', 'B2', 'C1', 'C2', 'nativo'].map((n) => (
                    <SelectItem key={n} value={n}>
                      {n}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={ingles.efecto ?? 'marcar'}
                onValueChange={(v) =>
                  set({
                    idiomas: {
                      ...p.idiomas,
                      ingles: { ...ingles, efecto: v as 'marcar' | 'excluir' },
                    },
                  })
                }
              >
                <SelectTrigger className='w-32'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='marcar'>Marcar</SelectItem>
                  <SelectItem value='excluir'>Descartar</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </Campo>
          <Campo
            titulo='Aviso inmediato desde'
            ayuda='Puntuación (0–100) para avisar al momento; el resto va al resumen.'
          >
            <div className='flex gap-2'>
              <Input
                type='number'
                min={0}
                max={100}
                className='w-24'
                value={p.avisos?.inmediato_desde ?? 85}
                onChange={(e) =>
                  set({
                    avisos: {
                      ...p.avisos,
                      inmediato_desde: Number(e.target.value),
                    },
                  })
                }
              />
              <Select
                value={p.avisos?.resumen ?? 'semanal'}
                onValueChange={(v) =>
                  set({
                    avisos: { ...p.avisos, resumen: v as 'diario' | 'semanal' },
                  })
                }
              >
                <SelectTrigger className='w-44'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='diario'>Resumen diario</SelectItem>
                  <SelectItem value='semanal'>Resumen semanal</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </Campo>
        </CardContent>
      </Card>

      <div className='sticky bottom-3 flex justify-end gap-2'>
        {cambiado && (
          <Button variant='outline' onClick={() => setP(structuredClone(data))}>
            Descartar
          </Button>
        )}
        <Button
          disabled={!cambiado || guardar.isPending}
          onClick={() => guardar.mutate({ body: p })}
          className='shadow-md'
        >
          <Save /> Guardar
        </Button>
      </div>
    </div>
  )
}

function Campo({
  titulo,
  ayuda,
  children,
}: {
  titulo: string
  ayuda?: string
  children: React.ReactNode
}) {
  return (
    <div className='flex flex-col gap-2'>
      <div>
        <div className='text-sm font-medium'>{titulo}</div>
        {ayuda && <div className='text-xs text-muted-foreground'>{ayuda}</div>}
      </div>
      {children}
    </div>
  )
}
