// 统一「设置中心」弹窗（WB-146）。左侧 11 标签导航 + 右侧内容区。
// 套现有 .np-overlay/.np-modal（token 化天然暗色，铁律#2/#3）；设置中心专属布局用 set- 前缀类。
// 首期：迁移已有（模型 = 内嵌 ModelConfigModal；个性化 = 外观切换）+ 账户真数据；
// 其余标签按截图做 UI，但未接后端的数据/开关诚实标注「即将上线」（铁律#1，不造假数据）。
import { useEffect, useState, type ReactNode } from 'react'
import { useUIStore, type SettingsTab } from '../../stores/uiStore'
import { useAuthStore } from '../../stores/authStore'
import { ModelConfigModal } from '../composer/ModelConfigModal'
import { toast } from '../../stores/toastStore'
import { api } from '../../lib/api'
import type { AgentSettings, AuditEntry, DataSummary, MemoryItem, MemorySearchHit, MemoryStats, MemoryTrace, StylePreset } from '../../lib/types'

type Tab = { id: SettingsTab; label: string; icon: ReactNode }

// 顺序即左侧导航顺序，对齐高保真截图。
const TABS: Tab[] = [
  { id: 'account', label: '账户管理', icon: <path d="M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6" /> },
  { id: 'system', label: '系统设置', icon: <><circle cx="12" cy="12" r="3.2" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M6 6l1.4 1.4M16.6 16.6L18 18M18 6l-1.4 1.4M7.4 16.6L6 18" /></> },
  { id: 'agent', label: '智能体设置', icon: <><rect x="5" y="7" width="14" height="11" rx="2" /><path d="M12 3v4M9 12h.01M15 12h.01M9 16h6" /></> },
  { id: 'shortcuts', label: '快捷键', icon: <><rect x="3" y="7" width="18" height="11" rx="2" /><path d="M7 11h.01M11 11h.01M15 11h.01M7 15h10" /></> },
  { id: 'memory', label: '记忆', icon: <><path d="M12 3a5 5 0 00-5 5v1a4 4 0 00-2 3.5A3.5 3.5 0 008 16v2a2 2 0 004 0" /><path d="M12 3a5 5 0 015 5v1a4 4 0 012 3.5A3.5 3.5 0 0116 16v2a2 2 0 01-4 0" /></> },
  { id: 'model', label: '模型', icon: <><path d="M4 7h11M4 12h16M4 17h7" /><circle cx="18" cy="7" r="2" /><circle cx="9" cy="17" r="2" /></> },
  { id: 'assistant', label: '助理设置', icon: <><circle cx="12" cy="12" r="9" /><path d="M8 13q4 3 8 0M9 9h.01M15 9h.01" /></> },
  { id: 'personalize', label: '个性化', icon: <><circle cx="13" cy="7" r="3" /><path d="M4 21c0-3 2.5-5 6-5M15 15l2 2 4-4" /></> },
  { id: 'data', label: '数据管理', icon: <><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" /></> },
  { id: 'security', label: '安全中心', icon: <path d="M12 3l7 3v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" /> },
  { id: 'help', label: '帮助与反馈', icon: <><circle cx="12" cy="12" r="9" /><path d="M9.5 9a2.5 2.5 0 115 1c0 1.5-2.5 2-2.5 3.5M12 17h.01" /></> },
]

function Icon({ children }: { children: ReactNode }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
}

// 未接后端的标签：诚实占位，说明「即将上线」，不造假数据/开关（铁律#1）。
function Soon({ title, desc, bullets }: { title: string; desc: string; bullets?: string[] }) {
  return (
    <div className="set-soon">
      <div className="set-ptitle">{title}<span className="set-soon-pill">即将上线</span></div>
      <div className="set-pdesc">{desc}</div>
      {bullets && (
        <ul className="set-soon-list">
          {bullets.map((b) => <li key={b}>{b}</li>)}
        </ul>
      )}
    </div>
  )
}

// 个性化 panel（WB-147）：外观 + 回复风格 + 自定义指令，接 /api/settings 真持久化、注入 agent。
function PersonalizePanel() {
  const theme = useUIStore((s) => s.theme)
  const setTheme = useUIStore((s) => s.setTheme)
  const [presets, setPresets] = useState<StylePreset[]>([])
  const [style, setStyle] = useState('default')
  const [custom, setCustom] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    api.settings()
      .then((s) => { setPresets(s.style_presets); setStyle(s.style); setCustom(s.custom_instructions); setLoaded(true) })
      .catch(() => { setLoaded(true); toast('加载个性化设置失败') })
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const r = await api.saveSettings({ style, custom_instructions: custom })
      setStyle(r.style); setCustom(r.custom_instructions); setDirty(false)
      toast('已保存个性化设置')
    } catch { toast('保存失败') } finally { setSaving(false) }
  }

  return (
    <div className="set-body">
      <div className="set-ptitle">个性化</div>
      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">外观</div>
          <div className="set-fsub">切换浅色 / 深色主题。</div>
        </div>
        <span className="seg2">
          <b className={theme === 'light' ? 'on' : ''} onClick={() => setTheme('light')}>浅色</b>
          <b className={theme === 'dark' ? 'on' : ''} onClick={() => setTheme('dark')}>深色</b>
        </span>
      </div>

      <div className="set-flabel">基本风格和语调<span className="set-fsub2">设置 AI 助手回复你的风格和语调。这不会影响 AI 助手的功能。</span></div>
      <div className="set-styles">
        {presets.map((p) => (
          <button key={p.key} className={`set-style ${style === p.key ? 'on' : ''}`.trim()} onClick={() => { setStyle(p.key); setDirty(true) }}>
            <span className="set-style-l">{p.label}</span>
            <span className="set-style-d">{p.desc}</span>
          </button>
        ))}
      </div>

      <div className="set-flabel">自定义指令<span className="set-fsub2">告诉 AI 助手你希望它始终遵循的规则和偏好，这会直接影响所有对话。</span></div>
      <textarea
        className="np-ta" placeholder={'例如："每次回答我之前都先说 ok，再接后续内容"'}
        value={custom} maxLength={2000} onChange={(e) => { setCustom(e.target.value); setDirty(true) }}
      />

      <div className="set-actions">
        <button className="btn-dark" disabled={!loaded || saving || !dirty} onClick={save}>{saving ? '保存中…' : '保存'}</button>
        <span className="set-pdesc" style={{ margin: 0 }}>这些设置会应用到你之后的所有对话。</span>
      </div>
    </div>
  )
}

