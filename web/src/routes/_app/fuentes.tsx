import { createFileRoute } from '@tanstack/react-router'
import { Fuentes } from '@/features/fuentes'

export const Route = createFileRoute('/_app/fuentes')({
  component: Fuentes,
})
