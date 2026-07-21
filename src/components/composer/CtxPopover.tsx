import { useSettingsStore } from '../../stores/settingsStore'
import { clickable } from '../../lib/a11y'

// Context-usage panel (spec 5.2 `usage` event). Numbers are real: fed by the
// backend's usage event after each turn (token accounting).
const COLORS: Record<string, string> = {
  系统提示词: '#16B37A',
  工具及子智能体: '#F0A020',
  对话消息: '#7C5CFC',
  连接器及MCP: '#12B5C9',
  技能: '#3D6BFF',
}

function fmt(n: number): string {
  if (n >= 1000) return '~' + (n / 1000).toFixed(1) + 'K'
  return '~' + n
}

export function CtxPopover({ onClose }: { onClose: () => void }) {
  const usage = useSettingsStore((s) => s.usage)
  const total = usage.total || 1_000_000
  const rows = Object.entries(usage.detail).filter(([, v]) => v > 0)

  return (
    <>
      <div className="ctx-h">
        上下文用量
        <span className="ctx-x" {...clickable} onClick={onClose}>×</span>
      </div>
      <div className="ctx-pct">
        {usage.pct.toFixed(1)}%
        <small>已使用 {(usage.used / 1000).toFixed(1)}K / {(total / 1000).toFixed(1)}K</small>
      </div>
      <div className="ctx-bar">
        {rows.map(([k, v]) => (
          <i key={k} style={{ background: COLORS[k] ?? '#999', width: `${(v / total) * 100}%` }} />
        ))}
      </div>
      {rows.length === 0 && <div className="ctx-row">暂无用量，发起一次对话后即有真实统计</div>}
      {rows.map(([k, v]) => (
        <div className="ctx-row" key={k}>
          <span className="dot" style={{ background: COLORS[k] ?? '#999' }} />
          {k}
          <span className="v">{fmt(v)}</span>
        </div>
      ))}
    </>
  )
}
