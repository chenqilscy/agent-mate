import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'
import { toast } from '../stores/toastStore'
import { useChatStore } from '../stores/chatStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useUIStore } from '../stores/uiStore'
import { useExpertStore } from '../stores/expertStore'
import { useSkillStore, matchSkill } from '../stores/skillStore'
import { CreateExpertModal } from '../components/expert/CreateExpertModal'
import { ConnectorDetailModal } from '../components/connector/ConnectorDetailModal'
import { SkillDetail, type SkillTarget } from '../components/skill/SkillDetail'
import { AddSkillControl } from '../components/skill/AddSkillControl'
import { api } from '../lib/api'
import type { InstalledSkill, SkillCard } from '../lib/types'
import { type ExpertTeam } from '../data/catalog'
import { useCatalog, useCatalogStore } from '../stores/catalogStore'

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

// 连接器卡片必须直接进入一段已挂载的新草稿。若只在目录页 toggle，用户随后点“新建任务”
// 会按会话隔离规则 reset loadout，形成“显示已添加、实际无法使用”的假入口（WB-194）。
function summonConnector(name: string) {
  useLoadoutStore.getState().summonConnectors([name])
  useChatStore.getState().startDraft('试试 · ' + name)
  useUIStore.getState().setView('home')
  toast('已挂载「' + name + '」· 去试试')
}

// 「推荐」段卡片的 ＋（WB-181）。此前它是个纯谎言：只翻转组件内 useState + toast「已添加」，
// 不进 loadout、不安装、刷新即复原。现在按卡片的**真实身份**分派——因为这一段的 SK_GRID
// 混着三种互不相容的东西（实测 16 张：6 张内置 / 3 张可装 / 7 张上游根本不存在）：
//   · 内置技能、已装且未停用 → 挂载进会话并跳 composer（同 SkillDetail 的「去试试」）
//   · 其余 → 真安装（装不到会诚实报错，不再假装成功）
// 三种身份混在一段里本身是数据问题，归 WB-184（数据源收敛）/ WB-183（目录入库）。
//
// 为什么是「挂载+跳转」而不是留在原地 toggle：loadout 是**会话级**的，`openSession` 与
// 侧栏「新建任务」都会 reset 它（chatStore.ts:70 / Sidebar.tsx:171，WB-003 的正确行为）。
// 留在原地 toggle 会得到「状态是真的、但用户一导航去用就没了」——真状态、假用处。
// 本 app 既有的正确出路是 summon 系：设 loadout → startDraft（不 reset）→ setView，
// 专家「召唤」(L30) 与 SkillDetail「去试试」(tryIt) 都走这条，这里保持一致。
function RecoBtn({ skillKey, displayName }: { skillKey: string; displayName: string }) {
  const builtin = useSkillStore((s) => s.builtin.find((b) => b.name === skillKey || b.slug === skillKey))
  const inst = useSkillStore((s) => matchSkill(s.installed, skillKey))
  if (!builtin && !(inst && !inst.disabled)) return <InstallBtn name={displayName} />
  return (
    <button
      type="button"
      className="add-btn"
      aria-label="挂载到本会话"
      title={'挂载「' + displayName + '」到本会话'}
      onClick={(e) => {
        e.stopPropagation()
        useLoadoutStore.getState().summonSkills([builtin?.slug || inst?.slug || inst?.key || skillKey])
        useChatStore.getState().startDraft('试试 · ' + displayName)
        useUIStore.getState().setView('home')
        toast('已挂载「' + displayName + '」· 去试试')
      }}
    >
      <IcPlusSm />
    </button>
  )
}

