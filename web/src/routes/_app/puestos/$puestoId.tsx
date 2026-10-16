import { createFileRoute } from '@tanstack/react-router'
import { FichaPuesto } from '@/features/puestos/ficha'

export const Route = createFileRoute('/_app/puestos/$puestoId')({
  component: FichaPuesto,
})
