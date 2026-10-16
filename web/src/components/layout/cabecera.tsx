import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'

/** La cabecera común: buscador de pantallas (⌘K), tema y apariencia. */
export function Cabecera() {
  return (
    <Header fixed>
      <Search className='me-auto' />
      <ThemeSwitch />
      <ConfigDrawer />
    </Header>
  )
}
