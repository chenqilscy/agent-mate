import { useState, type ReactNode } from 'react'
import { toast } from '../stores/toastStore'
import {
  CONNS, EXP_CATS, EXP_GRID, EXP_SCENES, INSTALLED, SK_CATS, SK_GRID, SK_RECO,
} from '../data/catalog'

type Hub = 'experts' | 'skills' | 'connectors'

function AddBtn() {
  const [on, setOn] = useState(false)
  return (
    <button
      className={`add-btn ${on ? 'on' : ''}`.trim()}
      aria-label="添加"
      onClick={() => { setOn((v) => !v); toast(!on ? '已添加' : '已移除') }}
    >
      {on ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 12l5 5L20 6" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
      )}
    </button>
  )
}

function ExpertsPane() {
  const [cat, setCat] = useState('全部')
  return (
    <div className="hub-pane show">
      <div className="sec-title" style={{ marginTop: 2 }}>精选场景</div>
      <div className="scene-grid">
        {EXP_SCENES.map(([t, list]) => (
          <div className="scene-card" key={t} onClick={() => toast('打开场景 · ' + t)}>
            <div className="sc-top">{t}</div>
            <div className="sc-list">
              {list.map((n) => (
                <div className="sc-item" key={n}><span className="av">🧑</span>{n}</div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="subtabs">
        <div className="subtab active">专家</div>
        <div className="subtab">专家团</div>
        <div style={{ flex: 1 }} />
        <div className="subtab" style={{ fontSize: 12, color: 'var(--brand-600)' }}>最热</div>
        <div className="subtab" style={{ fontSize: 12 }}>最新</div>
      </div>
      <div className="cats">
        {EXP_CATS.map((c) => (
          <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>
        ))}
      </div>
      <div className="card-grid g4">
        {EXP_GRID.map(([ic, n, s, b, d, tags]) => (
          <div className="ecard" key={n + s} onClick={() => toast('召唤专家 · ' + n)}>
            <div className="ec-h">
              <div className="ec-av">{ic}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ec-n">{n}{b && <span className="b">{b}</span>}</div>
                <div className="ec-s">{s}</div>
              </div>
            </div>
            <div className="ec-d">{d}</div>
            <div className="ec-tags">{tags.map((t) => <span className="ec-tag" key={t}>{t}</span>)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function SkillsPane() {
  const [sub, setSub] = useState<'market' | 'installed'>('market')
  return (
    <div className="hub-pane show">
      <div className="subtabs">
        <div className={`subtab ${sub === 'market' ? 'active' : ''}`.trim()} onClick={() => setSub('market')}>技能市场</div>
        <div className={`subtab ${sub === 'installed' ? 'active' : ''}`.trim()} onClick={() => setSub('installed')}>
          已安装<span className="n">{INSTALLED.length}</span>
        </div>
      </div>

      {sub === 'market' ? (
        <div>
          <div className="cats" style={{ margin: '14px 0 2px' }}>
            <div className="cat active">推荐</div><div className="cat">SkillHub</div><div className="cat">套件</div>
          </div>
          <div className="flex-right">
            <div className="sec-title" style={{ margin: '8px 0' }}>为你推荐</div>
            <div className="rt" onClick={() => toast('已换一批推荐')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 019-9 9 9 0 016 2.3L21 8M21 12a9 9 0 01-9 9 9 9 0 01-6-2.3L3 16" /></svg>换一换
            </div>
          </div>
          <div className="card-grid g4">
            {SK_RECO.map(([ic, n, d]) => (
              <div className="scard" key={n}>
                <div className="sc-ic">{ic}</div>
                <div className="sc-info"><div className="sc-n">{n}</div><div className="sc-d">{d}</div></div>
                <AddBtn />
              </div>
            ))}
          </div>
          <div className="cats" style={{ marginTop: 20 }}>
            {SK_CATS.map((c, i) => <div key={c} className={`cat ${i === 0 ? 'active' : ''}`.trim()}>{c}</div>)}
          </div>
          <div className="card-grid g4">
            {SK_GRID.map(([ic, n, d]) => (
              <div className="scard" key={n}>
                <div className="sc-ic">{ic}</div>
                <div className="sc-info"><div className="sc-n">{n}</div><div className="sc-d">{d}</div></div>
                <AddBtn />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 18 }}>
          {INSTALLED.map(([ic, color, n, d]) => (
            <div className="inst-card" key={n}>
              <span className="inst-ic" style={{ background: color }}>{ic}</span>
              <div style={{ minWidth: 0 }}>
                <div className="inst-n">{n}</div>
                <div className="inst-d">{d}</div>
              </div>
              <span className="inst-more" onClick={() => toast('技能管理 · ' + n)}>⋯</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ConnectorsPane() {
  return (
    <div className="hub-pane show">
      <div className="card-grid g2" style={{ marginTop: 6 }}>
        {CONNS.map(([ic, n, d]) => (
          <div className="conn" key={n}>
            <div className="c-ic">{ic}</div>
            <div style={{ flex: 1, minWidth: 0 }}><div className="c-n">{n}</div><div className="c-d">{d}</div></div>
            <AddBtn />
          </div>
        ))}
      </div>
    </div>
  )
}

const TABS: { id: Hub; label: string; icon: ReactNode }[] = [
  { id: 'experts', label: '专家', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg> },
  { id: 'skills', label: '技能', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg> },
  { id: 'connectors', label: '连接器', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2" /></svg> },
]

export function ExpertsView() {
  const [hub, setHub] = useState<Hub>('experts')
  const placeholder = { experts: '搜索专家职称或描述', skills: '搜索技能', connectors: '搜索连接器' }[hub]
  const actLabel = { experts: '我的专家', skills: '添加技能', connectors: '自定义连接器' }[hub]

  return (
    <section className="view active" data-view="experts">
      <div className="hub-top">
        {TABS.map((t) => (
          <div key={t.id} className={`hub-tab ${hub === t.id ? 'active' : ''}`.trim()} onClick={() => setHub(t.id)}>
            {t.icon}{t.label}
          </div>
        ))}
        <div className="sp" />
        <div className="search-box" style={{ margin: 0, width: 260 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <input placeholder={placeholder} />
        </div>
        <button className="hub-act" onClick={() => toast(actLabel)}>{actLabel}</button>
      </div>
      <div className="hub-body">
        {hub === 'experts' && <ExpertsPane />}
        {hub === 'skills' && <SkillsPane />}
        {hub === 'connectors' && <ConnectorsPane />}
      </div>
    </section>
  )
}
