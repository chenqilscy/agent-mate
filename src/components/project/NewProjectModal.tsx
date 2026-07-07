import { useRef, useState } from 'react'
import { useCatalog, useCatalogStore } from '../../stores/catalogStore'
import { useProjectStore } from '../../stores/projectStore'
import { toast } from '../../stores/toastStore'
import { Popover } from '../ui/Popover'
import type { ProjectInfo } from '../../lib/types'

type Kind = 'conn' | 'exp' | 'skill'

function iconOf(kind: Kind, name: string): string {
  const cat = useCatalogStore.getState()
  if (kind === 'conn') return cat.NP_CONNS.find((c) => c[1] === name)?.[0] ?? '🔗'
  if (kind === 'exp') return cat.NP_EXPERTS.find((e) => e[1] === name)?.[0] ?? '🧑'
  return cat.SK_GRID.find((s) => s[1] === name)?.[0] ?? '🧩'
}

// The new-project flow (spec 4.2): name + instruction (with template presets) +
// connector / expert / skill pickers → POST /api/projects. Fully persisted.
export function NewProjectModal({ open, onClose, onCreated }: {
  open: boolean
  onClose: () => void
  onCreated: (p: ProjectInfo) => void
}) {
  const createProject = useProjectStore((s) => s.create)
  const [name, setName] = useState('')
  const [instruction, setInstruction] = useState('')
  const [tplLabel, setTplLabel] = useState('选择模板')
  const [sel, setSel] = useState<Record<Kind, Set<string>>>({ conn: new Set(), exp: new Set(), skill: new Set() })
  const [picker, setPicker] = useState<Kind | null>(null)
  const [tplOpen, setTplOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const tplRef = useRef<HTMLButtonElement>(null)
  const { NP_TPLS } = useCatalog()

  if (!open) return null

  const reset = () => {
    setName(''); setInstruction(''); setTplLabel('选择模板')
    setSel({ conn: new Set(), exp: new Set(), skill: new Set() })
  }
  const close = () => { reset(); onClose() }

  const applyTpl = (tplName: string) => {
    const t = NP_TPLS.find((v) => v[0] === tplName)
    if (!t) return
    setTplLabel(tplName)
    setInstruction(t[1])
    setSel({ conn: new Set(t[2]), exp: new Set(t[3]), skill: new Set() })
    setTplOpen(false)
  }

  const toggle = (kind: Kind, itemName: string) => {
    setSel((prev) => {
      const next = new Set(prev[kind])
      next.has(itemName) ? next.delete(itemName) : next.add(itemName)
      return { ...prev, [kind]: next }
    })
  }

  const removeChip = (kind: Kind, itemName: string) => {
    setSel((prev) => {
      const next = new Set(prev[kind])
      next.delete(itemName)
      return { ...prev, [kind]: next }
    })
  }

  const confirm = async () => {
    if (!name.trim() || busy) return
    setBusy(true)
    try {
      const p = await createProject({
        name: name.trim(),
        instruction,
        connectors: [...sel.conn],
        experts: [...sel.exp],
        skills: [...sel.skill],
      })
      toast('项目已创建 · ' + p.name)
      reset()
      onCreated(p)
    } catch {
      toast('创建失败')
    } finally {
      setBusy(false)
    }
  }

  const chipRow = (kind: Kind, label: string) => (
    <div className="np-row">
      <b>{label}</b><small>（可选）</small>
      <div className="np-chips">
        {[...sel[kind]].map((n) => (
          <span className="np-chip" key={n} title={n}>
            <span>{iconOf(kind, n)}</span><span className="np-lbl">{n}</span>
            <span className="x" onClick={() => removeChip(kind, n)}>×</span>
          </span>
        ))}
      </div>
      <button className="np-add" onClick={() => setPicker(kind)}>＋ 添加</button>
    </div>
  )

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) close() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="新建项目">
        <div className="np-h">新建项目<button className="np-x" onClick={close}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">项目名称</div>
          <input className="np-input" placeholder="请输入项目名称" value={name} onChange={(e) => setName(e.target.value)} autoFocus />

          <div className="np-lbl">
            指令
            <button ref={tplRef} className="np-tplbtn" onClick={() => setTplOpen((v) => !v)}>
              <span>{tplLabel}</span>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
            </button>
          </div>
          <textarea
            className="np-ta"
            placeholder="提供当前项目的背景信息和规范，让 WorkBuddy 的回复更精准、更符合要求。比如：项目目标、团队习惯、风格偏好、输出约束等"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />

          {chipRow('conn', '连接器')}
          {chipRow('exp', '专家')}
          {chipRow('skill', '技能')}
        </div>
        <div className="np-foot">
          <span className="np-hint">切换模版会覆盖当前编辑内容</span>
          <button className="btn-ghost" onClick={close}>取消</button>
          <button className="btn-dark" disabled={!name.trim() || busy} onClick={confirm}>确定</button>
        </div>
      </div>

      <Popover open={tplOpen} anchor={tplRef.current} dir="down" onClose={() => setTplOpen(false)} minWidth={172}>
        {NP_TPLS.map((t) => (
          <div className="pop-item" key={t[0]} onClick={() => applyTpl(t[0])}>{t[0]}</div>
        ))}
      </Popover>

      {picker && <PickerOverlay kind={picker} sel={sel[picker]} onToggle={(n) => toggle(picker, n)} onClose={() => setPicker(null)} />}
    </div>
  )
}

