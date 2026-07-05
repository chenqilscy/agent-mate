import { useState } from 'react'
import { toast } from '../../stores/toastStore'
import { useSettingsStore } from '../../stores/settingsStore'
import { useLoadoutStore } from '../../stores/loadoutStore'

// The ＋ menu (spec 4.2). All items are now live:
//  · 添加文件 / 引用对话中的文件 → attach file content to the next message (M1/M3)
//  · 模式 → Plan (M4) / Ask (仅问答) toggles
//  · 专家 / 技能 / 连接器 → open a picker; picks apply to this session (M5)
export interface PlusActions {
  onPick: (kind: 'exp' | 'skill' | 'conn') => void
  onAddFile: () => void
  onRefFile: () => void
}

const ICON = {
  file: 'M21 12.5l-8.5 8.5a5 5 0 01-7-7l9-9a3.5 3.5 0 015 5l-9 9a2 2 0 01-3-3l8-8',
  ref: 'M16 8v5a3 3 0 006 0v-1a10 10 0 10-3.9 7.9',
  mode: 'M4 7h16M4 12h10M4 17h7',
  expert: 'M12 8a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6',
  skillx: 'M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z',
  connx: 'M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2',
}

function Item({ path, label, count, onClick }: { path: string; label: string; count?: number; onClick: () => void }) {
  return (
    <div className="pop-item px-root" onClick={onClick}>
      <span className="pi-ic">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={path} /></svg>
      </span>
      {label}
      {count ? <span className="px-count">{count}</span> : null}
      <span className="arr">›</span>
    </div>
  )
}

export function PlusMenu({ onClose, actions }: { onClose: () => void; actions: PlusActions }) {
  const [modeOpen, setModeOpen] = useState(false)
  const planMode = useSettingsStore((s) => s.planMode)
  const askMode = useSettingsStore((s) => s.askMode)
  const setPlan = useSettingsStore((s) => s.setPlan)
  const setAsk = useSettingsStore((s) => s.setAsk)
  const experts = useLoadoutStore((s) => s.experts)
  const skills = useLoadoutStore((s) => s.skills)
  const connectors = useLoadoutStore((s) => s.connectors)

  const modeLabel = planMode || askMode
    ? `（${planMode ? 'Plan' : ''}${planMode && askMode ? '·' : ''}${askMode ? 'Ask' : ''}）`
    : ''

  return (
    <>
      <Item path={ICON.file} label="添加文件" onClick={() => { actions.onAddFile(); onClose() }} />
      <Item path={ICON.ref} label="引用对话中的文件" onClick={() => { actions.onRefFile(); onClose() }} />

      <div>
        <div className={`pop-item px-root ${modeOpen ? 'on' : ''}`.trim()} onClick={() => setModeOpen((v) => !v)}>
          <span className="pi-ic">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={ICON.mode} /></svg>
          </span>
          模式{modeLabel}
          <span className="arr">{modeOpen ? '▾' : '›'}</span>
        </div>
        {modeOpen && (
          <>
            <div className="mode-row">计划 <small>Plan</small>
              <span className={`sw ${planMode ? 'on' : ''}`.trim()} onClick={(e) => { e.stopPropagation(); setPlan(!planMode); toast('计划模式已' + (!planMode ? '开启' : '关闭')) }} />
            </div>
            <div className="mode-row">仅问答 <small>Ask</small>
              <span className={`sw ${askMode ? 'on' : ''}`.trim()} onClick={(e) => { e.stopPropagation(); setAsk(!askMode); toast('仅问答已' + (!askMode ? '开启' : '关闭')) }} />
            </div>
          </>
        )}
      </div>

      <Item path={ICON.expert} label="专家" count={experts.length} onClick={() => { actions.onPick('exp'); onClose() }} />
      <Item path={ICON.skillx} label="技能" count={skills.length} onClick={() => { actions.onPick('skill'); onClose() }} />
      <Item path={ICON.connx} label="连接器" count={connectors.length} onClick={() => { actions.onPick('conn'); onClose() }} />
    </>
  )
}
