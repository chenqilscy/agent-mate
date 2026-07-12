import type { ReactNode } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'
import type { ModelOption } from '../../lib/types'

// Model menu (WB-128). Flat list from GET /api/models → settingsStore: a 默认(.env)
// backstop, built-in provider models (grouped by vendor, only those with a key), and
// free-form custom models. Selecting persists the entry's `key` via setModel.
// 「配置模型」opens the manager modal (survives this popover closing) via onConfigure.
export function ModelPicker({ onClose, onConfigure }: { onClose: () => void; onConfigure: () => void }) {
  const models = useSettingsStore((s) => s.models)
  const current = useSettingsStore((s) => s.model)

  const setModel = useSettingsStore((s) => s.setModel)

  const pick = (m: ModelOption) => {
    setModel(m.key)
    toast('已切换模型 · ' + m.name)
    onClose()
  }

  const row = (m: ModelOption) => {
    const sel = m.key === current
    return (
      <div className="mrow" key={m.key || 'default'} onClick={() => pick(m)}>
        <span className="mi" style={m.color ? { background: m.color, color: '#fff' } : undefined}>{m.icon}</span>
        <span className="mname">{m.name}</span>
        {sel && <span className="chk">✓</span>}
      </div>
    )
  }

  const def = models.find((m) => m.group === 'default')
  const providers = models.filter((m) => m.group === 'provider')
  const custom = models.filter((m) => m.group === 'custom')

  // provider rows grouped by vendor (header per providerName)
  const provSections: ReactNode[] = []
  let lastProv = ''
  for (const m of providers) {
    if (m.providerName && m.providerName !== lastProv) {
      lastProv = m.providerName
      provSections.push(<div className="pop-h" key={'h-' + m.provider}>{m.providerName}</div>)
    }
    provSections.push(row(m))
  }

  return (
    <>
      {def && row(def)}
      {providers.length === 0 && custom.length === 0 && (
        <div className="mpick-empty">还没有配置可用模型。点下方「配置模型」，给某个厂商填 API Key 即可启用。</div>
      )}
      {provSections}
      {custom.length > 0 && <div className="pop-h">自定义模型</div>}
      {custom.map(row)}
      <div className="pop-div" />
      <div className="pop-item" onClick={onConfigure}>
        <span className="pi-ic">⚙️</span>配置模型
      </div>
    </>
  )
}
