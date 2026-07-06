import { useEffect, useState, type ReactNode } from 'react'
import { toast } from '../stores/toastStore'
import { useChatStore } from '../stores/chatStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useUIStore } from '../stores/uiStore'
import { useExpertStore } from '../stores/expertStore'
import { CreateExpertModal } from '../components/expert/CreateExpertModal'
import {
  CONNS, EXP_CATS, EXP_GRID, EXP_SCENES, EXP_TEAMS, INSTALLED, SK_CATS, SK_GRID, SK_RECO,
  type ExpertTeam,
} from '../data/catalog'

type Hub = 'experts' | 'skills' | 'connectors'

// 详情弹窗的两种主体：单个专家（来自 EXP_GRID）或专家团（EXP_TEAMS）。
type Detail =
  | { type: 'expert'; icon: string; name: string; subtitle: string; badge: string; category: string; intro: string; strengths: string[] }
  | { type: 'team'; team: ExpertTeam }

// 召唤专家/专家团：把班底设进本会话 loadout（团队=全部成员），开一段干净对话。
// 传 prompt 时直接以该 prompt 发起对话（「试试这样问我」）；否则回首页 composer 待用户输入。
function summon(names: string[], display: string, prompt?: string) {
  useLoadoutStore.getState().summon(names)
  const chat = useChatStore.getState()
  if (prompt) {
    chat.startDraft(prompt.length > 26 ? prompt.slice(0, 26) + '…' : prompt)
    useUIStore.getState().setView('chat')
    void chat.send(prompt)
    toast('已召唤 · ' + display)
  } else {
    chat.startDraft('对话')
    useUIStore.getState().setView('home')
    toast('已召唤 ' + display + ' · 可直接开始对话')
  }
}

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
  const [sub, setSub] = useState<'专家' | '专家团'>('专家')
  const [cat, setCat] = useState('全部')
  const [detail, setDetail] = useState<Detail | null>(null)

  const experts = EXP_GRID.filter(([, , , , , , c]) => cat === '全部' || c === cat)
  const teams = EXP_TEAMS.filter((t) => cat === '全部' || t.category === cat)
  const empty = sub === '专家' ? experts.length === 0 : teams.length === 0

  return (
    <div className="hub-pane show">
      <div className="sec-title" style={{ marginTop: 2 }}>精选场景</div>
      <div className="scene-grid">
        {EXP_SCENES.map(([t, list]) => (
          <div className="scene-card" key={t} onClick={() => { setSub('专家团'); setCat('全部'); toast('打开场景 · ' + t) }}>
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
        <div className={`subtab ${sub === '专家' ? 'active' : ''}`.trim()} onClick={() => setSub('专家')}>专家</div>
        <div className={`subtab ${sub === '专家团' ? 'active' : ''}`.trim()} onClick={() => setSub('专家团')}>专家团</div>
        <div style={{ flex: 1 }} />
        <div className="subtab" style={{ fontSize: 12, color: 'var(--brand-600)' }}>最热</div>
        <div className="subtab" style={{ fontSize: 12 }}>最新</div>
      </div>
      <div className="cats">
        {EXP_CATS.map((c) => (
          <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>
        ))}
      </div>

      {sub === '专家' ? (
        <div className="card-grid g4">
          {experts.map(([ic, n, s, b, d, tags, c]) => (
            <div className="ecard" key={n + s} onClick={() => setDetail({ type: 'expert', icon: ic, name: n, subtitle: s, badge: b, category: c, intro: d, strengths: tags })}>
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
      ) : (
        <div className="card-grid g4">
          {teams.map((t) => (
            <div className="ecard" key={t.name} onClick={() => setDetail({ type: 'team', team: t })}>
              <div className="ec-h">
                <div className="ec-av">{t.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ec-n">{t.name}{t.badge && <span className="b">{t.badge}</span>}</div>
                  <div className="ec-s">{t.source}</div>
                </div>
              </div>
              <div className="ec-d">{t.intro}</div>
              <div className="ec-tags">{t.tags.map((x) => <span className="ec-tag" key={x}>{x}</span>)}</div>
            </div>
          ))}
        </div>
      )}
      {empty && <div className="hub-blank">该分类下暂无{sub}</div>}

      {detail && <ExpertDetailModal detail={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

// 专家 / 专家团 详情弹窗（套现有 .np-overlay/.np-modal 骨架，天然继承暗色覆盖）。
function ExpertDetailModal({ detail, onClose }: { detail: Detail; onClose: () => void }) {
  // 直接在三元里判别 detail.type，让 TS 正确收窄联合类型。
  const icon = detail.type === 'team' ? detail.team.icon : detail.icon
  const name = detail.type === 'team' ? detail.team.name : detail.name
  const subtitle = detail.type === 'team' ? detail.team.source : detail.subtitle
  const badge = detail.type === 'team' ? detail.team.badge : detail.badge
  const category = detail.type === 'team' ? detail.team.category : detail.category
  const intro = detail.type === 'team' ? detail.team.intro : detail.intro
  const strengths = detail.type === 'team' ? detail.team.strengths : detail.strengths
  const members = detail.type === 'team' ? detail.team.members : null
  const prompts = detail.type === 'team' ? detail.team.prompts : []
  // 召唤班底：专家团 = 全部成员；单专家 = 其本人。
  const names = detail.type === 'team' ? detail.team.members.map((m) => m.name) : [detail.name]

  const doSummon = (prompt?: string) => { summon(names, name, prompt); onClose() }

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" style={{ width: 460 }} role="dialog" aria-modal="true" aria-label={name}>
        <div className="np-h">
          <div className="ec-av" style={{ width: 50, height: 50, fontSize: 26 }}>{icon}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 800 }}>{name}</div>
            <div className="ec-tags" style={{ marginTop: 6 }}>
              {subtitle && <span className="ec-tag">{subtitle}</span>}
              <span className="ec-tag">{category}</span>
              {badge && <span className="ec-tag">{badge}</span>}
            </div>
          </div>
          <button className="np-x" onClick={onClose}>×</button>
        </div>
        <div className="np-body">
          <div className="sec-title" style={{ margin: '10px 0 8px' }}>能力介绍</div>
          <div className="ec-d" style={{ fontSize: 13.5, lineHeight: 1.7 }}>{intro}</div>

          <div className="sec-title" style={{ margin: '18px 0 8px' }}>擅长领域</div>
          <div className="ec-tags">{strengths.map((s) => <span className="ec-tag" key={s}>{s}</span>)}</div>

          {members && (
            <>
              <div className="sec-title" style={{ margin: '18px 0 8px' }}>团队成员</div>
              {members.map((m) => (
                <div className="pkc-row" key={m.name} style={{ cursor: 'default' }}>
                  <span className="pi">🧑</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="pn">{m.role}{m.lead && <span className="ec-tag" style={{ marginLeft: 6 }}>⭐ 主理人</span>}</div>
                    <div className="pd">{m.name}</div>
                  </div>
                </div>
              ))}
            </>
          )}

          {prompts.length > 0 && (
            <>
              <div className="sec-title" style={{ margin: '18px 0 8px' }}>试试这样问我</div>
              {prompts.map((p) => (
                <div className="pkc-row" key={p} onClick={() => doSummon(p)}>
                  <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--text-2)' }}>“{p}”</div>
                  <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>›</span>
                </div>
              ))}
            </>
          )}
        </div>
        <div className="np-foot">
          <button className="btn-dark" style={{ flex: 1, justifyContent: 'center' }} onClick={() => doSummon()}>召唤 {name}</button>
        </div>
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

// 我的专家（WB-049）：列出/创建/删除/召唤当前 owner 的自定义专家。
function MyExpertsPane({ onBack }: { onBack: () => void }) {
  const experts = useExpertStore((s) => s.experts)
  const load = useExpertStore((s) => s.load)
  const remove = useExpertStore((s) => s.remove)
  const [createOpen, setCreateOpen] = useState(false)

  useEffect(() => { void load() }, [load])

  return (
    <div className="hub-pane show">
      <div className="ph" style={{ alignItems: 'center', marginTop: 2 }}>
        <button className="btn-ghost" onClick={onBack}>‹ 全部专家</button>
        <div style={{ flex: 1 }} />
        {experts.length > 0 && <button className="hub-act" onClick={() => setCreateOpen(true)}>＋ 创建专家</button>}
      </div>

      {experts.length === 0 ? (
        <div className="auto-empty">
          <div className="auto-empty-ic">🎓</div>
          <div className="auto-empty-t">还没有创建任何专家</div>
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: -6 }}>创建属于你的专家，分享专业知识</div>
          <button className="btn-dark auto-empty-add" onClick={() => setCreateOpen(true)}>＋ 创建专家</button>
        </div>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 14 }}>
          {experts.map((e) => (
            <div className="ecard" key={e.id}>
              <div className="ec-h">
                <div className="ec-av">{e.avatar}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ec-n">{e.name}</div>
                  <div className="ec-s">{e.subtitle || '自定义专家'}</div>
                </div>
              </div>
              <div className="ec-d">{e.intro || e.persona}</div>
              <div className="ec-tags">{e.tags.map((t) => <span className="ec-tag" key={t}>{t}</span>)}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button className="btn-dark" style={{ flex: 1, justifyContent: 'center' }} onClick={() => summon([e.name], e.name)}>召唤</button>
                <button className="btn-ghost" onClick={() => { void remove(e.id); toast('已删除 · ' + e.name) }}>删除</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <CreateExpertModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => setCreateOpen(false)} />
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
  // 「我的专家」子视图（WB-049），仅在专家 tab 下有效；切换任意 tab 都退回目录。
  const [myExperts, setMyExperts] = useState(false)
  const placeholder = { experts: '搜索专家职称或描述', skills: '搜索技能', connectors: '搜索连接器' }[hub]
  const actLabel = { experts: '我的专家', skills: '添加技能', connectors: '自定义连接器' }[hub]

  const onAct = () => { if (hub === 'experts') setMyExperts(true); else toast(actLabel) }
  const switchHub = (id: Hub) => { setHub(id); setMyExperts(false) }

  return (
    <section className="view active" data-view="experts">
      <div className="hub-top">
        {TABS.map((t) => (
          <div key={t.id} className={`hub-tab ${hub === t.id ? 'active' : ''}`.trim()} onClick={() => switchHub(t.id)}>
            {t.icon}{t.label}
          </div>
        ))}
        <div className="sp" />
        <div className="search-box" style={{ margin: 0, width: 260 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <input placeholder={placeholder} />
        </div>
        <button className="hub-act" onClick={onAct}>{actLabel}</button>
      </div>
      <div className="hub-body">
        {hub === 'experts' && (myExperts ? <MyExpertsPane onBack={() => setMyExperts(false)} /> : <ExpertsPane />)}
        {hub === 'skills' && <SkillsPane />}
        {hub === 'connectors' && <ConnectorsPane />}
      </div>
    </section>
  )
}
