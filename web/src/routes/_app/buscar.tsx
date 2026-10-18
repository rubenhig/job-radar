import { createFileRoute } from '@tanstack/react-router'
import { Buscar } from '@/features/buscar'

export const Route = createFileRoute('/_app/buscar')({
  component: Buscar,
})
