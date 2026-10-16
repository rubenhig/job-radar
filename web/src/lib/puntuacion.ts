import type { Evaluacion } from '@/api'

/** Por encima de esto, aviso inmediato (Fase 5); entre esto y TOP, al resumen. */
export const DESTACADO = 75
export const TOP = 50

export function colorNota(nota: number, vetado = false) {
  if (vetado) return 'bg-muted text-muted-foreground'
  if (nota >= DESTACADO)
    return 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
  if (nota >= TOP) return 'bg-amber-500/15 text-amber-700 dark:text-amber-400'
  return 'bg-muted text-muted-foreground'
}

export const NOMBRES_CRITERIO: Record<string, string> = {
  modalidad: 'Modalidad',
  elegibilidad: 'Elegibilidad',
  idioma: 'Idioma',
  rol_ia: 'Encaje con IA',
  funcion: 'Función',
  seniority: 'Seniority',
  fuente: 'Quién publica',
  requisitos: 'Requisitos cubiertos',
}

export const VALORES: Record<string, string> = {
  pasa: 'Pasa',
  no_pasa: 'No pasa',
  marca: 'Ojo',
  sin_datos: 'No lo dice',
  ia_principal: 'Puesto de IA',
  software_con_ia: 'Software con IA',
  software_sin_ia: 'Software sin IA',
  ninguno: 'Nada',
  ingenieria: 'Ingeniería',
  tecnica_adyacente: 'Técnica adyacente',
  no_construye_software: 'No construye software',
  encaja: 'Encaja',
  reto: 'Un reto',
  por_debajo: 'Por debajo',
  muy_por_encima: 'Muy por encima',
  directa: 'La empresa',
  intermediario: 'Intermediario',
  dudosa: 'Dudosa',
  critico: 'Crítico',
  alto: 'Alto',
  deseable: 'Deseable',
  fuerte: 'Cubierto',
  parcial: 'En parte',
  falta: 'Falta',
  dicho: 'Lo dice',
  inferido: 'Inferido',
}

/** Trozos del texto que son citas de la evaluación, para resaltarlas. */
export function tramosCitados(
  texto: string,
  citas: string[]
): [number, number][] {
  const bajo = texto.toLowerCase()
  const tramos: [number, number][] = []
  for (const c of citas) {
    const i = bajo.indexOf(c.toLowerCase().trim())
    if (c.trim().length > 3 && i >= 0) tramos.push([i, i + c.trim().length])
  }
  tramos.sort((a, b) => a[0] - b[0])
  return tramos.reduce<[number, number][]>((acc, t) => {
    const ult = acc[acc.length - 1]
    if (ult && t[0] <= ult[1]) ult[1] = Math.max(ult[1], t[1])
    else acc.push([...t])
    return acc
  }, [])
}

export function citasDe(e?: Evaluacion | null): string[] {
  if (!e) return []
  return [
    ...Object.values(e.compuertas).map((c) => c.cita),
    ...Object.values(e.dimensiones).map((c) => c.cita),
    ...e.requisitos.filter((q) => q.origen === 'dicho').map((q) => q.requisito),
  ].filter((c): c is string => Boolean(c))
}
