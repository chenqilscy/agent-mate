import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { toast } from '../stores/toastStore'
import { useChatStore } from '../stores/chatStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useUIStore } from '../stores/uiStore'
import { useExpertStore } from '../stores/expertStore'
import { useSkillStore } from '../stores/skillStore'
import { CreateExpertModal } from '../components/expert/CreateExpertModal'
import { ConnectorDetailModal } from '../components/connector/ConnectorDetailModal'
import { api } from '../lib/api'
import {
  CONN_META, CONNS, EXP_CATS, EXP_GRID, EXP_SCENES, EXP_TEAMS, INSTALLED, SK_CATS, SK_GRID,
  SKILLHUB_CATS, SKILLHUB_FEATURED, SKILLHUB_GRID, SKILLHUB_KITS,
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

// ---- SkillHub「技能」页 --------------------------------------------------

// 小图标（沿用应用内 stroke/currentColor 风格）。
const IcDl = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3v12M7 11l5 5 5-5M5 21h14" /></svg>
const IcStar = () => <svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.9 6.3 6.9.6-5.2 4.5 1.6 6.8L12 17.3 5.8 20.8l1.6-6.8L2.2 8.9l6.9-.6z" /></svg>
const IcPlusSm = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
const IcPower = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 3v9" /><path d="M6.4 6.4a8 8 0 1 0 11.2 0" /></svg>
const IcEdit = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>
const IcTrash = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg>
const IcExt = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>
const IcSort = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 4v16M7 20l-3-3M7 4l3 3M17 20V4M17 4l3 3M17 20l-3-3" /></svg>

// 「编辑技能」：挂上 skill-creator 技能班底，回首页 composer 预填「请帮我编辑 X 这个 skill」。
function editSkill(name: string) {
  useLoadoutStore.getState().summonSkills(['skill-creator'])
  useLoadoutStore.getState().setDraft(`请帮我编辑 ${name} 这个 skill`)
  useChatStore.getState().startDraft('编辑技能 · ' + name)
  useUIStore.getState().setView('home')
  toast('已载入 skill-creator · 去编辑「' + name + '」')
}

// 按技能名跨目录取图标/底色/描述（用于「我安装的」等只有名字的场景）。
function skillInfo(name: string): { icon: string; color: string; desc: string } {
  const inst = INSTALLED.find((x) => x[2] === name)
  if (inst) return { icon: inst[0], color: inst[1], desc: inst[3] }
  const g = SKILLHUB_GRID.find((x) => x[2] === name)
  if (g) return { icon: g[0], color: g[1], desc: g[3] }
  const f = SKILLHUB_FEATURED.find((x) => x[2] === name)
  if (f) return { icon: f[0], color: f[1], desc: f[3] }
  const sk = SK_GRID.find((x) => x[1] === name)
  if (sk) return { icon: sk[0], color: '#6B7280', desc: sk[2] }
  return { icon: name.slice(0, 1).toUpperCase(), color: '#6B7280', desc: '已安装技能' }
}

// 已安装技能卡片的「⋯」菜单：关闭(停用)/编辑/卸载。点任意处关闭（挂载后才注册监听，
// 避免打开它的那一次点击立刻把自己关掉）。
function SkillMenu({ name, disabled, onClose }: { name: string; disabled: boolean; onClose: () => void }) {
  useEffect(() => {
    const h = () => onClose()
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [onClose])
  const skills = useSkillStore.getState()
  return (
    <div className="card-menu open">
      <div className="more-item" onClick={() => { skills.toggleDisabled(name); toast((disabled ? '已启用 · ' : '已关闭 · ') + name) }}>
        <IcPower />{disabled ? '启用' : '关闭'}
      </div>
      <div className="more-item" onClick={() => editSkill(name)}>
        <IcEdit />编辑
      </div>
      <div className="more-item div" onClick={() => { skills.uninstall(name); toast('已卸载 · ' + name) }}>
        <IcTrash />卸载
      </div>
    </div>
  )
}

// 已安装标记 ✓ + ⋯ 菜单（网格卡与精选卡共用）。
function InstalledCtl({ name }: { name: string }) {
  const disabled = useSkillStore((s) => s.disabled.includes(name))
  const [menu, setMenu] = useState(false)
  return (
    <div className="hc-act">
      {disabled && <span className="hc-off">已关闭</span>}
      <span className="hc-chk" title="已安装">✓</span>
      <button className="hc-more" aria-label="管理技能" onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</button>
      {menu && <SkillMenu name={name} disabled={disabled} onClose={() => setMenu(false)} />}
    </div>
  )
}

// 安装按钮（未安装态）。
function InstallBtn({ name }: { name: string }) {
  const install = useSkillStore((s) => s.install)
  return (
    <button className="add-btn" aria-label="安装" onClick={(e) => { e.stopPropagation(); install(name); toast('已安装 · ' + name) }}>
      <IcPlusSm />
    </button>
  )
}

// SkillHub 商店网格卡：图标 + 名称 + 描述 + 下载/星标，右上角安装/管理。
function SkillHubCard({ item }: { item: (typeof SKILLHUB_GRID)[number] }) {
  const [label, color, name, desc, downloads, stars] = item
  const installed = useSkillStore((s) => s.installed.includes(name))
  return (
    <div className="hcard">
      <div className="hc-h">
        <span className="hc-ic" style={{ background: color }}>{label}</span>
        <div className="hc-n" title={name}>{name}</div>
        {installed ? <InstalledCtl name={name} /> : <InstallBtn name={name} />}
      </div>
      <div className="hc-d">{desc}</div>
      <div className="hc-foot">
        <span className="hc-stat"><IcDl />{downloads}</span>
        <span className="hc-stat"><IcStar />{stars}</span>
      </div>
    </div>
  )
}

// 精选技能大卡（顶部）。
function FeaturedCard({ item }: { item: (typeof SKILLHUB_FEATURED)[number] }) {
  const [icon, , name, desc, badge] = item
  const installed = useSkillStore((s) => s.installed.includes(name))
  return (
    <div className="fcard">
      {badge && <span className="fc-badge">{badge}</span>}
      <div className="fc-h">
        <span className="fc-ic">{icon}</span>
        <div className="fc-n" title={name}>{name}</div>
        {installed ? <InstalledCtl name={name} /> : <InstallBtn name={name} />}
      </div>
      <div className="fc-d">{desc}</div>
    </div>
  )
}

// 精选技能区（4 个一屏，「换一换」轮换池）。
function FeaturedSkills() {
  const [off, setOff] = useState(0)
  const n = Math.min(4, SKILLHUB_FEATURED.length)
  const items = Array.from({ length: n }, (_, i) => SKILLHUB_FEATURED[(off + i) % SKILLHUB_FEATURED.length])
  return (
    <>
      <div className="flex-right" style={{ marginTop: 2 }}>
        <div className="sec-title">精选技能</div>
        <div className="rt" onClick={() => { setOff((o) => (o + n) % SKILLHUB_FEATURED.length); toast('已换一批') }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 019-9 9 9 0 016 2.3L21 8M21 12a9 9 0 01-9 9 9 9 0 01-6-2.3L3 16" /></svg>换一换
        </div>
      </div>
      <div className="card-grid g4">
        {items.map((it) => <FeaturedCard key={it[2]} item={it} />)}
      </div>
    </>
  )
}

// SkillHub 目录：分类过滤 + skillhub.cn 链接 + 排序 + 网格。
function SkillHubView() {
  const [cat, setCat] = useState('全部')
  const list = SKILLHUB_GRID.filter(([, , , , , , c]) => cat === '全部' || c === cat)
  return (
    <>
      <div className="sk-cathead">
        <div className="cats">
          {SKILLHUB_CATS.map((c) => (
            <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>
          ))}
        </div>
        <div className="sk-cathead-r">
          <a className="sk-link" href="https://skillhub.cn" target="_blank" rel="noopener noreferrer"><IcExt />skillhub.cn</a>
          <span className="sk-sort" onClick={() => toast('排序 · 综合评分')}><IcSort />综合评分</span>
        </div>
      </div>
      <div className="card-grid g4">
        {list.map((it) => <SkillHubCard key={it[2] + it[0]} item={it} />)}
      </div>
      {list.length === 0 && <div className="hub-blank">该分类下暂无技能</div>}
    </>
  )
}

// 推荐（保留原简版目录卡）。
function RecoView() {
  const [cat, setCat] = useState('全部')
  return (
    <>
      <div className="cats">
        {SK_CATS.map((c) => <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>)}
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
    </>
  )
}

// 套件（技能包）。
function KitView() {
  return (
    <div className="card-grid g2" style={{ marginTop: 4 }}>
      {SKILLHUB_KITS.map(([ic, color, name, desc, count]) => (
        <div className="conn" key={name}>
          <div className="c-ic" style={{ background: color, color: '#fff' }}>{ic}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="c-n">{name} <span className="kc-count">· {count} 个技能</span></div>
            <div className="c-d">{desc}</div>
          </div>
          <button className="hub-act" onClick={() => toast('安装套件 · ' + name)}>安装套件</button>
        </div>
      ))}
    </div>
  )
}

function SkillsPane() {
  const [seg, setSeg] = useState<'skillhub' | 'reco' | 'kit'>('skillhub')
  return (
    <div className="hub-pane show">
      <FeaturedSkills />
      <div className="sk-seg">
        <div className={`sk-seg-item ${seg === 'reco' ? 'active' : ''}`.trim()} onClick={() => setSeg('reco')}>推荐</div>
        <div className={`sk-seg-item ${seg === 'skillhub' ? 'active' : ''}`.trim()} onClick={() => setSeg('skillhub')}>SkillHub</div>
        <div className={`sk-seg-item ${seg === 'kit' ? 'active' : ''}`.trim()} onClick={() => setSeg('kit')}>套件</div>
      </div>
      {seg === 'skillhub' && <SkillHubView />}
      {seg === 'reco' && <RecoView />}
      {seg === 'kit' && <KitView />}
    </div>
  )
}

// 我安装的（从顶栏「我安装的 N」进入）：管理已安装技能。
function InstalledPane({ onBack }: { onBack: () => void }) {
  const installed = useSkillStore((s) => s.installed)
  return (
    <div className="hub-pane show">
      <div className="ph" style={{ alignItems: 'center', marginTop: 2 }}>
        <button className="btn-ghost" onClick={onBack}>‹ 技能市场</button>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12.5, color: 'var(--text-3)' }}>共 {installed.length} 个技能</span>
      </div>
      {installed.length === 0 ? (
        <div className="auto-empty">
          <div className="auto-empty-ic">🧩</div>
          <div className="auto-empty-t">还没有安装任何技能</div>
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: -6 }}>去 SkillHub 商店挑选并安装你需要的技能</div>
          <button className="btn-dark auto-empty-add" onClick={onBack}>去技能市场</button>
        </div>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 14 }}>
          {installed.map((name) => <InstalledCard key={name} name={name} />)}
        </div>
      )}
    </div>
  )
}