function ExpertsPane() {
  const [sub, setSub] = useState<'专家' | '专家团'>('专家')
  const [cat, setCat] = useState('全部')
  const [detail, setDetail] = useState<Detail | null>(null)
  const { EXP_GRID, EXP_TEAMS, EXP_SCENES, EXP_CATS } = useCatalog()

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

const IcSpin = () => <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg>

// 「编辑技能」：挂上 skill-creator 技能班底，回首页 composer 预填「请帮我编辑 X 这个 skill」。
function editSkill(name: string) {
  useLoadoutStore.getState().summonSkills(['skill-creator'])
  useLoadoutStore.getState().setDraft(`请帮我编辑 ${name} 这个 skill`)
  useChatStore.getState().startDraft('编辑技能 · ' + name)
  useUIStore.getState().setView('home')
  toast('已载入 skill-creator · 去编辑「' + name + '」')
}

// 展示名 → 图标/底色；只读真实推荐目录/Hub 镜像，不再回退静态 SkillHub 假统计卡。
function skillTile(name: string): { icon: string; color: string } {
  const catalog = useCatalogStore.getState()
  const inst = catalog.INSTALLED.find((x) => x[2] === name)
  if (inst) return { icon: inst[0], color: inst[1] }
  const recommended = catalog.SK_GRID.find((x) => x.name === name || x.slug === name)
  if (recommended) return { icon: recommended.icon, color: '#6B7280' }
  const hub = [...catalog.skillFeatured, ...catalog.skillMirror].find((x) => x.name === name || x.slug === name)
  if (hub) return { icon: (hub.name.trim()[0] || '?').toUpperCase(), color: '#6B7280' }
  return { icon: (name.trim()[0] || '?').toUpperCase(), color: '#6B7280' }
}

// 已安装技能卡片的「⋯」菜单：关闭(停用)/编辑/卸载 —— 真实调后端（skillStore）。
// 点任意处关闭（挂载后才注册监听，避免打开它的那一次点击立刻把自己关掉）。
function SkillMenu({ skill, onClose }: { skill: InstalledSkill; onClose: () => void }) {
  useEffect(() => {
    const h = () => onClose()
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [onClose])
  const store = useSkillStore.getState()
  return (
    <div className="card-menu open">
      <div className="more-item" onClick={() => store.toggle(skill.key, !skill.disabled)}>
        <IcPower />{skill.disabled ? '启用' : '关闭'}
      </div>
      <div className="more-item" onClick={() => editSkill(skill.name)}>
        <IcEdit />编辑
      </div>
      <div className="more-item div" onClick={() => store.uninstall(skill.key)}>
        <IcTrash />卸载
      </div>
    </div>
  )
}

// 已安装标记 ✓ + ⋯ 菜单（网格卡与精选卡共用）。stopPropagation 不触发卡片详情。
function InstalledCtl({ skill }: { skill: InstalledSkill }) {
  const [menu, setMenu] = useState(false)
  return (
    <div className="hc-act" onClick={(e) => e.stopPropagation()}>
      {skill.disabled && <span className="hc-off">已关闭</span>}
      <span className="hc-chk" title="已安装">✓</span>
      <button className="hc-more" aria-label="管理技能" onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</button>
      {menu && <SkillMenu skill={skill} onClose={() => setMenu(false)} />}
    </div>
  )
}

// 安装按钮（未安装态）——真实安装，进行中转圈。
function InstallBtn({ name }: { name: string }) {
  const install = useSkillStore((s) => s.install)
  const busy = useSkillStore((s) => s.installing.includes(name))
  return (
    <button className="add-btn" aria-label="安装" disabled={busy} onClick={(e) => { e.stopPropagation(); void install(name) }}>
      {busy ? <IcSpin /> : <IcPlusSm />}
    </button>
  )
}

// 精选技能大卡（顶部）。仅展示 Hub 真实精选；无下发时不伪造一组静态精选。
type FeaturedItem = { iconUrl?: string; icon: string; name: string; desc: string; badge?: string }
function FeaturedCard({ item, onOpenDetail }: { item: FeaturedItem; onOpenDetail: (target: SkillTarget) => void }) {
  const { iconUrl, icon, name, desc, badge } = item
  const inst = useSkillStore((s) => matchSkill(s.installed, name))
  return (
    <div className="fcard clickable" onClick={() => onOpenDetail(inst ? { key: inst.key } : { name })}>
      {badge && <span className="fc-badge">{badge}</span>}
      <div className="fc-h">
        {iconUrl
          ? <img className="fc-ic" src={iconUrl} alt="" style={{ objectFit: 'cover' }} onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
          : <span className="fc-ic">{icon}</span>}
        <div className="fc-n" title={name}>{name}</div>
        {inst ? <InstalledCtl skill={inst} /> : <InstallBtn name={name} />}
      </div>
      <div className="fc-d">{desc}</div>
    </div>
  )
}

// 精选技能区（4 个一屏，「换一换」轮换池）。
function FeaturedSkills({ onOpenDetail }: { onOpenDetail: (target: SkillTarget) => void }) {
  const [off, setOff] = useState(0)
  const hubFeat = useCatalogStore((s) => s.skillFeatured)
  const pool: FeaturedItem[] = hubFeat.map((c) => ({ iconUrl: c.iconUrl, icon: (String(c.name || c.slug || '?').trim()[0] || '?').toUpperCase(), name: c.name || c.slug || '', desc: c.description || '', badge: c.skillhub_category_name || '' }))
  if (pool.length === 0) return null
  const n = Math.min(4, pool.length)
  const items = Array.from({ length: n }, (_, i) => pool[(off + i) % pool.length])
  return (
    <>
      <div className="flex-right" style={{ marginTop: 2 }}>
        <div className="sec-title">精选技能</div>
        <div className="rt" onClick={() => { setOff((o) => (o + n) % pool.length); toast('已换一批') }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12a9 9 0 019-9 9 9 0 016 2.3L21 8M21 12a9 9 0 01-9 9 9 9 0 01-6-2.3L3 16" /></svg>换一换
        </div>
      </div>
      <div className="card-grid g4">
        {items.map((it) => <FeaturedCard key={it.name} item={it} onOpenDetail={onOpenDetail} />)}
      </div>
    </>
  )
}

// 数字格式化（下载量）：≥1000 → k 缩写，与静态卡视觉一致。
function fmtNum(n?: number): string {
  const v = n ?? 0
  return v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
}

// Hub 镜像/搜索的商店卡（对象形，区别于静态元组卡 SkillHubCard）。图标优先 iconUrl，缺省取首字母。
function MirrorSkillCard({ card, onOpenDetail }: { card: SkillCard; onOpenDetail: (target: SkillTarget) => void }) {
  const inst = useSkillStore((s) => matchSkill(s.installed, card.name))
  const target: SkillTarget = inst ? { key: inst.key } : { name: card.slug || card.name }
  return (
    <div className="hcard clickable" onClick={() => onOpenDetail(target)}>
      <div className="hc-h">
        <span className="hc-ic" style={card.iconUrl ? { background: 'transparent', padding: 0, overflow: 'hidden' } : { background: '#6B7280' }}>
          {card.iconUrl
            ? <img src={card.iconUrl} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 'inherit' }} />
            : (card.name.trim()[0] || '?').toUpperCase()}
        </span>
        <div className="hc-n" title={card.name}>{card.name}</div>
        {inst ? <InstalledCtl skill={inst} /> : <InstallBtn name={card.slug || card.name} />}
      </div>
      <div className="hc-d">{card.description}</div>
      <div className="hc-foot">
        <span className="hc-stat"><IcDl />{fmtNum(card.downloads)}</span>
        <span className="hc-stat"><IcStar />{card.stars ?? 0}</span>
      </div>
    </div>
  )
}

// 技能搜索结果（WB-070）：调本地 /api/skills/search（后端优先 Hub 代理、回退本地 CLI），去抖 300ms。
function SkillSearchResults({ q, onOpenDetail }: { q: string; onOpenDetail: (target: SkillTarget) => void }) {
  const [results, setResults] = useState<SkillCard[]>([])
  const [loading, setLoading] = useState(false)
  useEffect(() => {
    const query = q.trim()
    if (!query) { setResults([]); setLoading(false); return }
    setLoading(true)
    let alive = true
    const t = setTimeout(() => {
      api.searchSkills(query, 24)
        .then((r) => { if (alive) setResults(r.results || []) })
        .catch(() => { if (alive) setResults([]) })
        .finally(() => { if (alive) setLoading(false) })
    }, 300)
    return () => { alive = false; clearTimeout(t) }
  }, [q])
  return (
    <>
      <div className="sec-title" style={{ marginTop: 2 }}>搜索「{q.trim()}」</div>
      {loading && results.length === 0
        ? <div className="hub-blank">搜索中…</div>
        : results.length === 0
          ? <div className="hub-blank">没有找到相关技能</div>
          : (
            <div className="card-grid g4">
              {results.map((c) => <MirrorSkillCard key={c.slug || c.name} card={c} onOpenDetail={onOpenDetail} />)}
            </div>
          )}
    </>
  )
}

// SkillHub 目录：分类过滤 + skillhub.cn 链接 + 排序 + 网格。
// WB-070：有 Hub 镜像（catalogStore.skillMirror，已连 Hub 并 pull）→ 用镜像的真实 369 技能，
// 按 Hub taxonomy 分类过滤；无 Hub 镜像时由 catalogStore 尝试真实 rankings，失败则诚实空态。
function SkillHubView({ onOpenDetail }: { onOpenDetail: (target: SkillTarget) => void }) {
  const mirror = useCatalogStore((s) => s.skillMirror)
  const skillCats = useCatalogStore((s) => s.skillCats)
  const [cat, setCat] = useState('全部')
  const cathead = (chips: string[]) => (
    <div className="sk-cathead">
      <div className="cats">
        {chips.map((c) => (
          <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>
        ))}
      </div>
      <div className="sk-cathead-r">
        <a className="sk-link" href="https://skillhub.cn" target="_blank" rel="noopener noreferrer"><IcExt />skillhub.cn</a>
        {/* 「综合评分」排序控件已移除（WB-181）：它只 toast、不排任何序，是个谎。
            真排序要等 WB-184 把这一段的三层数据源（Hub 镜像 / rankings / 静态兜底）收敛掉
            —— 后端 /skills/rankings 的 featured|hot|newest|recommended|trending 早已就绪，
            但镜像那条路不经 rankings，现在接会得到「切了排序但只有部分数据源生效」的新谎。 */}
      </div>
    </div>
  )

  if (mirror.length > 0) {
    const chips = ['全部', ...skillCats.filter((c) => c.count > 0).map((c) => c.name)]
    const list = mirror.filter((c) => cat === '全部' || c.skillhub_category_name === cat)
    return (
      <>
        {cathead(chips)}
        <div className="card-grid g4">
          {list.map((c) => <MirrorSkillCard key={c.slug} card={c} onOpenDetail={onOpenDetail} />)}
        </div>
        {list.length === 0 && <div className="hub-blank">该分类下暂无技能</div>}
      </>
    )
  }

  return (
    <>
      {cathead(['全部'])}
      <div className="hub-blank">当前无法获取 SkillHub 目录，请连接 Hub 或稍后重试</div>
    </>
  )
}

// 推荐（保留原简版目录卡）。
function RecoView() {
  const [cat, setCat] = useState('全部')
  const { SK_CATS, SK_GRID } = useCatalog()
  return (
    <>
      <div className="cats">
        {SK_CATS.map((c) => <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>)}
      </div>
      <div className="card-grid g4">
        {SK_GRID.filter((s) => cat === '全部' || s.category === cat).map((s) => (
          <div className="scard" key={s.slug}>
            <div className="sc-ic">{s.icon}</div>
            <div className="sc-info"><div className="sc-n">{s.name}</div><div className="sc-d">{s.description}</div></div>
            <RecoBtn skillKey={s.slug} displayName={s.name} />
          </div>
        ))}
      </div>
      {SK_GRID.filter((s) => cat === '全部' || s.category === cat).length === 0 && <div className="hub-blank">该分类下暂无技能</div>}
    </>
  )
}

// 「套件」段已整体删除（WB-182）—— 详见 catalog.ts 里 SKILLHUB_KITS 原处的说明：
// 前端 4 张静态卡（技能数手写）、后端零代码、DB 无表、Hub 无源、「安装套件」只 toast，
// 是整次技能审查里唯一 100% 虚构的功能。真要做等 WB-183 目录入库后在 Hub 建 kit 表。

function SkillsPane({ query, onOpenDetail }: { query: string; onOpenDetail: (target: SkillTarget) => void }) {
  const [seg, setSeg] = useState<'skillhub' | 'reco'>('skillhub')
  // 搜索态（顶栏搜索框有输入）→ 全屏搜索结果，替代精选/分段浏览（WB-070）。
  if (query.trim()) {
    return <div className="hub-pane show"><SkillSearchResults q={query} onOpenDetail={onOpenDetail} /></div>
  }
  return (
    <div className="hub-pane show">
      <FeaturedSkills onOpenDetail={onOpenDetail} />
      <div className="sk-seg">
        <div className={`sk-seg-item ${seg === 'reco' ? 'active' : ''}`.trim()} onClick={() => setSeg('reco')}>推荐</div>
        <div className={`sk-seg-item ${seg === 'skillhub' ? 'active' : ''}`.trim()} onClick={() => setSeg('skillhub')}>SkillHub</div>
      </div>
      {seg === 'skillhub' && <SkillHubView onOpenDetail={onOpenDetail} />}
      {seg === 'reco' && <RecoView />}
    </div>
  )
}

// 我安装的（从顶栏「我安装的 N」进入）：真实磁盘技能，点开进详情。
function InstalledPane({ onBack, onOpenDetail }: { onBack: () => void; onOpenDetail: (target: SkillTarget) => void }) {
  const installed = useSkillStore((s) => s.installed)
  const loading = useSkillStore((s) => s.loading)
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
          <div className="auto-empty-t">{loading ? '加载中…' : '还没有安装任何技能'}</div>
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: -6 }}>去 SkillHub 商店挑选并安装你需要的技能</div>
          <button className="btn-dark auto-empty-add" onClick={onBack}>去技能市场</button>
        </div>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 14 }}>
          {installed.map((skill) => <InstalledCard key={skill.key} skill={skill} onOpenDetail={onOpenDetail} />)}
        </div>
      )}
    </div>
  )
}

