import { createFileRoute } from '@tanstack/react-router'
import { Puntuacion } from '@/features/puntuacion'

export const Route = createFileRoute('/_app/puntuacion')({
  component: Puntuacion,
})