// 记忆 panel（WB-148 + 认知记忆 WB-166/167 + 白盒管理 WB-168）：开关 + 概览 + 语义检索 playground +
// 活跃/已归档/已更替视图 + 每条记忆的强度条·重要度可调·状态·归档/回滚·溯源。接 /api/memory。
type MemView = 'active' | 'archived' | 'superseded'
const pct = (x: number | undefined) => Math.round((x ?? 0) * 100)

function MemoryPanel() {
  const [enabled, setEnabled] = useState(false)
  const [items, setItems] = useState<MemoryItem[]>([])
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [view, setView] = useState<MemView>('active')
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<MemorySearchHit[] | null>(null)
  const [hitsSemantic, setHitsSemantic] = useState(true)
  const [searching, setSearching] = useState(false)
  const [traceId, setTraceId] = useState<string | null>(null)
  const [trace, setTrace] = useState<MemoryTrace | null>(null)

  const load = (v: MemView = view) => api.memory(v)
    .then((m) => { setEnabled(m.enabled); setItems(m.items); if (m.stats) setStats(m.stats); setLoaded(true) })
    .catch(() => { setLoaded(true); toast('加载记忆失败') })
  useEffect(() => { load('active') }, [])
  const refreshStats = () => api.memoryStats().then(setStats).catch(() => {})

  const toggle = async () => {
    const next = !enabled
    setEnabled(next)
    try { await api.setMemoryEnabled(next) } catch { setEnabled(!next); toast('操作失败') }
  }
  const changeBackend = async (backend: string) => {
    try {
      const embed = await api.setEmbedBackend(backend)
      setStats((s) => (s ? { ...s, embed, semantic: embed.active != null } : s))
      toast(embed.active === 'glm' ? '已切换到在线 GLM embedding-3' : embed.active === 'local' ? '已切换到本地嵌入' : '当前无可用嵌入后端')
    } catch { toast('切换失败') }
  }
  const switchView = (v: MemView) => { setView(v); setLoaded(false); setTraceId(null); load(v) }
  const add = async () => {
    const text = adding.trim()
    if (!text || busy) return
    setBusy(true)
    try { const row = await api.addMemory(text); setItems((xs) => [row, ...xs]); setAdding(''); refreshStats() }
    catch { toast('添加失败（可能与已有记忆重复）') } finally { setBusy(false) }
  }
  const del = async (id: string) => {
    try { await api.deleteMemory(id); setItems((xs) => xs.filter((x) => x.id !== id)); refreshStats() } catch { toast('删除失败') }
  }
  const startEdit = (m: MemoryItem) => { setEditingId(m.id); setEditText(m.content) }
  const cancelEdit = () => { setEditingId(null); setEditText('') }
  const saveEdit = async (id: string) => {
    const text = editText.trim()
    if (!text) return
    try {
      const row = await api.editMemory(id, text)
      setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...row } : x)))
      cancelEdit()
    } catch { toast('保存失败（内容为空或与已有记忆重复）') }
  }
  const clear = async () => {
    if (busy || !window.confirm('清空全部记忆（含归档）？此操作不可撤销。')) return
    setBusy(true)
    try { await api.clearMemory(); setItems([]); refreshStats(); toast('已清空记忆') } catch { toast('清空失败') } finally { setBusy(false) }
  }
  const setImpLocal = (id: string, p: number) =>
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, importance: p / 100 } : x)))
  const commitImp = async (id: string, p: number) => {
    try { const row = await api.setMemoryImportance(id, p / 100); setItems((xs) => xs.map((x) => (x.id === id ? { ...x, ...row } : x))); refreshStats() }
    catch { toast('调整重要度失败') }
  }
  const archive = async (id: string) => {
    try { await api.archiveMemory(id); setItems((xs) => xs.filter((x) => x.id !== id)); refreshStats() } catch { toast('归档失败') }
  }
  const rollback = async (id: string) => {
    try { await api.rollbackMemory(id); setItems((xs) => xs.filter((x) => x.id !== id)); refreshStats() } catch { toast('恢复失败') }
  }
  const doSearch = async () => {
    const q = query.trim()
    if (!q || searching) return
    setSearching(true)
    try { const r = await api.searchMemory(q); setHits(r.hits); setHitsSemantic(r.semantic) }
    catch { toast('检索失败') } finally { setSearching(false) }
  }
  const showTrace = async (id: string) => {
    if (traceId === id) { setTraceId(null); return }
    try { const t = await api.memoryDetail(id); setTrace(t); setTraceId(id) } catch { toast('溯源失败') }
  }

  const emptyHint = view === 'active'
    ? (enabled ? '聊几轮后这里会出现从对话中提取的记忆。' : '开启上面的开关可从对话中自动积累，也可手动添加。')
    : (view === 'archived' ? '没有已归档的记忆。强度过低的记忆会自动归档到这里，可随时恢复。' : '没有被更替的记忆。当新事实覆盖旧记忆时，旧的会移到这里（保留溯源）。')

  return (
    <div className="set-body">
      <div className="set-ptitle">记忆</div>
      <div className="set-pdesc">记忆让 WorkBuddy 记住你的偏好和习惯，对话越多越懂你。记忆仅本人可见。</div>

      <div className="set-field" style={{ marginTop: 16 }}>
        <div className="set-fhd">
          <div className="set-fname">生成对话记忆</div>
          <div className="set-fsub">开启后，WorkBuddy 会从对话中提取并记住相关事实，供未来对话按相关性注入。</div>
        </div>
        <button className={`set-switch ${enabled ? 'on' : ''}`.trim()} onClick={toggle} role="switch" aria-checked={enabled} aria-label="生成对话记忆">
          <span className="set-switch-dot" />
        </button>
      </div>

      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">记忆嵌入</div>
          <div className="set-fsub">
            本地：离线、零成本（fastembed · bge-small-zh）。在线：GLM embedding-3（需在「模型管理」为智谱 GLM 配置密钥）。切换后旧记忆会在后续对话里自动重新嵌入。
            {stats?.embed?.configured === 'glm' && !stats.embed.glm && <span style={{ color: '#e5484d' }}>　未配置 GLM 密钥，当前暂用本地。</span>}
          </div>
        </div>
        <select className="np-input" style={{ width: 190, flexShrink: 0 }}
          value={stats?.embed?.configured ?? 'local'} onChange={(e) => changeBackend(e.target.value)}>
          <option value="local">本地（离线）</option>
          <option value="glm">在线 · GLM embedding-3</option>
        </select>
      </div>

      {stats && (
        <div className="set-mstat">
          <span><b>{stats.active}</b> 条活跃</span>
          <span>平均强度 <b>{pct(stats.avg_strength)}%</b></span>
          {stats.decaying > 0 && <span><b>{stats.decaying}</b> 条衰退中</span>}
          <span>语义检索 <b>{stats.embed?.active === 'glm' ? '在线 GLM' : stats.embed?.active === 'local' ? '本地' : '未启用'}</b></span>
        </div>
      )}

      <div className="set-flabel">检索 · 看哪些记忆与一句话最相关</div>
      <div className="set-msearch">
        <input className="np-input" placeholder="输入一句话，检索最相关的记忆…" value={query} maxLength={300}
          onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') doSearch() }} />
        <button className="btn-dark" disabled={!query.trim() || searching} onClick={doSearch}>检索</button>
        {hits && <button className="set-link" onClick={() => { setHits(null); setQuery('') }}>清除</button>}
      </div>
      {hits && (
        <div style={{ marginBottom: 14 }}>
          <div className="set-pdesc" style={{ margin: '0 0 6px' }}>{hitsSemantic ? '语义检索（按 相似度×强度 排序）' : '关键词匹配（未启用语义检索）'}</div>
          {hits.length === 0 && <div className="set-mem-empty">无匹配记忆。</div>}
          {hits.map((h) => (
            <div className="set-mhit" key={h.id}>
              <span className="set-mhit-c">{h.content}</span>
              <span className="set-mhit-s">{h.similarity != null ? `相似 ${pct(h.similarity)}% · ` : ''}强度 {pct(h.strength)}%</span>
            </div>
          ))}
        </div>
      )}

      <div className="set-flabel" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        记忆内容
        <div className="set-mviews">
          <button className={`set-mview ${view === 'active' ? 'on' : ''}`} onClick={() => switchView('active')}>活跃{stats ? ` (${stats.active})` : ''}</button>
          <button className={`set-mview ${view === 'archived' ? 'on' : ''}`} onClick={() => switchView('archived')}>已归档{stats ? ` (${stats.archived})` : ''}</button>
          {stats && stats.superseded > 0 && <button className={`set-mview ${view === 'superseded' ? 'on' : ''}`} onClick={() => switchView('superseded')}>已更替 ({stats.superseded})</button>}
        </div>
        {stats && stats.total > 0 && <button className="set-link" onClick={clear}>清空</button>}
      </div>

      {view === 'active' && (
        <div className="set-memadd">
          <input className="np-input" placeholder="手动添加一条记忆，如「我是一名前端工程师」" value={adding}
            maxLength={300} onChange={(e) => setAdding(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
          <button className="btn-dark" disabled={!adding.trim() || busy} onClick={add}>添加</button>
        </div>
      )}

      <div className="set-memlist">
        {!loaded && <div className="set-pdesc">加载中…</div>}
        {loaded && items.length === 0 && <div className="set-mem-empty">{emptyHint}</div>}
        {items.map((m) => (
          editingId === m.id ? (
            <div className="set-mem" key={m.id}>
              <input className="np-input" style={{ flex: 1, minWidth: 0 }} value={editText} maxLength={300} autoFocus
                onChange={(e) => setEditText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') saveEdit(m.id); if (e.key === 'Escape') cancelEdit() }} />
              <button className="set-mem-x" onClick={() => saveEdit(m.id)} disabled={!editText.trim()} aria-label="保存">✓</button>
              <button className="set-mem-x" onClick={cancelEdit} aria-label="取消">×</button>
            </div>
          ) : (
            <div className="set-mem" key={m.id}>
              <div className="set-mem-col">
                <span className="set-mem-c">{m.content}</span>
                <div className="set-mem-meta">
                  <div className="set-strength" title={`强度 ${pct(m.strength)}%（重要度 × 新鲜度 × 使用）`}><i style={{ width: `${pct(m.strength)}%` }} /></div>
                  <input type="range" className="set-mem-imp" min={0} max={100} value={pct(m.importance ?? 0.5)}
                    title={`重要度 ${pct(m.importance ?? 0.5)}%`} aria-label="重要度"
                    onChange={(e) => setImpLocal(m.id, Number(e.target.value))}
                    onMouseUp={(e) => commitImp(m.id, Number((e.target as HTMLInputElement).value))}
                    onTouchEnd={(e) => commitImp(m.id, Number((e.target as HTMLInputElement).value))} />
                  <span className="set-mem-src">{m.source === 'conversation' ? '来自对话' : '手动'}</span>
                  {m.status === 'superseded' && <span className="set-badge">已更替</span>}
                  {m.status === 'archived' && <span className="set-badge">已归档</span>}
                  {view === 'active' ? (
                    <>
                      <button className="set-mem-x" onClick={() => startEdit(m)} title="编辑" aria-label="编辑">✎</button>
                      <button className="set-mem-x" onClick={() => archive(m.id)} title="归档" aria-label="归档">⊟</button>
                      <button className="set-mem-x" onClick={() => del(m.id)} title="删除" aria-label="删除">×</button>
                    </>
                  ) : (
                    <>
                      {view === 'superseded' && <button className="set-mem-x" onClick={() => showTrace(m.id)} title="溯源" aria-label="溯源">↪</button>}
                      <button className="set-mem-x" onClick={() => rollback(m.id)} title="恢复为活跃" aria-label="恢复">↩</button>
                      <button className="set-mem-x" onClick={() => del(m.id)} title="删除" aria-label="删除">×</button>
                    </>
                  )}
                </div>
                {traceId === m.id && trace && (
                  <div className="set-mtrace">
                    {trace.superseded_by ? <>被新记忆取代：「{trace.superseded_by.content}」</> : '暂无取代它的更新记忆。'}
                  </div>
                )}
              </div>
            </div>
          )
        ))}
      </div>
    </div>
  )
}

// 数据管理 panel（WB-149）：数据概览 + 导出(下载 JSON) + 清空个人对话(二次确认)。接 /api/data。
function DataPanel() {
  const [sum, setSum] = useState<DataSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)

  const load = () => api.dataSummary().then(setSum).catch(() => toast('加载数据概览失败'))
  useEffect(() => { load() }, [])

  const doExport = async () => {
    setBusy(true)
    try {
      const data = await api.dataExport()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `workbuddy-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('已导出数据')
    } catch { toast('导出失败') } finally { setBusy(false) }
  }
  const doClear = async () => {
    setBusy(true)
    try { const r = await api.clearConversations(); toast(`已清空 ${r.removed} 条个人对话`); setConfirming(false); load() }
    catch { toast('清空失败') } finally { setBusy(false) }
  }

  return (
    <div className="set-body">
      <div className="set-ptitle">数据管理</div>
      <div className="set-pdesc">你的数据存在本机。可随时导出备份，或清理不再需要的记录。</div>

      <div className="set-stats">
        <div className="set-stat"><span className="set-stat-n">{sum?.sessions ?? '—'}</span><span className="set-stat-l">会话</span></div>
        <div className="set-stat"><span className="set-stat-n">{sum?.messages ?? '—'}</span><span className="set-stat-l">消息</span></div>
        <div className="set-stat"><span className="set-stat-n">{sum?.memories ?? '—'}</span><span className="set-stat-l">记忆</span></div>
      </div>

      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">导出数据</div>
          <div className="set-fsub">下载一份包含你的会话、设置与记忆的 JSON 备份。</div>
        </div>
        <button className="btn-dark" disabled={busy} onClick={doExport}>导出</button>
      </div>

      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">清空个人对话记录</div>
          <div className="set-fsub">删除全部个人对话（不含项目、助理、自动化会话）。此操作不可恢复。</div>
        </div>
        {confirming
          ? <span className="set-confirm">
              <button className="btn-ghost" disabled={busy} onClick={() => setConfirming(false)}>取消</button>
              <button className="btn-ghost danger-b" disabled={busy} onClick={doClear}>确认清空</button>
            </span>
          : <button className="btn-ghost danger-b" disabled={busy || !sum} onClick={() => setConfirming(true)}>清空</button>}
      </div>

      <Soon title="删除保护 · 批量删除审批" desc="需要执行层接管删除行为才能真正生效，暂不做以免成为「存了不生效」的假开关。" />
    </div>
  )
}

// 智能体设置 panel（WB-150）：工具步数上限 + 回复发散度，接 /api/settings/agent，run_chat 真读真用。
function AgentPanel() {
  const [s, setS] = useState<AgentSettings | null>(null)
  const [rounds, setRounds] = useState(12)
  const [temp, setTemp] = useState(0.6)
  const [dirty, setDirty] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.agentSettings()
      .then((d) => { setS(d); setRounds(d.max_rounds); setTemp(d.temperature) })
      .catch(() => toast('加载智能体设置失败'))
  }, [])

  const save = async () => {
    setSaving(true)
    try {
      const d = await api.saveAgentSettings({ max_rounds: rounds, temperature: temp })
      setS(d); setRounds(d.max_rounds); setTemp(d.temperature); setDirty(false)
      toast('已保存智能体设置')
    } catch { toast('保存失败') } finally { setSaving(false) }
  }

  if (!s) return <div className="set-body"><div className="set-ptitle">智能体设置</div><div className="set-pdesc">加载中…</div></div>
  const [rMin, rMax] = s.limits.max_rounds
  const [tMin, tMax] = s.limits.temperature
  return (
    <div className="set-body">
      <div className="set-ptitle">智能体设置</div>
      <div className="set-pdesc">调节智能体的执行行为。改动对之后新开的对话生效。</div>

      <div className="set-slider">
        <div className="set-fhd">
          <div className="set-fname">最多连续工具步数<span className="set-fsub2">一次回答里智能体最多连续调用工具的轮数。调小更省 token，调大更能自动完成复杂任务。默认 {s.defaults.max_rounds}。</span></div>
          <span className="set-slval">{rounds}</span>
        </div>
        <input type="range" min={rMin} max={rMax} step={1} value={rounds}
          onChange={(e) => { setRounds(Number(e.target.value)); setDirty(true) }} />
      </div>

      <div className="set-slider">
        <div className="set-fhd">
          <div className="set-fname">回复发散度（temperature）<span className="set-fsub2">越低越稳定确定、越高越有创造性。默认 {s.defaults.temperature}。</span></div>
          <span className="set-slval">{temp.toFixed(1)}</span>
        </div>
        <input type="range" min={tMin} max={tMax} step={0.1} value={temp}
          onChange={(e) => { setTemp(Number(e.target.value)); setDirty(true) }} />
      </div>

      <div className="set-actions">
        <button className="btn-dark" disabled={saving || !dirty} onClick={save}>{saving ? '保存中…' : '保存'}</button>
        <button className="btn-ghost" disabled={saving} onClick={() => { setRounds(s.defaults.max_rounds); setTemp(s.defaults.temperature); setDirty(true) }}>恢复默认</button>
      </div>
    </div>
  )
}

// 安全中心 panel（WB-152）：命令黑名单(真拦截 run_command) + 审计日志(真记录)。接 /api/security。
function SecurityPanel() {
  const [blocklist, setBlocklist] = useState<string[]>([])
  const [audit, setAudit] = useState<AuditEntry[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const loadAll = () => {
    api.securityPolicy().then((p) => setBlocklist(p.command_blocklist)).catch(() => toast('加载安全策略失败'))
    api.securityAudit().then((a) => setAudit(a.items)).catch(() => {})
  }
  useEffect(() => { loadAll() }, [])

  const persist = async (next: string[]) => {
    setBusy(true)
    try { const p = await api.saveSecurityPolicy(next); setBlocklist(p.command_blocklist) }
    catch { toast('保存失败'); loadAll() } finally { setBusy(false) }
  }
  const add = () => {
    const v = draft.trim()
    if (!v || blocklist.includes(v)) { setDraft(''); return }
    setDraft(''); persist([...blocklist, v])
  }
  const remove = (p: string) => persist(blocklist.filter((x) => x !== p))
  const clearAudit = async () => {
    setBusy(true)
    try { await api.clearAudit(); setAudit([]); toast('已清空审计记录') } catch { toast('清空失败') } finally { setBusy(false) }
  }

  return (
    <div className="set-body">
      <div className="set-ptitle">安全中心</div>
      <div className="set-pdesc">统一管理工作空间内的进程安全与授权。安全能力由本地运行时提供。</div>

      <div className="set-flabel">命令安全策略<span className="set-fsub2">命中黑名单的命令会被真拦截、不执行（大小写不敏感的子串匹配）。规则如 <code>rm -rf</code>、<code>shutdown</code>。</span></div>
      <div className="set-memadd">
        <input className="np-input" placeholder="添加拦截规则（命令子串），如 rm -rf" value={draft} maxLength={200}
          onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
        <button className="btn-dark" disabled={!draft.trim() || busy} onClick={add}>添加</button>
      </div>
      <div className="set-chips">
        {blocklist.length === 0 && <span className="set-mem-empty">暂无拦截规则。添加后 agent 执行命中的命令会被拦截。</span>}
        {blocklist.map((p) => (
          <span className="set-chip2" key={p}>{p}<button className="set-chip2-x" onClick={() => remove(p)} aria-label="移除">×</button></span>
        ))}
      </div>

      <div className="set-flabel" style={{ display: 'flex', alignItems: 'center' }}>
        审计中心<span className="set-fsub2" style={{ flex: 1 }}>命令执行 / 拦截记录（最近 100 条）。</span>
        {audit.length > 0 && <button className="set-link" onClick={clearAudit}>清空记录</button>}
      </div>
      <div className="set-memlist">
        {audit.length === 0 && <div className="set-mem-empty">暂无审计记录。agent 执行命令后这里会出现记录。</div>}
        {audit.map((a) => (
          <div className="set-audit" key={a.id}>
            <span className={`set-badge ${a.action === 'blocked' ? 'blk' : 'ok'}`.trim()}>{a.action === 'blocked' ? '已拦截' : '已执行'}</span>
            <span className="set-audit-d" title={a.detail}>{a.tool} · {a.detail}</span>
            <span className="set-audit-t">{new Date(a.created_at * 1000).toLocaleString()}</span>
          </div>
        ))}
      </div>

      <Soon title="文件安全 · 网络域名规则 · 数据网关" desc="路径白/黑名单、网络访问域名规则、数据流转网关需执行层进一步接管，暂不做以免成为「存了不生效」的假开关。" />
    </div>
  )
}

export function SettingsModal({ onClose }: { onClose: () => void }) {
  const tab = useUIStore((s) => s.settingsTab)
  const setTab = useUIStore((s) => s.setSettingsTab)
  const setView = useUIStore((s) => s.setView)
  const me = useAuthStore((s) => s.me)
  const loggedIn = useAuthStore((s) => s.loggedIn)
  const logout = useAuthStore((s) => s.logout)

  return (
    <div className="np-overlay open" style={{ zIndex: 175 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal set-modal" role="dialog" aria-modal="true" aria-label="设置">
        <div className="set-layout">
          <aside className="set-nav">
            <div className="set-nav-title">设置</div>
            {TABS.map((t) => (
              <div
                key={t.id}
                className={`set-nav-item ${tab === t.id ? 'active' : ''}`.trim()}
                onClick={() => setTab(t.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setTab(t.id) } }}
              >
                <span className="set-nav-ic"><Icon>{t.icon}</Icon></span>
                {t.label}
              </div>
            ))}
          </aside>

          <div className="set-panel">
            <button className="np-x set-x" onClick={onClose} aria-label="关闭">×</button>

            {tab === 'account' && (
              <div className="set-body">
                <div className="set-ptitle">账户管理</div>
                <div className="set-card">
                  <div className="set-row">
                    <span className="set-k">用户名</span>
                    <span className="set-v">{me?.name ?? '奇'}</span>
                  </div>
                  <div className="set-row">
                    <span className="set-k">套餐</span>
                    <span className="set-v">{me?.plan ?? '体验版'}</span>
                  </div>
                  <div className="set-row">
                    <span className="set-k">角色</span>
                    <span className="set-v">{me?.role ?? '—'}</span>
                  </div>
                  <div className="set-row">
                    <span className="set-k">模型凭据</span>
                    <span className="set-v">{me?.llm_configured ? '已配置' : '未配置'}</span>
                  </div>
                </div>
                <div className="set-actions">
                  {loggedIn
                    ? <button className="btn-ghost danger-b" onClick={() => { onClose(); void logout() }}>退出登录</button>
                    : <span className="set-pdesc">当前以本机默认身份使用，登录后可跨设备协作。</span>}
                </div>
              </div>
            )}

            {tab === 'model' && (
              <div className="set-body set-body--flush">
                <div className="set-ptitle set-ptitle--pad">模型</div>
                <ModelConfigModal embedded onClose={onClose} />
              </div>
            )}

            {tab === 'personalize' && <PersonalizePanel />}

            {tab === 'assistant' && (
              <div className="set-body">
                <div className="set-ptitle">助理设置</div>
                <div className="set-pdesc">助理的名字、人格、模型、权限、绑定工作空间与外部渠道，在「助理」页逐个管理。</div>
                <div className="set-actions">
                  <button className="btn-dark" onClick={() => { onClose(); setView('assistant') }}>前往助理管理</button>
                </div>
              </div>
            )}

            {tab === 'system' && (
              <div className="set-body">
                <Soon
                  title="系统设置"
                  desc="应用级偏好。语言 / 字号会随主题在明暗双主题下生效；带持久化的项需后端支持。"
                  bullets={['显示语言、字体大小', '技能自动更新、非高风险技能自动安装', '锁屏远程、默认工作空间存储路径', '体验优化计划']}
                />
              </div>
            )}

            {tab === 'agent' && <AgentPanel />}

            {tab === 'shortcuts' && (
              <Soon
                title="快捷键"
                desc="常用操作的键盘快捷键一览与自定义。"
              />
            )}

            {tab === 'memory' && <MemoryPanel />}

            {tab === 'data' && <DataPanel />}

            {tab === 'security' && <SecurityPanel />}

            {tab === 'help' && (
              <div className="set-body">
                <div className="set-ptitle">帮助与反馈</div>
                <div className="set-pdesc">遇到问题或有建议？下面是常用入口。</div>
                <div className="set-actions" style={{ flexWrap: 'wrap', gap: 10 }}>
                  <button className="btn-ghost" onClick={() => toast('反馈渠道即将上线')}>提交反馈</button>
                  <button className="btn-ghost" onClick={() => toast('帮助文档即将上线')}>查看帮助文档</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