function InstalledCard({ skill, onOpenDetail }: { skill: InstalledSkill; onOpenDetail: (target: SkillTarget) => void }) {
  const tile = skillTile(skill.name)
  const [menu, setMenu] = useState(false)
  return (
    <div className={`inst-card clickable ${skill.disabled ? 'off' : ''}`.trim()} onClick={() => onOpenDetail({ key: skill.key })}>
      <span className="inst-ic" style={{ background: tile.color }}>{tile.icon}</span>
      <div style={{ minWidth: 0 }}>
        <div className="inst-n">{skill.name}{skill.disabled && <span className="hc-off" style={{ marginLeft: 6 }}>已关闭</span>}</div>
        <div className="inst-d">{skill.description || '已安装技能'}</div>
      </div>
      <div className="more-wrap" style={{ position: 'absolute', top: 8, right: 8 }} onClick={(e) => e.stopPropagation()}>
        <span className="inst-more" onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</span>
        {menu && <SkillMenu skill={skill} onClose={() => setMenu(false)} />}
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
  const { CONNS, CONN_META } = useCatalog()
  const connectors = useLoadoutStore((s) => s.connectors)
  // 真实连接态 → 卡片上的「● 已连接」。两类：OAuth（金山文档，问 kdocs 授权态）与
  // 表单型（WeKnora · WB-188，问 /api/knowledge/config 是否已配 key）。
  const [authed, setAuthed] = useState<Record<string, boolean>>({})
  const refreshAuth = () => {
    if (CONN_META['金山文档']?.oauth) {
      api.kdocsStatus().then((s) => setAuthed((m) => ({ ...m, 金山文档: s.authenticated }))).catch(() => {})
    }
    if (CONN_META['WeKnora知识库']?.configKind) {
      api.knowledgeConfig().then((c) => setAuthed((m) => ({ ...m, WeKnora知识库: c.configured }))).catch(() => {})
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
          // oauth / 表单型连接器显示实时连接态；其它显示静态标签。
          const badge = meta && ((meta.oauth || meta.configKind)
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
                  if (added) {
                    useLoadoutStore.getState().toggle('conn', n)
                    toast('已移除 · ' + n)
                  } else {
                    summonConnector(n)
                  }
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

function HubView({ hub }: { hub: Hub }) {
  // 「我的专家」子视图（WB-049）/「我安装的」子视图，仅在各自 tab 下有效；切 tab 退回目录。
  const [myExperts, setMyExperts] = useState(false)
  const [myInstalled, setMyInstalled] = useState(false)
  // 技能详情页（WB-056/057）：非空则占满 hub-body。已装用 {key}，未装用 {name} 预览。
  const [detailTarget, setDetailTarget] = useState<SkillTarget | null>(null)
  // 顶栏搜索框输入（WB-070）：目前用于技能 tab 的 SkillHub 搜索；切 tab 清空。
  const [query, setQuery] = useState('')
  const installedCount = useSkillStore((s) => s.installed.length)
  const loadSkills = useSkillStore((s) => s.load)
  const placeholder = { experts: '搜索专家职称或描述', skills: '搜索技能', connectors: '搜索连接器' }[hub]
  const actLabel = { experts: '我的专家', skills: '添加技能', connectors: '自定义连接器' }[hub]

  // 进入应用即拉一次已安装技能（顶栏计数、卡片安装态、我安装的页都依赖它）。
  useEffect(() => { void loadSkills() }, [loadSkills])

  const onAct = () => { if (hub === 'experts') setMyExperts(true); else toast(actLabel) }
  const currentTab = TABS.find((tab) => tab.id === hub)!
  const createSkill = () => {
    setDetailTarget(null)
    setMyInstalled(false)
    useLoadoutStore.getState().summonSkills(['skill-creator-guide'])
    useLoadoutStore.getState().setDraft('请帮我创建一个可以实现「……」的 skill')
    useChatStore.getState().startDraft('创建技能')
    useUIStore.getState().setView('home')
    toast('已载入技能创建指南 · 请描述你要创建的技能')
  }

  return (
    <section className="view active" data-view={hub}>
      <div className="hub-top">
        <div className="hub-tab active" aria-current="page">
          {currentTab.icon}{currentTab.label}
        </div>
        <div className="sp" />
        <div className="search-box" style={{ margin: 0, width: 260 }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
          <input placeholder={placeholder} value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        {hub === 'skills' ? (
          <>
            <button className={`hub-act ${myInstalled ? 'on' : ''}`.trim()} onClick={() => { setDetailTarget(null); setMyInstalled((v) => !v) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="4" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
              我安装的<span className="hub-act-n">{installedCount}</span>
            </button>
            <AddSkillControl
              onCreate={createSkill}
              onImported={() => { setQuery(''); setDetailTarget(null); setMyInstalled(true) }}
            />
          </>
        ) : (
          <button className="hub-act" onClick={onAct}>{actLabel}</button>
        )}
      </div>
      <div className="hub-body">
        {hub === 'experts' && (myExperts ? <MyExpertsPane onBack={() => setMyExperts(false)} /> : <ExpertsPane />)}
        {hub === 'skills' && (
          detailTarget
            ? <SkillDetail target={detailTarget} onBack={() => setDetailTarget(null)} />
            : myInstalled
              ? <InstalledPane onBack={() => setMyInstalled(false)} onOpenDetail={setDetailTarget} />
              : <SkillsPane query={query} onOpenDetail={setDetailTarget} />
        )}
        {hub === 'connectors' && <ConnectorsPane />}
      </div>
    </section>
  )
}

export function ExpertsView() {
  return <HubView hub="experts" />
}

export function SkillsView() {
  return <HubView hub="skills" />
}

export function ConnectorsView() {
  return <HubView hub="connectors" />
}
