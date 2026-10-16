import { createFileRoute } from '@tanstack/react-router'
import { Etiquetar } from '@/features/etiquetar'

export const Route = createFileRoute('/_app/etiquetar')({
  component: Etiquetar,
})
