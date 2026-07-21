import { WbButton } from '../components/ui/Primitives'
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
import { LocalSkillEditorModal } from '../components/skill/LocalSkillEditorModal'
import { api } from '../lib/api'
import type { InstalledSkill, SkillCard } from '../lib/types'
import { type ExpertTeam } from '../data/catalog'
import { useCatalog, useCatalogStore } from '../stores/catalogStore'
import { AntModalBridge } from '../components/ui/AntModalBridge'
import { Empty, Input, Spin, Tabs, Tag } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'

type CapabilityKind = 'experts' | 'skills' | 'connectors'

const SKILL_CATEGORY_LABELS: Record<string, string> = {
  'ai-agent': 'AI 智能体',
  'office-efficiency': '办公效率',
  'knowledge-management': '知识管理',
  'data-analysis': '数据分析',
  'design-media': '设计与媒体',
  'dev-programming': '开发编程',
  professional: '专业服务',
  'life-service': '生活服务',
  'content-creation': '内容创作',
  'it-ops-security': '运维与安全',
  'business-ops': '商业运营',
}

function skillCategoryLabel(category: string) {
  return SKILL_CATEGORY_LABELS[category] || category
}

// 详情弹窗的两种主体：Server 推荐的单个专家或独立 EXP_TEAMS 专家团。
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

function RecoBtn({ skillKey, displayName }: { skillKey: string; displayName: string }) {
  const inst = useSkillStore((s) => s.installed.find((item) => item.slug === skillKey && item.source === 'agentmate'))
  return inst ? <InstalledCtl skill={inst} /> : <InstallBtn name={displayName} slug={skillKey} catalog />
}

function SkillHubRecoBtn({ skillKey, displayName }: { skillKey: string; displayName: string }) {
  const inst = useSkillStore((s) => matchSkill(s.installed, skillKey || displayName))
  return inst ? <InstalledCtl skill={inst} /> : <InstallBtn name={displayName} slug={skillKey} />
}

function ExpertsPane() {
  const [sub, setSub] = useState<'专家' | '专家团'>('专家')
  const [cat, setCat] = useState('全部')
  const [detail, setDetail] = useState<Detail | null>(null)
  const { EXPERT_RECOMMENDATIONS, EXP_TEAMS, EXP_SCENES, EXP_CATS } = useCatalog()

  const experts = EXPERT_RECOMMENDATIONS.filter((expert) => cat === '全部' || expert.category === cat)
  const teams = EXP_TEAMS.filter((t) => cat === '全部' || t.category === cat)
  const empty = sub === '专家' ? experts.length === 0 : teams.length === 0

  return (
    <div className="cap-pane show">
      <div className="sec-title" style={{ marginTop: 2 }}>精选场景</div>
      <div className="scene-grid">
        {EXP_SCENES.map(([t, list]) => (
          <div className="scene-card" key={t} {...clickable} onClick={() => { setSub('专家团'); setCat('全部'); toast('打开场景 · ' + t) }}>
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
        <div className={`subtab ${sub === '专家' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setSub('专家')}>专家</div>
        <div className={`subtab ${sub === '专家团' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setSub('专家团')}>专家团</div>
        <div style={{ flex: 1 }} />
        <div className="subtab" style={{ fontSize: 12, color: 'var(--brand-600)' }}>最热</div>
        <div className="subtab" style={{ fontSize: 12 }}>最新</div>
      </div>
      <div className="cats">
        {EXP_CATS.map((c) => (
          <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} {...clickable} onClick={() => setCat(c)}>{skillCategoryLabel(c)}</div>
        ))}
      </div>

      {sub === '专家' ? (
        <div className="card-grid g4">
          {experts.map((expert) => (
            <ProCard className="ecard" hoverable styles={{ body: { display: 'contents' } }} key={expert.slug} {...clickable} onClick={() => setDetail({ type: 'expert', icon: expert.avatar, name: expert.name, subtitle: expert.subtitle, badge: expert.badge, category: expert.category, intro: expert.intro, strengths: expert.tags })}>
              <div className="ec-h">
                <div className="ec-av">{expert.avatar}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ec-n">{expert.name}{expert.badge && <span className="b">{expert.badge}</span>}</div>
                  <div className="ec-s">{expert.subtitle}</div>
                </div>
              </div>
              <div className="ec-d">{expert.intro}</div>
              <div className="ec-tags">{expert.tags.map((t) => <Tag className="ec-tag" key={t}>{t}</Tag>)}</div>
            </ProCard>
          ))}
        </div>
      ) : (
        <div className="card-grid g4">
          {teams.map((t) => (
            <ProCard className="ecard" hoverable styles={{ body: { display: 'contents' } }} key={t.name} {...clickable} onClick={() => setDetail({ type: 'team', team: t })}>
              <div className="ec-h">
                <div className="ec-av">{t.icon}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ec-n">{t.name}{t.badge && <span className="b">{t.badge}</span>}</div>
                  <div className="ec-s">{t.source}</div>
                </div>
              </div>
              <div className="ec-d">{t.intro}</div>
              <div className="ec-tags">{t.tags.map((x) => <Tag className="ec-tag" key={x}>{x}</Tag>)}</div>
            </ProCard>
          ))}
        </div>
      )}
      {empty && <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description={`该分类下暂无${sub}`} />}

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
  const names = detail.type === 'team' ? detail.team.members.map((m) => m.expert_slug) : [detail.name]

  const doSummon = (prompt?: string) => { summon(names, name, prompt); onClose() }

  return (
    <AntModalBridge onClose={onClose}>
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
          <WbButton className="np-x" onClick={onClose}>×</WbButton>
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
                <div className="pkc-row" key={p} {...clickable} onClick={() => doSummon(p)}>
                  <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--text-2)' }}>“{p}”</div>
                  <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>›</span>
                </div>
              ))}
            </>
          )}
        </div>
        <div className="np-foot">
          <WbButton className="btn-dark" style={{ flex: 1, justifyContent: 'center' }} onClick={() => doSummon()}>召唤 {name}</WbButton>
        </div>
      </div>
    </AntModalBridge>
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
const IcSpin = () => <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg>

