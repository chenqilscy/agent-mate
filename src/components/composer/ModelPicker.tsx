import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

// Model menu content (spec 4.2). List comes from GET /api/models → settingsStore;
// selecting persists to localStorage via setModel. 「配置自定义模型」opens the manager
// modal (WB-124) via onConfigure so it survives this popover closing.
export function ModelPicker({ onClose, onConfigure }: { onClose: () => void; onConfigure: () => void }) {
  const models = useSettingsStore((s) => s.models)
  const current = useSettingsStore((s) => s.model)
  const setModel = useSettingsStore((s) => s.setModel)
  const maxMode = useSettingsStore((s) => s.maxMode)
  const toggleMax = useSettingsStore((s) => s.toggleMax)

  const builtin = models.filter((m) => m.group === 'builtin')
  const custom = models.filter((m) => m.group === 'custom')

  const row = (m: (typeof models)[number]) => {
    const sel = m.name === current
    const hi = m.off || (m.level === 'High' && m.name !== 'Auto')
    return (
      <div
        className="mrow"
        key={m.name}
        onClick={() => {
          setModel(m.name)
          toast('已切换模型 · ' + m.name)
          onClose()
        }}
      >
        <span className="mi" style={m.color ? { background: m.color, color: '#fff' } : undefined}>{m.icon}</span>
        <span className="mname">{m.name}</span>
        {m.off && <span className="off">{m.off}</span>}
        {hi && <span className="tag">高</span>}
        <span className="mult">{m.mult}</span>
        {sel && <span className="chk">✓</span>}
      </div>
    )
  }

  return (
    <>
      <div className="max-row">
        Max 模式
        <span className={`sw ${maxMode ? 'on' : ''}`.trim()} onClick={(e) => { e.stopPropagation(); toggleMax(); toast('Max 模式已' + (!maxMode ? '开启' : '关闭')) }} />
      </div>
      {builtin.map(row)}
      {custom.length > 0 && <div className="pop-h">自定义模型</div>}
      {custom.map(row)}
      <div className="pop-div" />
      <div className="pop-item" onClick={onConfigure}>
        <span className="pi-ic">✏️</span>配置自定义模型
      </div>
    </>
  )
}