function InstalledCard({ name }: { name: string }) {
  const info = skillInfo(name)
  const disabled = useSkillStore((s) => s.disabled.includes(name))
  const [menu, setMenu] = useState(false)
  return (
    <div className={`inst-card ${disabled ? 'off' : ''}`.trim()}>
      <span className="inst-ic" style={{ background: info.color }}>{info.icon}</span>
      <div style={{ minWidth: 0 }}>
        <div className="inst-n">{name}{disabled && <span className="hc-off" style={{ marginLeft: 6 }}>已关闭</span>}</div>
        <div className="inst-d">{info.desc}</div>
      </div>
      <div className="more-wrap" style={{ position: 'absolute', top: 8, right: 8 }}>
        <span className="inst-more" onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</span>
        {menu && <SkillMenu name={name} disabled={disabled} onClose={() => setMenu(false)} />}
      </div>
    </div>
  )
}

// 连接器加入本会话的按钮（受控，反映真实 loadout；stopPropagation 不触发卡片详情）。
function ConnAddBtn({ on, onToggle }: { on: boolean; onToggle: (e: MouseEvent) => void }) {
  return (
    <button type="button" className={`add-btn ${on ? 'on' : ''}`.trim()} aria-label={on ? '移除' : '添加'} onClick={onToggle}>
      {on ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 12l5 5L20 6" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
      )}
    </button>
  )
}