// 展示名 → 图标/底色；只读真实推荐目录/本地市场，不回退静态 SkillHub 假统计卡。
function skillTile(name: string): { icon: string; color: string } {
  const catalog = useCatalogStore.getState()
  const inst = catalog.INSTALLED.find((x) => x[2] === name)
  if (inst) return { icon: inst[0], color: inst[1] }
  const recommended = catalog.SK_GRID.find((x) => x.name === name || x.slug === name)
  if (recommended) return { icon: recommended.icon, color: '#6B7280' }
  const market = catalog.skillMarketplace.find((x) => x.name === name || x.slug === name)
  if (market) return { icon: (market.name.trim()[0] || '?').toUpperCase(), color: '#6B7280' }
  return { icon: (name.trim()[0] || '?').toUpperCase(), color: '#6B7280' }
}

// 已安装技能卡片的「⋯」菜单：关闭(停用)/编辑/卸载 —— 真实调后端（skillStore）。
// 点任意处关闭（挂载后才注册监听，避免打开它的那一次点击立刻把自己关掉）。
function SkillMenu({ skill, onClose, onEdit }: { skill: InstalledSkill; onClose: () => void; onEdit?: (skill: InstalledSkill) => void }) {
  useEffect(() => {
    const h = () => onClose()
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [onClose])
  const store = useSkillStore.getState()
  return (
    <div className="card-menu open">
      <div className="more-item" {...clickable} onClick={() => store.toggle(skill.key, !skill.disabled)}>
        <IcPower />{skill.disabled ? '启用' : '关闭'}
      </div>
      {skill.source !== 'agentmate' && onEdit && (
        <div className="more-item" {...clickable} onClick={() => onEdit(skill)}><IcEdit />编辑</div>
      )}
      <div className="more-item div" {...clickable} onClick={() => store.uninstall(skill.key)}>
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
      <WbButton className="hc-more" aria-label="管理技能" onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</WbButton>
      {menu && <SkillMenu skill={skill} onClose={() => setMenu(false)} />}
    </div>
  )
}

// 安装按钮（未安装态）——真实安装，进行中转圈。
function InstallBtn({ name, slug, catalog = false }: { name: string; slug?: string; catalog?: boolean }) {
  const install = useSkillStore((s) => s.install)
  const installCatalog = useSkillStore((s) => s.installCatalog)
  const busyKey = catalog ? (slug || name) : name
  const busy = useSkillStore((s) => s.installing.includes(busyKey))
  return (
    <WbButton className="add-btn" aria-label="安装" disabled={busy} onClick={(e) => {
      e.stopPropagation()
      if (catalog && slug) void installCatalog(name, slug)
      else void install(name, slug)
    }}>
      {busy ? <IcSpin /> : <IcPlusSm />}
    </WbButton>
  )
}

// 数字格式化（下载量）：≥1000 → k 缩写，与静态卡视觉一致。
function fmtNum(n?: number): string {
  const v = n ?? 0
  return v >= 1000 ? `${Math.round(v / 1000)}k` : String(v)
}

// 本地 App 市场/搜索的第三方商店卡。图标优先 iconUrl，缺省取首字母。
function MirrorSkillCard({ card, onOpenDetail }: { card: SkillCard; onOpenDetail: (target: SkillTarget) => void }) {
  const inst = useSkillStore((s) => matchSkill(s.installed, card.slug || card.name))
  const target: SkillTarget = inst ? { key: inst.key } : { card }
  return (
    <ProCard className="hcard clickable" hoverable styles={{ body: { display: 'contents' } }} {...clickable} onClick={() => onOpenDetail(target)}>
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
    </ProCard>
  )
}

// 技能搜索结果：调本地 /api/skills/search，由 App 直接访问 SkillHub，去抖 300ms。
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
        ? <Spin className="cap-blank" tip="搜索中…" />
        : results.length === 0
          ? <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有找到相关技能" />
          : (
            <div className="card-grid g4">
              {results.map((c) => <MirrorSkillCard key={c.slug || c.name} card={c} onOpenDetail={onOpenDetail} />)}
            </div>
          )}
    </>
  )
}

