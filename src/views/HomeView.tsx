import { useState } from 'react'
import { Composer } from '../components/composer/Composer'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'

const SCENES: [string, string, string][] = [
  ['day', '🔥', '日常办公'],
  ['code', '💻', '代码开发'],
  ['design', '🎨', '设计创意'],
]

export function HomeView() {
  const [scene, setScene] = useState('day')
  const startDraft = useChatStore((s) => s.startDraft)
  const send = useChatStore((s) => s.send)
  const setView = useUIStore((s) => s.setView)
  const { QUICK } = useCatalog()

  const launch = (text: string) => {
    startDraft(text.length > 26 ? text.slice(0, 26) + '…' : text)
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
              <button className="tray-chip" onClick={() => toast('选择工作空间')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>
                选择工作空间
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
              </button>
              <button className="tray-chip" onClick={() => toast('默认权限')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 14, height: 14 }}><circle cx="12" cy="12" r="9" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
                默认权限
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 10, height: 10 }}><path d="M6 9l6 6 6-6" /></svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
