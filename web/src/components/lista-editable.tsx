import { useState } from 'react'
import { X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'

/** Lista de textos cortos: Enter o coma para añadir, × para quitar. */
export function ListaEditable({
  valores,
  onChange,
  placeholder,
}: {
  valores: string[]
  onChange: (v: string[]) => void
  placeholder?: string
}) {
  const [texto, setTexto] = useState('')
  const anadir = () => {
    const nuevo = texto.trim().replace(/,$/, '')
    if (nuevo && !valores.includes(nuevo)) onChange([...valores, nuevo])
    setTexto('')
  }
  return (
    <div className='flex flex-col gap-2'>
      <div className='flex flex-wrap gap-1.5'>
        {valores.map((v) => (
          <Badge key={v} variant='secondary' className='gap-1 pe-1 font-normal'>
            {v}
            <button
              type='button'
              onClick={() => onChange(valores.filter((x) => x !== v))}
              className='rounded-full p-0.5 hover:bg-foreground/10'
              aria-label={`Quitar ${v}`}
            >
              <X className='size-3' />
            </button>
          </Badge>
        ))}
      </div>
      <Input
        value={texto}
        placeholder={placeholder ?? 'Añadir…'}
        className='h-8'
        onChange={(e) => setTexto(e.target.value)}
        onBlur={anadir}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            anadir()
          }
        }}
      />
    </div>
  )
}
