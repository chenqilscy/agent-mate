import { WbButton, WbInput, WbTextArea } from '../ui/Primitives'
import { useEffect, useRef, useState, type ChangeEvent, type MouseEvent as ReactMouseEvent } from 'react'
import { useSettingsStore } from '../../stores/settingsStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useChatStore } from '../../stores/chatStore'
import { toast } from '../../stores/toastStore'
import { Popover } from '../ui/Popover'
import { ModelPicker } from './ModelPicker'
import { PermPopover } from './PermPopover'
import { CtxPopover } from './CtxPopover'
import { PlusMenu, type PlusActions } from './PlusMenu'
import { PickerOverlay } from '../project/NewProjectModal'
import { RefPicker } from './RefPicker'
import { useCatalogStore } from '../../stores/catalogStore'
import { useKnowledgeStore } from '../../stores/knowledgeStore'
import { skillDisplayName, useSkillStore } from '../../stores/skillStore'
import { useVoiceInput } from './useVoiceInput'
import { IcPlus, IcClose, IcSend, IcChevronDown, IcMic, IcShield } from '../../lib/icons'
import { clickable } from '../../lib/a11y'

// Attach limits — kept in step with the backend ref caps in backend/agent/runtime.py
// (MAX_REF_BODY / MAX_REFS_TOTAL). EFFECTIVE_REF_LIMIT mirrors MAX_REF_BODY: the chars
// actually fed to the LLM per ref. A file longer than this is still attachable, but the
// chip flags it「已截断」so the user knows only the head is injected (WB-025). MAX_ATTACH
// is a hard payload guard so a single attach can't blow up memory/request size (WB-010).
const EFFECTIVE_REF_LIMIT = 1_000_000 // chars injected per ref (== backend MAX_REF_BODY)
const MAX_ATTACH = 4_000_000 // ~4 MB hard cap per attachment

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
  const [picker, setPicker] = useState<'exp' | 'skill' | 'conn' | 'kb' | null>(null)
  useSkillStore((s) => s.builtin)
  useSkillStore((s) => s.installed)
  const [refOpen, setRefOpen] = useState(false)
  const anchorRef = useRef<HTMLElement | null>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const model = useSettingsStore((s) => s.model)
  const models = useSettingsStore((s) => s.models)
  // 选择键 → 友好显示名（WB-128）：默认兜底/厂商模型/自定义；找不到时退回「默认」。
  const modelLabel = models.find((m) => m.key === model)?.name ?? '默认'
  const perm = useSettingsStore((s) => s.perm)
  const planMode = useSettingsStore((s) => s.planMode)
  const setPlan = useSettingsStore((s) => s.setPlan)

  const experts = useLoadoutStore((s) => s.experts)
  const skills = useLoadoutStore((s) => s.skills)
  const connectors = useLoadoutStore((s) => s.connectors)
  const knowledgeIds = useLoadoutStore((s) => s.knowledgeIds)
  const refs = useLoadoutStore((s) => s.refs)
  const toggleLoad = useLoadoutStore((s) => s.toggle)
  const kbs = useKnowledgeStore((s) => s.kbs)
  const kbName = (id: string) => kbs.find((k) => k.id === id)?.name ?? '知识库'
  const addRef = useLoadoutStore((s) => s.addRef)
  const removeRef = useLoadoutStore((s) => s.removeRef)

  const activeId = useChatStore((s) => s.activeId)
  const activeProjectId = useChatStore((s) => s.activeProjectId)
  const scope = activeProjectId ? { project: activeProjectId } : activeId ? { session: activeId } : {}

  const plusActions: PlusActions = {
    onPick: (kind) => setPicker(kind),
    onAddFile: () => fileRef.current?.click(),
    onRefFile: () => setRefOpen(true),
  }

  const onFileChosen = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // allow re-picking the same file
    if (!file) return
    if (file.size > MAX_ATTACH) { toast('文件过大（上限约 4MB 文本）'); return }
    try {
      const content = await file.text()
      if (!addRef({ name: file.name, content })) {
        toast('已添加过 · ' + file.name)
        return
      }
      toast(content.length > EFFECTIVE_REF_LIMIT
        ? `已添加 · ${file.name}（超 100 万字符，注入时会截断至前 100 万字符）`
        : '已添加 · ' + file.name)
    } catch {
      toast('读取失败')
    }
  }

  const iconOf = (kind: 'exp' | 'skill' | 'conn', name: string): string => {
    const cat = useCatalogStore.getState()
    if (kind === 'conn') return cat.NP_CONNS.find((c) => c[1] === name)?.[0] ?? '🔗'
    if (kind === 'exp') return cat.EXPERT_RECOMMENDATIONS.find((x) => x.slug === name || x.name === name)?.avatar
      ?? cat.NP_EXPERTS.find((x) => x[1] === name)?.[0] ?? '🧑'
    const label = skillDisplayName(name)
    return cat.SK_GRID.find((s) => s.name === label || s.slug === name)?.icon ?? '🧩'
  }

  const expertLabel = (key: string): string => {
    const cat = useCatalogStore.getState()
    return cat.EXPERT_RECOMMENDATIONS.find((x) => x.slug === key || x.name === key)?.name
      ?? cat.EXP_TEAMS.flatMap((team) => team.members).find((member) => member.expert_slug === key)?.name
      ?? key
  }

  const grow = () => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px'
  }

  // 语音输入（WB-139）：转写结果追加到当前文本（有内容则空格分隔），并撑高、聚焦。
  const voice = useVoiceInput((t) => {
    setText((cur) => (cur.trim() ? cur.replace(/\s*$/, '') + ' ' + t : t))
    requestAnimationFrame(grow)
    taRef.current?.focus()
  })

  // 一次性草稿：某处（如「编辑技能」）在跳转前塞了 draft，本 Composer 挂载即取走并清空。
  useEffect(() => {
    const d = useLoadoutStore.getState().draft
    if (d) {
      setText(d)
      useLoadoutStore.getState().clearDraft()
      requestAnimationFrame(grow)
    }
    // 仅在挂载时消费一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  const hasLoadout = experts.length + skills.length + connectors.length + knowledgeIds.length + refs.length > 0

  return (
    <div className="composer">
      {hasLoadout && (
        <div className="cloadout">
          {experts.map((n) => (
            <span className="np-chip" key={'e' + n} title={expertLabel(n)}><span>{iconOf('exp', n)}</span><span className="np-lbl">{expertLabel(n)}</span><span className="x" {...clickable} onClick={() => toggleLoad('exp', n)}>×</span></span>
          ))}
          {skills.map((n) => (
            <span className="np-chip" key={'s' + n} title={n}><span>{iconOf('skill', n)}</span><span className="np-lbl">{skillDisplayName(n)}</span><span className="x" {...clickable} onClick={() => toggleLoad('skill', n)}>×</span></span>
          ))}
          {connectors.map((n) => (
            <span className="np-chip" key={'c' + n} title={n}><span>{iconOf('conn', n)}</span><span className="np-lbl">{n}</span><span className="x" {...clickable} onClick={() => toggleLoad('conn', n)}>×</span></span>
          ))}
          {knowledgeIds.map((id) => (
            <span className="np-chip" key={'k' + id} title={kbName(id)}><span>📚</span><span className="np-lbl">{kbName(id)}</span><span className="x" {...clickable} onClick={() => toggleLoad('kb', id)}>×</span></span>
          ))}
          {refs.map((r) => {
            const truncated = r.content.length > EFFECTIVE_REF_LIMIT
            return (
              <span className={`np-chip ${r.kind === 'todo' ? 'ref-todo' : 'ref-file'}`} key={r.id} title={truncated ? `${r.name}（注入时截断至前 100 万字符）` : r.name}><span>{r.kind === 'todo' ? '🔖' : '📎'}</span><span className="np-lbl">{r.name}{truncated ? ' · 已截断' : ''}</span><span className="x" {...clickable} onClick={() => removeRef(r.id)}>×</span></span>
            )
          })}
        </div>
      )}
      <WbTextArea
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
      <WbInput ref={fileRef} type="file" hidden onChange={onFileChosen} />
      {picker && (
        <PickerOverlay
          kind={picker}
          sel={new Set(picker === 'exp' ? experts : picker === 'skill' ? skills : picker === 'kb' ? knowledgeIds : connectors)}
          onToggle={(n) => toggleLoad(picker, n)}
          onClose={() => setPicker(null)}
        />
      )}
      {refOpen && <RefPicker scope={scope} onClose={() => setRefOpen(false)} />}
      <div className="cbar">
        <WbButton className="cicon plusbtn" aria-label="添加" onClick={(e) => openPop('plusx', e)}>
          {pop === 'plusx' ? <IcClose /> : <IcPlus />}
        </WbButton>

        {variant === 'chat' && (
          <WbButton className="ctool" onClick={(e) => openPop('perm', e)}>
            <IcShield style={{ width: 14, height: 14 }} />
            <span className="perm-lb">{perm}</span>
            <IcChevronDown style={{ width: 10, height: 10 }} />
          </WbButton>
        )}

        {variant === 'chat' && (
          <WbButton
            className="ctool"
            style={planMode ? { borderColor: 'var(--brand)', color: 'var(--brand-600)' } : undefined}
            title="计划模式：只规划不执行，用提问卡与你确认关键决策"
            onClick={() => setPlan(!planMode)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 13, height: 13 }}><rect x="6" y="4" width="12" height="16" rx="2" /><path d="M9 4h6M9 10h6M9 14h4" /></svg>
            {planMode ? 'Plan' : '执行'}
          </WbButton>
        )}

        <div className="sp" />

        {variant === 'chat' && (
          <WbButton className="cicon" aria-label="上下文用量" onClick={(e) => openPop('ctx', e)}>
            <span className="ringc" />
          </WbButton>
        )}

        <WbButton className="ctool model" onClick={(e) => openPop('model', e)}>
          <span className="mk">🐋</span>
          <span className="model-lb">{modelLabel}</span>
          <IcChevronDown style={{ width: 10, height: 10 }} />
        </WbButton>

        <WbButton
          className={`cicon mic${voice.state === 'recording' ? ' rec' : ''}${voice.state === 'transcribing' ? ' busy' : ''}`}
          aria-label={voice.state === 'recording' ? '松开结束录音' : '按住说话'}
          title={voice.available === false ? '语音输入不可用（后端未安装 faster-whisper）' : voice.state === 'transcribing' ? '转写中…' : '按住说话，松开转写'}
          disabled={voice.state === 'transcribing' || streaming}
          onPointerDown={(e) => { e.preventDefault(); voice.start() }}
          onPointerUp={voice.stop}
          onPointerLeave={voice.stop}
          onPointerCancel={voice.stop}
          onContextMenu={(e) => e.preventDefault()}
        >
          <IcMic />
        </WbButton>

        {streaming ? (
          <WbButton className="cstop" aria-label="停止" onClick={onStop}>
            <span className="sq" />
          </WbButton>
        ) : (
          <WbButton className="csend" aria-label="发送" disabled={!text.trim()} onClick={submit}>
            <IcSend />
          </WbButton>
        )}
      </div>

      <Popover open={pop === 'plusx'} anchor={anchorRef.current} dir="up" onClose={closePop} minWidth={168}>
        <PlusMenu onClose={closePop} actions={plusActions} />
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
