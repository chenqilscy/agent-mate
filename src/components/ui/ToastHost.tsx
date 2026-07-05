import { useToastStore } from '../../stores/toastStore'

export function ToastHost() {
  const { message, visible } = useToastStore()
  return (
    <div className={`toast ${visible ? 'show' : ''}`.trim()}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 12l5 5L20 6" /></svg>
      <span>{message}</span>
    </div>
  )
}
