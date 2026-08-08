import { serverConsoleBase } from './channels'

export async function openServerConsole(path = '/'): Promise<void> {
  const popup = window.open('about:blank', '_blank')
  try {
    const root = await serverConsoleBase()
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
