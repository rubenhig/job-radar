import type { Salario } from '@/api'

/** Etiquetas en español de los vocabularios del sistema. */
export const MODALIDADES: Record<string, string> = {
  presencial: 'Presencial',
  hibrido: 'Híbrido',
  remoto: 'Remoto',
}

export const CONTRATOS: Record<string, string> = {
  tiempo_completo: 'Jornada completa',
  tiempo_parcial: 'Jornada parcial',
  temporal: 'Temporal',
  practicas: 'Prácticas',
  autonomo: 'Autónomo',
}

export const FUENTES: Record<string, string> = {
  freehire: 'freehire',
  infojobs: 'InfoJobs',
  linkedin: 'LinkedIn',
  indeed: 'Indeed',
  ats: 'ATS',
}

const PERIODOS: Record<string, string> = {
  hora: '/h',
  dia: '/día',
  semana: '/sem',
  mes: '/mes',
  ano: '/año',
}

const miles = (n: number) =>
  n >= 1000 ? `${Math.round(n / 1000)}k` : String(Math.round(n))

export function salario(s?: Salario | null): string | null {
  if (!s || (!s.salario_min && !s.salario_max)) return null
  const moneda = s.salario_moneda === 'EUR' ? '€' : (s.salario_moneda ?? '')
  const rango =
    s.salario_min && s.salario_max && s.salario_min !== s.salario_max
      ? `${miles(s.salario_min)}–${miles(s.salario_max)}`
      : `${s.salario_min ? 'desde ' : 'hasta '}${miles((s.salario_min ?? s.salario_max)!)}`
  return `${rango} ${moneda}${PERIODOS[s.salario_periodo ?? ''] ?? ''}`.trim()
}

/** "hace 3 h", "hace 2 días", "15 oct". */
export function haceCuanto(iso?: string | null): string {
  if (!iso) return '—'
  const fecha = new Date(iso)
  const horas = (Date.now() - fecha.getTime()) / 36e5
  if (horas < 1) return 'hace un momento'
  if (horas < 24) return `hace ${Math.floor(horas)} h`
  if (horas < 48) return 'ayer'
  if (horas < 24 * 7) return `hace ${Math.floor(horas / 24)} días`
  return fecha.toLocaleDateString('es-ES', { day: 'numeric', month: 'short' })
}

export function lugar(
  ciudad?: string | null,
  pais?: string | null
): string | null {
  return (
    [ciudad, pais && pais !== 'ES' ? pais : null].filter(Boolean).join(', ') ||
    null
  )
}
