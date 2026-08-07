// Platform abstraction (decision A.1). The UI always calls through this facade;
// it never imports Tauri APIs directly. In the browser these are no-ops; inside
// the Tauri desktop shell (A1) the window controls drive the real OS window over
// IPC. Detection is at runtime (Tauri 2 injects `__TAURI_INTERNALS__`), so a
// single bundle works both as the web app and inside the shell.
import { getCurrentWindow } from '@tauri-apps/api/window'

export type UpdateResult = {
  status: 'latest' | 'available' | 'updating' | 'unsupported'
  current_version?: string
  version?: string | null
  notes?: string | null
  release_id?: string | null
  rollback?: boolean
  forced?: boolean
}

export type UpdateOptions = {
  endpoint: string
  channel: 'stable' | 'beta'
  deviceId: string
  install?: boolean
}

export type LocalAgentStatus = {
  service: 'local-agent-core'
  protocol_version: number
  server_configured: boolean
  server_api_url: string
  transport: {
    identities: number
    leases: { total: number; active: number }
    wal: { count: number; bytes: number; oldest_at: number }
    errors: Array<{ run_id: string; error: string }>
    working_copies: Partial<Record<'local-only' | 'uploading' | 'committed', number>>
  }
  workers: unknown
}

export type LocalAgentWorkingCopy = {
  id: string
  owner_id: string
  asset_id: string
  project_id: string
  run_id: string
  relative_path: string
  source_kind: 'workspace' | 'external'
  state: 'local-only' | 'uploading' | 'committed'
  size: number
  sha256: string
  upload_id: string
  object_version_id: string
}

export type CommitAssetOptions = {
  ownerId: string
  localPath: string
  projectId?: string
  sessionId?: string
  runId?: string
  kind?: string
  external?: boolean
  explicitExternalUpload?: boolean
}

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
  // Auto-update (A4): check the release endpoint; if newer, download+install and
  // relaunch (never returns in that case). Throws on network/endpoint failure.
  checkForUpdates(options: UpdateOptions): Promise<UpdateResult>
  localAgent: {
    status(): Promise<LocalAgentStatus | null>
    commitAsset(options: CommitAssetOptions): Promise<LocalAgentWorkingCopy | null>
    downloadAsset(assetId: string, options: { ownerId: string; relativePath: string; projectId?: string }): Promise<LocalAgentWorkingCopy | null>
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
  async checkForUpdates() { return { status: 'unsupported' } },
  localAgent: { async status() { return null }, async commitAsset() { return null }, async downloadAsset() { return null } },
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
  async checkForUpdates(options) {
    const { invoke } = await import('@tauri-apps/api/core')
    return invoke<UpdateResult>('check_desktop_update', {
      endpoint: options.endpoint,
      channel: options.channel,
      deviceId: options.deviceId,
      install: Boolean(options.install),
    })
  },
  localAgent: {
    async status() {
      const { invoke } = await import('@tauri-apps/api/core')
      return invoke<LocalAgentStatus>('local_agent_status')
    },
    async commitAsset(options) {
      const { invoke } = await import('@tauri-apps/api/core')
      const result = await invoke<{ working_copy: LocalAgentWorkingCopy }>('local_agent_commit_asset', {
        body: {
          owner_id: options.ownerId,
          local_path: options.localPath,
          project_id: options.projectId ?? '',
          session_id: options.sessionId ?? '',
          run_id: options.runId ?? '',
          kind: options.kind ?? 'asset',
          external: Boolean(options.external),
          explicit_external_upload: Boolean(options.explicitExternalUpload),
        },
      })
      return result.working_copy
    },
    async downloadAsset(assetId, options) {
      const { invoke } = await import('@tauri-apps/api/core')
      const result = await invoke<{ working_copy: LocalAgentWorkingCopy }>('local_agent_download_asset', {
        assetId,
        body: {
          owner_id: options.ownerId,
          relative_path: options.relativePath,
          project_id: options.projectId ?? '',
        },
      })
      return result.working_copy
    },
  },
  isDesktop: true,
}

export const platform: Platform = isTauri ? tauriPlatform : webPlatform
