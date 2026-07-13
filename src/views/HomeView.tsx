import { useEffect, useRef, useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { useProjectStore } from '../stores/projectStore'
import { useSettingsStore } from '../stores/settingsStore'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'
import { Popover } from '../components/ui/Popover'
import { PermPopover } from '../components/composer/PermPopover'

const SCENES: [string, string, string][] = [
  ['day', '🔥', '日常办公'],
  ['code', '💻', '代码开发'],
  ['design', '🎨', '设计创意'],
]

export function HomeView() {
  const [scene, setScene] = useState('day')
  const startDraft = useChatStore((s) => s.startDraft)
  const startProject = useChatStore((s) => s.startProject)
  const send = useChatStore((s) => s.send)
  const setView = useUIStore((s) => s.setView)
  const { QUICK } = useCatalog()

  const projects = useProjectStore((s) => s.projects)
  const loadProjects = useProjectStore((s) => s.load)
  const perm = useSettingsStore((s) => s.perm)

  // 首页新任务的目标空间（null = 默认空间，不绑定任何项目）与两个 tray popover。
  const [selProject, setSelProject] = useState<string | null>(null)
  const [pop, setPop] = useState<'ws' | 'perm' | null>(null)
  const wsAnchor = useRef<HTMLButtonElement | null>(null)
  const permAnchor = useRef<HTMLButtonElement | null>(null)

  useEffect(() => { void loadProjects() }, [loadProjects])

  const selName = selProject ? projects.find((p) => p.id === selProject)?.name : null

  const launch = (text: string) => {
    const title = text.length > 26 ? text.slice(0, 26) + '…' : text
    if (selProject && selName) startProject(selProject, title)
    else startDraft(title)
    setView('chat')
    void send(text)
  }

  return (
    <section className="view active" data-view="home">
      <div className="reward" onClick={() => toast('打开成长计划')}>
        <span className="ri">🚀</span>做任务赢积分好礼
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M9 6l6 6-6 6" /></svg>
      </div>
      <div className="home-wrap">
        <div className="home-inner">
          <h1 className="hero-title">
            WorkBuddy<br />
            <span className="g">你的职场超能力</span>
          </h1>
          <div className="scenes">
            {SCENES.map(([id, ic, label]) => (
              <div key={id} className={`scene ${scene === id ? 'active' : ''}`.trim()} onClick={() => setScene(id)}>
                <span className="si">{ic}</span>{label}
              </div>
            ))}
          </div>
          <div className="quick">
            {QUICK[scene].map(([ic, label]) => (
              <div
                key={label}
                className="qchip"
                onClick={() => (label === '更多' ? toast('更多快捷入口，敬请期待') : launch(label))}
              >
                {ic === '⋯' ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="6" cy="12" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="18" cy="12" r="1.6" /></svg>
                ) : (
                  ic
                )}{' '}
                {label}
              </div>
            ))}
          </div>

          <div className="comp-zone">
            <svg className="mascot2" viewBox="0 0 100 100" aria-hidden="true">
              <circle cx="79" cy="13" r="9" fill="#16B37A" />
              <path d="M75 13l3 3 5-5" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" />
              <path d="M24 48a28 20 0 0152 0" fill="none" stroke="#9AA6B2" strokeWidth="5" strokeLinecap="round" />
              <rect x="16" y="44" width="12" height="19" rx="6" fill="#8B98A6" />
              <rect x="72" y="44" width="12" height="19" rx="6" fill="#8B98A6" />
              <path d="M34 38l7 9M66 38l-7 9" stroke="#C7CFD8" strokeWidth="6" strokeLinecap="round" />
              <rect x="29" y="44" width="42" height="40" rx="17" fill="#E2E7ED" />
              <ellipse cx="43" cy="63" rx="4.3" ry="5.6" fill="#16B37A" />
              <ellipse cx="57" cy="63" rx="4.3" ry="5.6" fill="#16B37A" />
              <circle cx="44.5" cy="61" r="1.3" fill="#eafff6" />
              <circle cx="58.5" cy="61" r="1.3" fill="#eafff6" />
              <path d="M46 73q4 2.6 8 0" stroke="#8B98A6" strokeWidth="2.4" fill="none" strokeLinecap="round" />
            </svg>
            <Composer variant="home" onSend={launch} autoFocus />
            <div className="ctray">
              <button
                className="tray-chip"
                ref={wsAnchor}
                onClick={() => setPop((c) => (c === 'ws' ? null : 'ws'))}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
                {selName ?? '选择工作空间'}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
              </button>
              <button
                className="tray-chip"
                ref={permAnchor}
                onClick={() => setPop((c) => (c === 'perm' ? null : 'perm'))}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 14, height: 14 }}><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
                {perm}
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
              </button>
            </div>
            <Popover open={pop === 'ws'} anchor={wsAnchor.current} dir="down" onClose={() => setPop(null)} minWidth={220}>
              <div className="pop-item" onClick={() => { setSelProject(null); setPop(null) }}>
                无（默认空间）{selProject === null && <span className="chk">✓</span>}
              </div>
              {projects.length === 0 && <div className="pop-item pop-empty">暂无工作空间</div>}
              {projects.map((p) => (
                <div className="pop-item" key={p.id} onClick={() => { setSelProject(p.id); setPop(null) }}>
                  <span className="pi-ic">🗂️</span>{p.name}{selProject === p.id && <span className="chk">✓</span>}
                </div>
              ))}
            </Popover>
            <Popover open={pop === 'perm'} anchor={permAnchor.current} dir="down" onClose={() => setPop(null)} className="perm-pop" minWidth={232}>
              <PermPopover />
            </Popover>
          </div>
        </div>
      </div>
    </section>
  )
}
