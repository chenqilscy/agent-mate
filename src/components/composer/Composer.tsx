import { useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'
import { Popover } from '../ui/Popover'
import { ModelPicker } from './ModelPicker'
import { PermPopover } from './PermPopover'
import { CtxPopover } from './CtxPopover'
import { PlusMenu } from './PlusMenu'
import { IcPlus, IcClose, IcSend, IcChevronDown, IcMic, IcShield } from '../../lib/icons'

interface ComposerProps {
  variant?: 'home' | 'chat'
  streaming?: boolean
  onSend: (text: string) => void
  onStop?: () => void
  placeholder?: string
  autoFocus?: boolean
}

type PopId = 'plusx' | 'model' | 'perm' | 'ctx' | null

const PLACEHOLDER = '今天帮你做些什么？  @ 引用对话文件，/ 调用技能与指令'

export function Composer({ variant = 'home', streaming = false, onSend, onStop, placeholder, autoFocus }: ComposerProps) {
  const [text, setText] = useState('')
  const [pop, setPop] = useState<PopId>(null)
  const anchorRef = useRef<HTMLElement | null>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const model = useSettingsStore((s) => s.model)
  const perm = useSettingsStore((s) => s.perm)
  const planMode = useSettingsStore((s) => s.planMode)
  const setPlan = useSettingsStore((s) => s.setPlan)

  const grow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
  }

  const submit = () => {
    const t = text.trim()
    if (!t || streaming) return
    onSend(t)
    setText('')
    requestAnimationFrame(() => { if (taRef.current) taRef.current.style.height = 'auto' })
  }

  const openPop = (id: Exclude<PopId, null>, e: ReactMouseEvent) => {
    e.stopPropagation()
    anchorRef.current = e.currentTarget as HTMLElement
    setPop((cur) => (cur === id ? null : id))
  }

  const closePop = () => setPop(null)

  return (
    <div className="composer">
      <textarea
        ref={taRef}
        rows={1}
        autoFocus={autoFocus}
        placeholder={placeholder ?? PLACEHOLDER}
        value={text}
        onChange={(e) => { setText(e.target.value); grow() }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
      />
      <div className="cbar">
        <button className="cicon plusbtn" aria-label="添加" onClick={(e) => openPop('plusx', e)}>
          {pop === 'plusx' ? <IcClose /> : <IcPlus />}
        </button>

        {variant === 'chat' && (
          <button className="ctool" onClick={(e) => openPop('perm', e)}>
            <IcShield style={{ width: 14, height: 14 }} />
            <span className="perm-lb">{perm}</span>
            <IcChevronDown style={{ width: 10, height: 10 }} />
          </button>
        )}

        {variant === 'chat' && (
          <button
            className="ctool"
            style={planMode ? { borderColor: 'var(--brand)', color: 'var(--brand-600)' } : undefined}
            title="计划模式：只规划不执行，用提问卡与你确认关键决策"
            onClick={() => setPlan(!planMode)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 13, height: 13 }}><rect x="6" y="4" width="12" height="16" rx="2" /><path d="M9 4h6M9 10h6M9 14h4" /></svg>
            {planMode ? 'Plan' : '执行'}
          </button>
        )}

        <div className="sp" />

        {variant === 'chat' && (
          <button className="cicon" aria-label="上下文用量" onClick={(e) => openPop('ctx', e)}>
            <span className="ringc" />
          </button>
        )}

        <button className="ctool model" onClick={(e) => openPop('model', e)}>
          <span className="mk">🐋</span>
          <span className="model-lb">{model}</span>
          <IcChevronDown style={{ width: 10, height: 10 }} />
        </button>

        <button className="cicon" aria-label="语音" onClick={() => toast('语音输入')}>
          <IcMic />
        </button>

        {streaming ? (
          <button className="cstop" aria-label="停止" onClick={onStop}>
            <span className="sq" />
          </button>
        ) : (
          <button className="csend" aria-label="发送" disabled={!text.trim()} onClick={submit}>
            <IcSend />
          </button>
        )}
      </div>

      <Popover open={pop === 'plusx'} anchor={anchorRef.current} dir="up" onClose={closePop} minWidth={168}>
        <PlusMenu onClose={closePop} />
      </Popover>
      <Popover open={pop === 'model'} anchor={anchorRef.current} dir="up" onClose={closePop} className="model">
        <ModelPicker onClose={closePop} />
      </Popover>
      <Popover open={pop === 'perm'} anchor={anchorRef.current} dir="up" onClose={closePop} className="perm-pop" minWidth={232}>
        <PermPopover />
      </Popover>
      <Popover open={pop === 'ctx'} anchor={anchorRef.current} dir="up" onClose={closePop} className="ctx-pop" minWidth={284}>
        <CtxPopover onClose={closePop} />
      </Popover>
    </div>
  )
}
