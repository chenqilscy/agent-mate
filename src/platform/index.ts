// Platform abstraction (decision A.1). The UI always calls through this facade;
// it never imports Tauri APIs directly. In the browser these are no-ops; inside
// the Tauri desktop shell (A1) the window controls drive the real OS window over
// IPC. Detection is at runtime (Tauri 2 injects `__TAURI_INTERNALS__`), so a
// single bundle works both as the web app and inside the shell.
import { getCurrentWindow } from '@tauri-apps/api/window'

export interface Platform {
  windowControls: {
    minimize(): void
    toggleMaximize(): void
    close(): void
  }
  tray: {
    setBadge(count: number): void
  }
  notify(title: string, body?: string): void
  globalShortcut: {
    register(accelerator: string, handler: () => void): void
    unregister(accelerator: string): void
  }
  fileDialog: {
    openDirectory(): Promise<string | null>
  }
  isDesktop: boolean
}

const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window

function webNotify(title: string, body?: string): void {
  if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
    new Notification(title, { body })
  }
}

// Web implementation: the browser can't drive the OS window/tray, so these are
// deliberate no-ops. Notifications use the Web Notifications API when granted.
const webPlatform: Platform = {
  windowControls: { minimize() {}, toggleMaximize() {}, close() {} },
  tray: { setBadge() {} },
  notify: webNotify,
  globalShortcut: { register() {}, unregister() {} },
  fileDialog: { async openDirectory() { return null } },
  isDesktop: false,
}

// Tauri desktop shell (A1): real window controls over IPC. Tray / global
// shortcut / native dialog land in later phases (A2–A4); until then they reuse
// the web behaviour so the UI never breaks.
const tauriPlatform: Platform = {
  windowControls: {
    minimize() { void getCurrentWindow().minimize() },
    toggleMaximize() { void getCurrentWindow().toggleMaximize() },
    close() { void getCurrentWindow().close() },
  },
  tray: { setBadge() {} },
  notify: webNotify,
  globalShortcut: { register() {}, unregister() {} },
  fileDialog: { async openDirectory() { return null } },
  isDesktop: true,
}

export const platform: Platform = isTauri ? tauriPlatform : webPlatform
