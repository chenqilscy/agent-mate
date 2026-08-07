import { serverApiBase } from './channels'

export async function openServerConsole(path = '/'): Promise<void> {
  const popup = window.open('about:blank', '_blank')
  try {
    const apiBase = await serverApiBase()
    const root = apiBase.replace(/\/api\/?$/, '')
    const target = new URL(path.replace(/^\//, ''), `${root}/`).toString()
    if (popup) {
      popup.opener = null
      popup.location.replace(target)
    } else {
      window.location.assign(target)
    }
  } catch (error) {
    popup?.close()
    throw error
  }
}
