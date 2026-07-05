import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'

interface PopoverProps {
  open: boolean
  anchor: HTMLElement | null
  dir?: 'up' | 'down'
  onClose: () => void
  className?: string
  minWidth?: number
  children: ReactNode
}

// Lightweight floating popover anchored to a trigger element. Positions above
// (default, for composer bars) or below the anchor, clamped to the viewport.
// Replaces the prototype's hand-rolled buildPop/openSubAt positioning.
export function Popover({ open, anchor, dir = 'up', onClose, className = '', minWidth, children }: PopoverProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ left: number; top?: number; bottom?: number }>({ left: -9999 })

  useLayoutEffect(() => {
    if (!open || !anchor || !ref.current) return
    const r = anchor.getBoundingClientRect()
    const w = ref.current.offsetWidth
    const left = Math.max(8, Math.min(r.left, window.innerWidth - w - 12))
    if (dir === 'down') setPos({ left, top: r.bottom + 8 })
    else setPos({ left, bottom: window.innerHeight - r.top + 8 })
  }, [open, anchor, dir, children])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (ref.current?.contains(t)) return
      if (anchor?.contains(t)) return
      onClose()
    }
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onEsc)
    }
  }, [open, anchor, onClose])

  if (!open) return null
  return (
    <div
      ref={ref}
      className={`pop open ${className}`.trim()}
      role="menu"
      style={{ left: pos.left, top: pos.top, bottom: pos.bottom, minWidth }}
    >
      {children}
    </div>
  )
}
