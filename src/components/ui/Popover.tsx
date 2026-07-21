import { Popover as AntPopover } from 'antd'
import { useEffect, useLayoutEffect, useState, type ReactNode } from 'react'

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
  const [rect, setRect] = useState<DOMRect | null>(null)

  useLayoutEffect(() => {
    if (!open || !anchor) return
    const update = () => setRect(anchor.getBoundingClientRect())
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [open, anchor])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if ((t as HTMLElement).closest?.('.wb-ant-popover')) return
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

  if (!open || !anchor || !rect) return null
  return (
    <AntPopover
      open
      arrow={false}
      placement={dir === 'down' ? 'bottomLeft' : 'topLeft'}
      trigger={[]}
      onOpenChange={(next) => { if (!next) onClose() }}
      getPopupContainer={() => document.body}
      rootClassName="wb-ant-popover"
      content={(
        <div className={`pop open ${className}`.trim()} role="menu" style={{ minWidth }}>
          {children}
        </div>
      )}
    >
      <span
        aria-hidden="true"
        className="wb-ant-popover-anchor"
        style={{
          position: 'fixed',
          left: rect.left,
          top: dir === 'down' ? rect.bottom : rect.top,
          width: Math.max(1, rect.width),
          height: 1,
          pointerEvents: 'none',
        }}
      />
    </AntPopover>
  )
}
