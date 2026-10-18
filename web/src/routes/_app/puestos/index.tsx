import z from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { Puestos } from '@/features/puestos'

// Los filtros viven en la URL: se pueden guardar, compartir y recargar.
const filtros = z.object({
  q: z.string().optional().catch(undefined),
  fuente: z.array(z.string()).optional().catch(undefined),
  modalidad: z.array(z.string()).optional().catch(undefined),
  etiqueta: z
    .enum(['todas', 'sin', 'top', 'no_top'])
    .optional()
    .catch(undefined),
  dias: z.number().int().positive().optional().catch(undefined),
  orden: z
    .enum(['recientes', 'publicadas', 'vias', 'nota'])
    .optional()
    .catch(undefined),
  nota: z
    .enum(['todas', 'destacados', 'top', 'sin'])
    .optional()
    .catch(undefined),
  descartados: z.boolean().optional().catch(undefined),
  nuevos: z.boolean().optional().catch(undefined),
  pagina: z.number().int().positive().optional().catch(undefined),
})

export const Route = createFileRoute('/_app/puestos/')({
  validateSearch: filtros,
  component: Puestos,
})