// SkillHub 目录：分类过滤 + skillhub.cn 链接 + 排序 + 网格。
// 数据只来自本地 App 的真实 rankings；Server 登录状态不影响第三方市场（WB-215）。
function SkillHubView({ onOpenDetail }: { onOpenDetail: (target: SkillTarget) => void }) {
  const marketplace = useCatalogStore((s) => s.skillMarketplace)
  const skillCats = useCatalogStore((s) => s.skillCats)
  const [cat, setCat] = useState('全部')
  const cathead = (chips: string[]) => (
    <div className="sk-cathead">
      <div className="cats">
        {chips.map((c) => (
          <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} {...clickable} onClick={() => setCat(c)}>{skillCategoryLabel(c)}</div>
        ))}
      </div>
      <div className="sk-cathead-r">
        <a className="sk-link" href="https://skillhub.cn" target="_blank" rel="noopener noreferrer"><IcExt />skillhub.cn</a>
        {/* 「综合评分」排序控件已移除（WB-181）：它只 toast、不排任何序，是个谎。
            真排序要等 WB-184 把这一段的三层数据源（Server 镜像 / rankings / 静态兜底）收敛掉
            —— 后端 /skills/rankings 的 featured|hot|newest|recommended|trending 早已就绪，
            但镜像那条路不经 rankings，现在接会得到「切了排序但只有部分数据源生效」的新谎。 */}
      </div>
    </div>
  )

  if (marketplace.length > 0) {
    const chips = ['全部', ...skillCats.filter((c) => c.count > 0).map((c) => c.name)]
    const list = marketplace.filter((c) => cat === '全部' || c.skillhub_category_name === cat)
    return (
      <>
        {cathead(chips)}
        <div className="card-grid g4">
          {list.map((c) => <MirrorSkillCard key={c.slug} card={c} onOpenDetail={onOpenDetail} />)}
        </div>
        {list.length === 0 && <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description="该分类下暂无技能" />}
      </>
    )
  }

  return (
    <>
      {cathead(['全部'])}
      <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前无法获取 SkillHub 目录，请检查本地网络或稍后重试" />
    </>
  )
}