function ConnectorsPane() {
  const [detail, setDetail] = useState<[string, string, string] | null>(null)
  const connectors = useLoadoutStore((s) => s.connectors)
  // OAuth 连接器（当前仅金山文档）的实时连接态，卡片上以「● 已连接」展示。
  const [authed, setAuthed] = useState<Record<string, boolean>>({})
  const refreshAuth = () => {
    if (CONN_META['金山文档']?.oauth) {
      api.kdocsStatus().then((s) => setAuthed((m) => ({ ...m, 金山文档: s.authenticated }))).catch(() => {})
    }
  }
  useEffect(() => { refreshAuth() }, [])

  return (
    <div className="hub-pane show">
      <div className="card-grid g2" style={{ marginTop: 6 }}>
        {CONNS.map(([ic, n, d]) => {
          const meta = CONN_META[n]
          const added = connectors.includes(n)
          const open = () => setDetail([ic, n, d])
          // oauth 连接器显示实时连接态；其它显示静态标签。
          const badge = meta && (meta.oauth
            ? (authed[n]
                ? <span className="conn-tag rdy">● 已连接</span>
                : <span className="conn-tag tok">{meta.statusLabel}</span>)
            : <span className={`conn-tag ${meta.status}`}>{meta.statusLabel}</span>)
          return (
            <div
              className="conn" key={n} role="button" tabIndex={0} onClick={open}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }}
            >
              <div className="c-ic">{ic}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="c-n">{n}{badge}</div>
                <div className="c-d">{d}</div>
              </div>
              <ConnAddBtn
                on={added}
                onToggle={(e) => {
                  e.stopPropagation()
                  useLoadoutStore.getState().toggle('conn', n)
                  toast((added ? '已移除 · ' : '已添加到本会话 · ') + n)
                }}
              />
            </div>
          )
        })}
      </div>
      {detail && (
        <ConnectorDetailModal
          icon={detail[0]} name={detail[1]} desc={detail[2]}
          onClose={() => { setDetail(null); refreshAuth() }}
        />
      )}
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
  // 「我的专家」子视图（WB-049）/「我安装的」子视图，仅在各自 tab 下有效；切 tab 退回目录。
  const [myExperts, setMyExperts] = useState(false)
  const [myInstalled, setMyInstalled] = useState(false)
  const installedCount = useSkillStore((s) => s.installed.length)
  const placeholder = { experts: '搜索专家职称或描述', skills: '搜索技能', connectors: '搜索连接器' }[hub]
  const actLabel = { experts: '我的专家', skills: '添加技能', connectors: '自定义连接器' }[hub]

  const onAct = () => { if (hub === 'experts') setMyExperts(true); else toast(actLabel) }
  const switchHub = (id: Hub) => { setHub(id); setMyExperts(false); setMyInstalled(false) }

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
        {hub === 'skills' ? (
          <>
            <button className={`hub-act ${myInstalled ? 'on' : ''}`.trim()} onClick={() => setMyInstalled((v) => !v)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="4" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
              我安装的<span className="hub-act-n">{installedCount}</span>
            </button>
            <button className="hub-act" onClick={() => toast('添加技能')}>＋ 添加技能</button>
          </>
        ) : (
          <button className="hub-act" onClick={onAct}>{actLabel}</button>
        )}
      </div>
      <div className="hub-body">
        {hub === 'experts' && (myExperts ? <MyExpertsPane onBack={() => setMyExperts(false)} /> : <ExpertsPane />)}
        {hub === 'skills' && (myInstalled ? <InstalledPane onBack={() => setMyInstalled(false)} /> : <SkillsPane />)}
        {hub === 'connectors' && <ConnectorsPane />}
      </div>
    </section>
  )
}
