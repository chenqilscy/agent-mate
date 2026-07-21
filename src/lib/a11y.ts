// a11y helper for clickable non-button elements (WB-016).
//
// Much of the UI was migrated verbatim from the prototype as `<div onClick>`,
// which can't take keyboard focus, so the global :focus-visible ring never fires
// and keyboard/screen-reader users can't reach them. Spreading `activate(handler)`
// onto such a div makes it a proper button: focusable, and triggered by Enter/Space.
import type { KeyboardEvent } from 'react'

export function activate<E extends HTMLElement = HTMLElement>(handler: (e?: KeyboardEvent<E>) => void) {
  return {
    role: 'button' as const,
    tabIndex: 0,
    onKeyDown: (e: KeyboardEvent<E>) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        handler(e)
      }
    },
  }
}

// Compatibility props for elements that already have an onClick handler. The
// key handler delegates to the element's existing click path so call sites do
// not have to duplicate business logic while legacy prototype markup is being
// migrated to semantic Ant controls.
export const clickable = {
  role: 'button' as const,
  tabIndex: 0,
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      e.currentTarget.click()
    }
  },
}