// 推荐位由 Server 配置；AgentMate 与 SkillHub 都复用真实的本地安装生命周期。
function RecoView({ onOpenDetail }: { onOpenDetail: (target: SkillTarget) => void }) {
  const [cat, setCat] = useState('全部')
  const { SK_CATS, SK_RECOMMENDATIONS } = useCatalog()
  const visible = SK_RECOMMENDATIONS.filter((s) => cat === '全部' || s.category === cat)
  return (
    <>
      <div className="cats">
        {SK_CATS.map((c) => <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} {...clickable} onClick={() => setCat(c)}>{skillCategoryLabel(c)}</div>)}
      </div>
      <div className="card-grid g4">
        {visible.map((s) => {
          const target: SkillTarget = s.provider === 'agentmate'
            ? { slug: s.slug, name: s.name, catalog: true }
            : { card: { slug: s.slug, name: s.name, description: s.description, category: s.category, source: 'SkillHub' } }
          return (
            <ProCard className="scard clickable" hoverable styles={{ body: { display: 'contents' } }} key={`${s.provider}:${s.slug}`} {...clickable} onClick={() => onOpenDetail(target)}>
              <div className="sc-ic">{s.icon}</div>
              <div className="sc-info"><div className="sc-n">{s.name}</div><div className="sc-d">{s.description}</div></div>
              {s.provider === 'agentmate'
                ? <RecoBtn skillKey={s.slug} displayName={s.name} />
                : <SkillHubRecoBtn skillKey={s.slug} displayName={s.name} />}
            </ProCard>
          )
        })}
      </div>
      {visible.length === 0 && <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description="该分类下暂无技能" />}
    </>
  )
}

// 「套件」段已整体删除（WB-182）—— 详见 catalog.ts 里 SKILLHUB_KITS 原处的说明：
// 前端 4 张静态卡（技能数手写）、后端零代码、DB 无表、Server 无源、「安装套件」只 toast，
// 是整次技能审查里唯一 100% 虚构的功能。真要做等 WB-183 目录入库后在 Server 建 kit 表。

