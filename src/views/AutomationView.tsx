import { useEffect, useRef, useState } from 'react'
import { AUTO } from '../data/catalog'
import { useAutomationStore } from '../stores/automationStore'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { Popover } from '../components/ui/Popover'
import type { Automation, CreateAutomationInput, TriggerKind } from '../lib/types'

const IC_ADD = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
)

function iconOf(name: string): string {
  return AUTO.find((a) => a[1] === name)?.[0] ?? '⏰'
}

function triggerLabel(a: Automation): string {
  return a.trigger_kind === 'daily' ? `每天 ${a.at_time}` : `每 ${a.interval_min} 分钟`
}

export function AutomationView() {
  const items = useAutomationStore((s) => s.items)
  const load = useAutomationStore((s) => s.load)
  const toggle = useAutomationStore((s) => s.toggle)
  const remove = useAutomationStore((s) => s.remove)
  const runNow = useAutomationStore((s) => s.runNow)
  const openSession = useChatStore((s) => s.openSession)
  const setView = useUIStore((s) => s.setView)

  const [modal, setModal] = useState<{ prefill?: Partial<CreateAutomationInput> } | null>(null)
  const [menuId, setMenuId] = useState<string | null>(null)
  const menuAnchor = useRef<HTMLElement | null>(null)

  useEffect(() => { load() }, [load])

  const openRun = async (a: Automation) => {
    if (!a.last_session_id) { toast('尚未运行'); return }
    await openSession(a.last_session_id)
    setView('chat')
  }

  const doRun = async (a: Automation) => {
    setMenuId(null)
    toast('已触发运行 · ' + a.name)
    await runNow(a.id)
  }

  return (
    <section className="view active" data-view="automation">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>自动化</h1>
            <div className="sub">管理自动化任务并查看近期运行记录。到点由真实智能体执行并产出会话。</div>
          </div>
          <button className="btn-line" style={{ marginTop: 0 }} onClick={() => setModal({})}>
            {IC_ADD}新建
          </button>
        </div>

        {items.length > 0 && (
          <>
            <div className="sec-title">我的自动化（{items.length}）</div>
            <div className="card-grid g2">
              {items.map((a) => (
                <div className="auto-card" key={a.id}>
                  <div className="auto-h">
                    <span className="t-ic">{iconOf(a.name)}</span>
                    <div className="auto-tt">
                      <div className="auto-n">{a.name}</div>
                      <div className="auto-meta">
                        {triggerLabel(a)}
                        <span className="dot">·</span>
                        {a.enabled ? `下次 ${a.next_run_label}` : '已停用'}
                      </div>
                    </div>
                    <span
                      className={`sw ${a.enabled ? 'on' : ''}`.trim()}
                      role="switch"
                      aria-checked={a.enabled ? 'true' : 'false'}
                      aria-label={a.enabled ? '停用' : '启用'}
                      onClick={() => toggle(a.id, !a.enabled)}
                    />
                  </div>
                  <div className="auto-prompt">{a.prompt}</div>
                  <div className="auto-f">
                    {a.last_status === 'running' && <span className="auto-chip run"><i className="run-ic" />运行中</span>}
                    {a.last_status === 'ok' && <span className="auto-chip ok">上次成功 · {a.last_run_label}</span>}
                    {a.last_status === 'error' && <span className="auto-chip err">上次失败 · {a.last_run_label}</span>}
                    {!a.last_status && <span className="auto-chip">尚未运行</span>}
                    <button
                      className="auto-more"
                      aria-label="更多"
                      onClick={(e) => { menuAnchor.current = e.currentTarget; setMenuId(menuId === a.id ? null : a.id) }}
                    >
                      <svg viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /></svg>
                    </button>
                  </div>

                  <Popover open={menuId === a.id} anchor={menuAnchor.current} dir="down" onClose={() => setMenuId(null)} minWidth={140}>
                    <div className="pop-item" onClick={() => doRun(a)}>立即运行</div>
                    <div className="pop-item" onClick={() => { setMenuId(null); openRun(a) }}>打开上次运行</div>
                    <div className="pop-item danger" onClick={() => { setMenuId(null); remove(a.id); toast('已删除 · ' + a.name) }}>删除</div>
                  </Popover>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="sec-title">从模板入手</div>
        <div className="card-grid g3">
          {AUTO.map(([ic, n, d]) => (
            <div className="tpl" key={n} onClick={() => setModal({ prefill: { name: n, prompt: d } })}>
              <span className="t-ic">{ic}</span>
              <div>
                <div className="t-n">{n}</div>
                <div className="t-d">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {modal && <AutomationModal prefill={modal.prefill} onClose={() => setModal(null)} />}
    </section>
  )
}

// Create-automation modal. Reuses the new-project modal shell (.np-*).
function AutomationModal({ prefill, onClose }: { prefill?: Partial<CreateAutomationInput>; onClose: () => void }) {
  const create = useAutomationStore((s) => s.create)
  const [name, setName] = useState(prefill?.name ?? '')
  const [prompt, setPrompt] = useState(prefill?.prompt ?? '')
  const [kind, setKind] = useState<TriggerKind>('interval')
  const [interval, setInterval] = useState(60)
  const [atTime, setAtTime] = useState('09:00')
  const [busy, setBusy] = useState(false)

  const confirm = async () => {
    if (!name.trim() || !prompt.trim() || busy) return
    setBusy(true)
    try {
      await create({
        name: name.trim(),
        prompt: prompt.trim(),
        trigger_kind: kind,
        interval_min: Math.max(1, interval),
        at_time: atTime,
      })
      toast('自动化已创建 · ' + name.trim())
      onClose()
    } catch {
      toast('创建失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="新建自动化">
        <div className="np-h">新建自动化<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">名称</div>
          <input className="np-input" placeholder="给这个自动化起个名字" value={name} onChange={(e) => setName(e.target.value)} autoFocus />

          <div className="np-lbl">指令（到点会作为一次对话真实执行）</div>
          <textarea
            className="np-ta"
            placeholder="例如：关注当天 AI 领域的重要动态，筛选 3-5 条整理成中文简报"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />

          <div className="np-lbl">触发方式</div>
          <div className="auto-trig">
            <div className="seg2">
              <b className={kind === 'interval' ? 'on' : ''} onClick={() => setKind('interval')}>每隔一段</b>
              <b className={kind === 'daily' ? 'on' : ''} onClick={() => setKind('daily')}>每天定时</b>
            </div>
            {kind === 'interval' ? (
              <div className="auto-trig-in">
                每
                <input type="number" min={1} aria-label="间隔分钟" value={interval} onChange={(e) => setInterval(Number(e.target.value) || 1)} />
                分钟运行一次
              </div>
            ) : (
              <div className="auto-trig-in">
                每天
                <input type="time" aria-label="每天运行时间" value={atTime} onChange={(e) => setAtTime(e.target.value)} />
                运行
              </div>
            )}
          </div>
        </div>
        <div className="np-foot">
          <span className="np-hint">创建后即按计划运行，可随时停用</span>
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-dark" disabled={!name.trim() || !prompt.trim() || busy} onClick={confirm}>创建</button>
        </div>
      </div>
    </div>
  )
}
