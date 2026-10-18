import z from 'zod'
import { createFileRoute } from '@tanstack/react-router'
import { MiLista } from '@/features/lista'

const filtros = z.object({
  vista: z.enum(['tablero', 'tabla']).optional().catch(undefined),
  etiqueta: z.string().optional().catch(undefined),
  descartados: z.boolean().optional().catch(undefined),
})

export const Route = createFileRoute('/_app/lista')({
  validateSearch: filtros,
  component: MiLista,
})
