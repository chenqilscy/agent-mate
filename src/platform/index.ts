// Platform abstraction (decision A.1). The UI always calls through this facade;
// it never imports Tauri APIs directly. M0–M4 use the web no-op implementation;
// M5 adds index.tauri.ts wiring these to real window/tray/notification IPC, and
// the swap is a build-time alias — zero UI changes.

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

// Web implementation: browser can't drive the OS window/tray, so these are
// deliberate no-ops. Notifications use the Web Notifications API when granted.
export const platform: Platform = {
  windowControls: {
    minimize() {},
    toggleMaximize() {},
    close() {},
  },
  tray: {
    setBadge() {},
  },
  notify(title, body) {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted') {
      new Notification(title, { body })
    }
  },
  globalShortcut: {
    register() {},
    unregister() {},
  },
  fileDialog: {
    async openDirectory() {
      return null
    },
  },
  isDesktop: false,
}
