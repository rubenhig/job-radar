import { createFileRoute } from '@tanstack/react-router'
import { FichaEmpresa } from '@/features/empresas/ficha'

export const Route = createFileRoute('/_app/empresas/$empresaId')({
  component: FichaEmpresa,
})
