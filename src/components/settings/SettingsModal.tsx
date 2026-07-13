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
import type { MemoryItem, StylePreset } from '../../lib/types'

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

// 记忆 panel（WB-148）：生成对话记忆开关 + 记忆列表(增删清) + 从其他 AI 导入(占位)。接 /api/memory。
function MemoryPanel() {
  const [enabled, setEnabled] = useState(false)
  const [items, setItems] = useState<MemoryItem[]>([])
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState('')

  const load = () => api.memory()
    .then((m) => { setEnabled(m.enabled); setItems(m.items); setLoaded(true) })
    .catch(() => { setLoaded(true); toast('加载记忆失败') })
  useEffect(() => { load() }, [])

  const toggle = async () => {
    const next = !enabled
    setEnabled(next)
    try { await api.setMemoryEnabled(next) } catch { setEnabled(!next); toast('操作失败') }
  }
  const add = async () => {
    const text = adding.trim()
    if (!text || busy) return
    setBusy(true)
    try { const row = await api.addMemory(text); setItems((xs) => [row, ...xs]); setAdding('') }
    catch { toast('添加失败（可能与已有记忆重复）') } finally { setBusy(false) }
  }
  const del = async (id: string) => {
    try { await api.deleteMemory(id); setItems((xs) => xs.filter((x) => x.id !== id)) } catch { toast('删除失败') }
  }
  const clear = async () => {
    if (!items.length || busy) return
    setBusy(true)
    try { await api.clearMemory(); setItems([]); toast('已清空记忆') } catch { toast('清空失败') } finally { setBusy(false) }
  }

  return (
    <div className="set-body">
      <div className="set-ptitle">记忆</div>
      <div className="set-pdesc">记忆让 WorkBuddy 记住你的偏好和习惯，对话越多越懂你。记忆仅本人可见。</div>

      <div className="set-field" style={{ marginTop: 16 }}>
        <div className="set-fhd">
          <div className="set-fname">生成对话记忆</div>
          <div className="set-fsub">开启后，WorkBuddy 会从对话中提取并记住相关事实，供未来对话更连贯、个性化。</div>
        </div>
        <button className={`set-switch ${enabled ? 'on' : ''}`.trim()} onClick={toggle} role="switch" aria-checked={enabled} aria-label="生成对话记忆">
          <span className="set-switch-dot" />
        </button>
      </div>

      <div className="set-flabel" style={{ display: 'flex', alignItems: 'center' }}>
        记忆内容
        {items.length > 0 && <button className="set-link" style={{ marginLeft: 'auto' }} onClick={clear}>清空</button>}
      </div>
      <div className="set-memadd">
        <input className="np-input" placeholder="手动添加一条记忆，如「我是一名前端工程师」" value={adding}
          maxLength={300} onChange={(e) => setAdding(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') add() }} />
        <button className="btn-dark" disabled={!adding.trim() || busy} onClick={add}>添加</button>
      </div>
      <div className="set-memlist">
        {!loaded && <div className="set-pdesc">加载中…</div>}
        {loaded && items.length === 0 && <div className="set-mem-empty">暂无记忆内容。{enabled ? '聊几轮后这里会出现从对话中提取的记忆。' : '开启上面的开关可从对话中自动积累。'}</div>}
        {items.map((m) => (
          <div className="set-mem" key={m.id}>
            <span className="set-mem-c">{m.content}</span>
            <span className="set-mem-src">{m.source === 'conversation' ? '来自对话' : '手动'}</span>
            <button className="set-mem-x" onClick={() => del(m.id)} aria-label="删除">×</button>
          </div>
        ))}
      </div>
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

            {tab === 'agent' && (
              <Soon
                title="智能体设置"
                desc="智能体（agent）默认行为：工具循环轮数上限、默认权限、计划模式等。"
              />
            )}

            {tab === 'shortcuts' && (
              <Soon
                title="快捷键"
                desc="常用操作的键盘快捷键一览与自定义。"
              />
            )}

            {tab === 'memory' && <MemoryPanel />}

            {tab === 'data' && (
              <Soon
                title="数据管理"
                desc="数据导出、清空与删除保护。涉及真实删除行为，需后端接口与二次确认。"
                bullets={['导出对话 / 工作空间', '删除保护、批量删除审批', '清空本地数据']}
              />
            )}

            {tab === 'security' && (
              <Soon
                title="安全中心"
                desc="统一管理工作空间内的进程安全、数据安全与系统授权。部分能力由本地运行时提供。"
                bullets={['沙箱安全：文件 / 命令 / 网络访问策略', '数据安全：安全网关、传输加密、删除保护', '系统级工具开关、内置运行时（Python/Node/Git Bash）', '审计中心：拦截 / 放行日志']}
              />
            )}

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