function SkillsPane({ query, onOpenDetail }: { query: string; onOpenDetail: (target: SkillTarget) => void }) {
  const [seg, setSeg] = useState<'skillhub' | 'reco'>('skillhub')
  // 搜索态（顶栏搜索框有输入）→ 全屏搜索结果，替代精选/分段浏览（WB-070）。
  if (query.trim()) {
    return <div className="cap-pane show"><SkillSearchResults q={query} onOpenDetail={onOpenDetail} /></div>
  }
  return (
    <div className="cap-pane show">
      <div className="sk-seg">
        <div className={`sk-seg-item ${seg === 'reco' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setSeg('reco')}>推荐</div>
        <div className={`sk-seg-item ${seg === 'skillhub' ? 'active' : ''}`.trim()} {...clickable} onClick={() => setSeg('skillhub')}>SkillHub</div>
      </div>
      {seg === 'skillhub' && <SkillHubView onOpenDetail={onOpenDetail} />}
      {seg === 'reco' && <RecoView onOpenDetail={onOpenDetail} />}
    </div>
  )
}

// 我安装的（从顶栏「我安装的 N」进入）：真实磁盘技能，点开进详情。
function InstalledPane({ onBack, onOpenDetail }: { onBack: () => void; onOpenDetail: (target: SkillTarget) => void }) {
  const installed = useSkillStore((s) => s.installed)
  const loading = useSkillStore((s) => s.loading)
  const [editing, setEditing] = useState<InstalledSkill | null>(null)
  return (
    <div className="cap-pane show">
      <div className="ph" style={{ alignItems: 'center', marginTop: 2 }}>
        <WbButton className="btn-ghost" onClick={onBack}>‹ 技能市场</WbButton>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 12.5, color: 'var(--text-3)' }}>共 {installed.length} 个技能</span>
      </div>
      {installed.length === 0 ? (
        <Empty className="auto-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? '加载中…' : '还没有安装任何技能'}>
          <WbButton className="btn-dark auto-empty-add" onClick={onBack}>去技能市场</WbButton>
        </Empty>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 14 }}>
          {installed.map((skill) => <InstalledCard key={skill.key} skill={skill} onOpenDetail={onOpenDetail} onEdit={setEditing} />)}
        </div>
      )}
      {editing && <LocalSkillEditorModal skill={editing} onClose={() => setEditing(null)} />}
    </div>
  )
}

function InstalledCard({ skill, onOpenDetail, onEdit }: { skill: InstalledSkill; onOpenDetail: (target: SkillTarget) => void; onEdit: (skill: InstalledSkill) => void }) {
  const tile = skillTile(skill.name)
  const [menu, setMenu] = useState(false)
  return (
    <ProCard className={`inst-card clickable ${skill.disabled ? 'off' : ''}`.trim()} hoverable styles={{ body: { display: 'contents' } }} {...clickable} onClick={() => onOpenDetail({ key: skill.key })}>
      <span className="inst-ic" style={{ background: tile.color }}>{tile.icon}</span>
      <div style={{ minWidth: 0 }}>
        <div className="inst-n">{skill.name}{skill.disabled && <span className="hc-off" style={{ marginLeft: 6 }}>已关闭</span>}</div>
        <div className="inst-d">{skill.description || '已安装技能'}</div>
      </div>
      <div className="more-wrap" style={{ position: 'absolute', top: 8, right: 8 }} onClick={(e) => e.stopPropagation()}>
        <span className="inst-more" {...clickable} onClick={(e) => { e.stopPropagation(); setMenu((v) => !v) }}>⋯</span>
        {menu && <SkillMenu skill={skill} onClose={() => setMenu(false)} onEdit={onEdit} />}
      </div>
    </ProCard>
  )
}

// 连接器加入本会话的按钮（受控，反映真实 loadout；stopPropagation 不触发卡片详情）。
function ConnAddBtn({ on, onToggle }: { on: boolean; onToggle: (e: MouseEvent) => void }) {
  return (
    <WbButton type="button" className={`add-btn ${on ? 'on' : ''}`.trim()} aria-label={on ? '移除' : '添加'} onClick={onToggle}>
      {on ? (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 12l5 5L20 6" /></svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
      )}
    </WbButton>
  )
}

function ConnectorsPane() {
  const [detail, setDetail] = useState<[string, string, string] | null>(null)
  const { CONNECTOR_RECOMMENDATIONS, CONN_META } = useCatalog()
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
    <div className="cap-pane show">
      <div className="card-grid g2" style={{ marginTop: 6 }}>
        {CONNECTOR_RECOMMENDATIONS.map((connector) => {
          const { icon: ic, name: n, description: d, status } = connector
          const meta = CONN_META[n]
          const added = connectors.includes(n)
          const open = () => setDetail([ic, n, d])
          // oauth / 表单型连接器显示实时连接态；其它显示静态标签。
          const badge = meta ? ((meta.oauth || meta.configKind)
            ? (authed[n]
                ? <Tag className="conn-tag rdy">● 已连接</Tag>
                : <Tag className="conn-tag tok">{meta.statusLabel}</Tag>)
            : <Tag className={`conn-tag ${meta.status}`}>{meta.statusLabel}</Tag>)
            : <Tag className={`conn-tag ${status}`}>{status === 'rdy' ? '内置即用' : '需连接'}</Tag>
          return (
            <ProCard
              className="conn" key={n} hoverable styles={{ body: { display: 'contents' } }} role="button" tabIndex={0} onClick={open}
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
            </ProCard>
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
    <div className="cap-pane show">
      <div className="ph" style={{ alignItems: 'center', marginTop: 2 }}>
        <WbButton className="btn-ghost" onClick={onBack}>‹ 全部专家</WbButton>
        <div style={{ flex: 1 }} />
        {experts.length > 0 && <WbButton className="cap-act" onClick={() => setCreateOpen(true)}>＋ 创建专家</WbButton>}
      </div>

      {experts.length === 0 ? (
        <Empty className="auto-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有创建任何专家">
          <WbButton className="btn-dark auto-empty-add" onClick={() => setCreateOpen(true)}>＋ 创建专家</WbButton>
        </Empty>
      ) : (
        <div className="card-grid g4" style={{ marginTop: 14 }}>
          {experts.map((e) => (
            <ProCard className="ecard" key={e.id} styles={{ body: { display: 'contents' } }}>
              <div className="ec-h">
                <div className="ec-av">{e.avatar}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ec-n">{e.name}</div>
                  <div className="ec-s">{e.subtitle || '自定义专家'}</div>
                </div>
              </div>
              <div className="ec-d">{e.intro || e.persona}</div>
              <div className="ec-tags">{e.tags.map((t) => <Tag className="ec-tag" key={t}>{t}</Tag>)}</div>
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <WbButton className="btn-dark" style={{ flex: 1, justifyContent: 'center' }} onClick={() => summon([e.name], e.name)}>召唤</WbButton>
                <WbButton className="btn-ghost" onClick={() => { void remove(e.id); toast('已删除 · ' + e.name) }}>删除</WbButton>
              </div>
            </ProCard>
          ))}
        </div>
      )}

      <CreateExpertModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={() => setCreateOpen(false)} />
    </div>
  )
}

const TABS: { id: CapabilityKind; label: string; icon: ReactNode }[] = [
  { id: 'experts', label: '专家', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 4-6 8-6s8 2 8 6" /></svg> },
  { id: 'skills', label: '技能', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z" /></svg> },
  { id: 'connectors', label: '连接器', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 15l6-6M8 8L6 10a4 4 0 006 6l2-2M16 16l2-2a4 4 0 00-6-6l-2 2" /></svg> },
]

function CapabilityView({ kind }: { kind: CapabilityKind }) {
  // 「我的专家」子视图（WB-049）/「我安装的」子视图，仅在各自 tab 下有效；切 tab 退回目录。
  const [myExperts, setMyExperts] = useState(false)
  const [myInstalled, setMyInstalled] = useState(false)
  // 技能详情页（WB-056/057）：非空则占满 cap-body。已装用 {key}，未装用 {name} 预览。
  const [detailTarget, setDetailTarget] = useState<SkillTarget | null>(null)
  // 顶栏搜索框输入（WB-070）：目前用于技能 tab 的 SkillHub 搜索；切 tab 清空。
  const [query, setQuery] = useState('')
  const setView = useUIStore((s) => s.setView)
  const installedCount = useSkillStore((s) => s.installed.length)
  const loadSkills = useSkillStore((s) => s.load)
  const placeholder = { experts: '搜索专家职称或描述', skills: '搜索技能', connectors: '搜索连接器' }[kind]
  const actLabel = { experts: '我的专家', skills: '添加技能', connectors: '' }[kind]

  // 进入应用即拉一次已安装技能（顶栏计数、卡片安装态、我安装的页都依赖它）。
  useEffect(() => { void loadSkills() }, [loadSkills])

  const onAct = () => { if (kind === 'experts') setMyExperts(true) }
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
    <section className="view active" data-view={kind}>
      <div className="cap-top">
        <Tabs className="cap-tabs" activeKey={kind} onChange={(key) => setView(key as CapabilityKind)} items={TABS.map((item) => ({ key: item.id, label: <span className="cap-tab">{item.icon}{item.label}</span> }))} />
        <div className="sp" />
        <Input.Search className="search-box" allowClear style={{ margin: 0, width: 260 }} placeholder={placeholder} value={query} onChange={(e) => setQuery(e.target.value)} />
        {kind === 'skills' ? (
          <>
            <WbButton className={`cap-act ${myInstalled ? 'on' : ''}`.trim()} onClick={() => { setDetailTarget(null); setMyInstalled((v) => !v) }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="4" /><path d="M8.5 12l2.5 2.5 4.5-5" /></svg>
              我安装的<span className="cap-act-n">{installedCount}</span>
            </WbButton>
            <AddSkillControl
              onCreate={createSkill}
              onImported={() => { setQuery(''); setDetailTarget(null); setMyInstalled(true) }}
            />
          </>
        ) : actLabel ? (
          <WbButton className="cap-act" onClick={onAct}>{actLabel}</WbButton>
        ) : null}
      </div>
      <div className="cap-body">
        {kind === 'experts' && (myExperts ? <MyExpertsPane onBack={() => setMyExperts(false)} /> : <ExpertsPane />)}
        {kind === 'skills' && (
          detailTarget
            ? <SkillDetail target={detailTarget} onBack={() => setDetailTarget(null)} />
            : myInstalled
              ? <InstalledPane onBack={() => setMyInstalled(false)} onOpenDetail={setDetailTarget} />
              : <SkillsPane query={query} onOpenDetail={setDetailTarget} />
        )}
        {kind === 'connectors' && <ConnectorsPane />}
      </div>
    </section>
  )
}

export function ExpertsView() {
  return <CapabilityView kind="experts" />
}

export function SkillsView() {
  return <CapabilityView kind="skills" />
}

export function ConnectorsView() {
  return <CapabilityView kind="connectors" />
}
