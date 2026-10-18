import z from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { Empresas } from '@/features/empresas'

const filtros = z.object({
  q: z.string().optional().catch(undefined),
  estado: z
    .enum(['todas', 'sin_revisar', 'seguida', 'pendiente', 'descartada'])
    .optional()
    .catch(undefined),
  consultoras: z.boolean().optional().catch(undefined),
  orden: z
    .enum(['nota', 'puestos', 'recientes', 'nombre'])
    .optional()
    .catch(undefined),
  pagina: z.number().int().positive().optional().catch(undefined),
})

export const Route = createFileRoute('/_app/empresas/')({
  validateSearch: filtros,
  component: Empresas,
})
