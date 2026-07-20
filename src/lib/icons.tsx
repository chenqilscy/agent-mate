// Reusable SVG icons migrated from the prototype. One-off icons stay inlined in
// their view; these are the ones used across the shell and composer.
import type { SVGProps } from 'react'

type P = SVGProps<SVGSVGElement>
const stroke = (props: P) => ({
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  ...props,
})

export const IcPlus = (p: P) => (
  <svg {...stroke(p)}><path d="M12 5v14M5 12h14" /></svg>
)
export const IcClose = (p: P) => (
  <svg {...stroke(p)}><path d="M6 6l12 12M18 6L6 18" /></svg>
)
export const IcSend = (p: P) => (
  <svg {...stroke({ strokeWidth: 2.2, ...p })}><path d="M12 19V5M6 11l6-6 6 6" /></svg>
)
export const IcChevronDown = (p: P) => (
  <svg {...stroke({ strokeWidth: 2.5, ...p })}><path d="M6 9l6 6 6-6" /></svg>
)
export const IcChevronRight = (p: P) => (
  <svg {...stroke({ strokeWidth: 2.4, ...p })}><path d="M9 6l6 6-6 6" /></svg>
)
export const IcSearch = (p: P) => (
  <svg {...stroke(p)}><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
)
export const IcMic = (p: P) => (
  <svg {...stroke(p)}><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" /></svg>
)
export const IcShield = (p: P) => (
  <svg {...stroke(p)}><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
)
export const IcBell = (p: P) => (
  <svg {...stroke(p)}><path d="M6 9a6 6 0 1112 0c0 5 2 7 2 7H4s2-2 2-7z" /><path d="M10 21h4" /></svg>
)
export const IcCompass = (p: P) => (
  <svg {...stroke(p)}><circle cx="12" cy="12" r="9" /><path d="M15 9l-2 5-5 2 2-5z" /></svg>
)
export const IcFolder = (p: P) => (
  <svg {...stroke(p)}><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
)
export const IcPanel = (p: P) => (
  <svg {...stroke(p)}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M15 4v16" /></svg>
)
export const IcShare = (p: P) => (
  <svg {...stroke(p)}><path d="M14 5h5v5M19 5l-8 8" /><path d="M10 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-3" /></svg>
)
export const IcHistory = (p: P) => (
  <svg {...stroke(p)}><path d="M3 12a9 9 0 109-9 9 9 0 00-7 3M3 3v4h4" /><path d="M12 8v4l3 2" /></svg>
)
export const IcSpark = (p: P) => (
  <svg {...stroke(p)}><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg>
)
export const IcLink = (p: P) => (
  <svg {...stroke(p)}><path d="M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2" /></svg>
)
export const IcCopy = (p: P) => (
  <svg {...stroke(p)}><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg>
)
export const IcGear = (p: P) => (
  <svg {...stroke(p)}><path d="M12 8a4 4 0 100 8 4 4 0 000-8z" /><path d="M19 12a7 7 0 00-.1-1.2l2-1.6-2-3.4-2.4 1a7 7 0 00-2-1.2l-.4-2.6H9.9l-.4 2.6a7 7 0 00-2 1.2l-2.4-1-2 3.4 2 1.6a7 7 0 000 2.4l-2 1.6 2 3.4 2.4-1a7 7 0 002 1.2l.4 2.6h4.2l.4-2.6a7 7 0 002-1.2l2.4 1 2-3.4-2-1.6c.06-.4.1-.8.1-1.2z" /></svg>
)

// Brand cat logo (the AgentMate mascot), used as bot avatar & app icon.
export const CatLogo = (p: P) => (
  <svg viewBox="0 0 40 40" aria-hidden="true" {...p}>
    <rect x="4" y="6" width="32" height="30" rx="9" fill="#16B37A" />
    <path d="M11 12l4 5h10l4-5" fill="none" stroke="#0E8A5F" strokeWidth="2.4" strokeLinecap="round" />
    <circle cx="15.5" cy="24" r="2.4" fill="#eafff6" />
    <circle cx="24.5" cy="24" r="2.4" fill="#eafff6" />
  </svg>
)
