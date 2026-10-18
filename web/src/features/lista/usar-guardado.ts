import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { GuardadoEntrada } from '@/api'
import { toast } from 'sonner'
import {
  puestosGuardarMutation,
  puestosQuitarGuardadoMutation,
} from '@/api/@tanstack/react-query.gen'

/** Todo lo que pinta un puesto (lista, ficha, Mi lista, Inicio) se refresca al guardar. */
function useRefrescar() {
  const qc = useQueryClient()
  return () =>
    qc.invalidateQueries({
      predicate: (q) =>
        [
          'puestosListar',
          'puestosFicha',
          'listaMisEtiquetas',
          'sistemaResumen',
          'puntuacionAcuerdo',
        ].includes((q.queryKey[0] as { _id?: string })?._id ?? ''),
    })
}

export function useGuardar(puestoId: number) {
  const refrescar = useRefrescar()
  const guardar = useMutation({
    ...puestosGuardarMutation(),
    onSuccess: refrescar,
  })
  const quitar = useMutation({
    ...puestosQuitarGuardadoMutation(),
    onSuccess: () => {
      refrescar()
      toast.success('Quitado de Mi lista')
    },
  })
  return {
    guardar: (body: GuardadoEntrada) =>
      guardar.mutate({ path: { puesto_id: puestoId }, body }),
    quitar: () => quitar.mutate({ path: { puesto_id: puestoId } }),
    ocupado: guardar.isPending || quitar.isPending,
  }
}