// Multi-select picker for connectors / experts / skills.
export function PickerOverlay({ kind, sel, onToggle, onClose }: {
  kind: 'conn' | 'exp' | 'skill'
  sel: Set<string>
  onToggle: (name: string) => void
  onClose: () => void
}) {
  const [q, setQ] = useState('')
  const { NP_CONNS, NP_EXPERTS, SK_GRID, READY_CONNECTORS, NEEDS_TOKEN_CONNECTORS } = useCatalog()
  const title = { conn: '添加连接器', exp: '选择专家', skill: '选择技能' }[kind]

  const match = (s: string) => s.toLowerCase().includes(q.trim().toLowerCase())

  return (
    <div className="np-overlay open" style={{ zIndex: 160 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={`np-modal pk-modal ${kind === 'exp' ? 'wide' : kind === 'skill' ? 'mid' : ''}`.trim()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="np-h">
          {title}
          <div className="search-box" style={{ marginLeft: 'auto', width: 220 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input placeholder="搜索…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <button className="np-x" onClick={onClose}>×</button>
        </div>
        <div className="np-body" style={{ paddingTop: 2 }}>
          {kind === 'conn' && (
            NP_CONNS.filter((c) => match(c[1]) || match(c[2])).map((c) => {
              const on = sel.has(c[1])
              const ready = READY_CONNECTORS.has(c[1])
              const needsToken = NEEDS_TOKEN_CONNECTORS.has(c[1])
              return (
                <div className={`pkc-row ${on ? 'sel' : ''}`.trim()} key={c[1]} onClick={() => onToggle(c[1])}>
                  <span className="pi">{c[0]}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="pn">
                      {c[1]}
                      {ready && <span className={`conn-tag ${needsToken ? 'tok' : 'rdy'}`}>{needsToken ? '需配置' : '内置'}</span>}
                    </div>
                    <div className="pd">{c[2]}</div>
                  </div>
                  <span className="ckc">{on ? '✓' : ''}</span>
                </div>
              )
            })
          )}
          {kind === 'exp' && (
            <div className="selgrid">
              {NP_EXPERTS.filter((e) => match(e[1]) || match(e[3])).map((e) => {
                const on = sel.has(e[1])
                return (
                  <div className={`selcard ecard ${on ? 'sel' : ''}`.trim()} key={e[1]} onClick={() => onToggle(e[1])}>
                    <div className="ec-h"><div className="ec-av">{e[0]}</div>
                      <div style={{ flex: 1, minWidth: 0 }}><div className="ec-n">{e[1]}</div><div className="ec-s">{e[2]}</div></div>
                    </div>
                    <div className="ec-d">{e[3]}</div>
                    <div className="ec-tags">{e[4].map((t) => <span className="ec-tag" key={t}>{t}</span>)}</div>
                  </div>
                )
              })}
            </div>
          )}
          {kind === 'skill' && (
            <div className="selgrid">
              {SK_GRID.filter((s) => match(s[1]) || match(s[2])).map((s) => {
                const on = sel.has(s[1])
                return (
                  <div className={`selcard ${on ? 'sel' : ''}`.trim()} key={s[1]} onClick={() => onToggle(s[1])}>
                    <div style={{ display: 'flex', gap: 11, alignItems: 'center' }}>
                      <div className="sc-ic">{s[0]}</div><div className="sc-n">{s[1]}</div>
                    </div>
                    <div className="sc-d" style={{ marginTop: 9 }}>{s[2]}</div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
        <div className="np-foot" style={{ justifyContent: 'flex-end', marginTop: 6 }}>
          <button className="btn-dark" onClick={onClose}>完成（{sel.size}）</button>
        </div>
      </div>
    </div>
  )
}
