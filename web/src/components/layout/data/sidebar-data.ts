import {
  Activity,
  Bookmark,
  Gauge,
  BriefcaseBusiness,
  LayoutDashboard,
  Tags,
  UserRound,
} from 'lucide-react'
import { type SidebarData } from '../types'

// Una entrada por pantalla. Cada fase añade la suya (avisos, empresas, candidaturas…).
export const sidebarData: SidebarData = {
  navGroups: [
    {
      title: 'Radar',
      items: [
        { title: 'Inicio', url: '/', icon: LayoutDashboard },
        { title: 'Puestos', url: '/puestos', icon: BriefcaseBusiness },
        { title: 'Mi lista', url: '/lista', icon: Bookmark },
        { title: 'Etiquetar', url: '/etiquetar', icon: Tags },
        { title: 'Puntuación', url: '/puntuacion', icon: Gauge },
      ],
    },
    {
      title: 'Sistema',
      items: [
        { title: 'Fuentes', url: '/fuentes', icon: Activity },
        { title: 'Perfil', url: '/perfil', icon: UserRound },
      ],
    },
  ],
}
