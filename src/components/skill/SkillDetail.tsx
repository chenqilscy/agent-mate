// 技能详情页（WB-056）—— 渲染磁盘上真实的 SKILL.md。
//
// 数据来自后端 GET /api/skills/{key}（agent/skills_store.py 读磁盘）。提供预览/源码切换、
// 去试试（把技能挂进会话 loadout 开对话）、启用开关、打开文件夹、卸载。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { SkillDetail as SkillDetailData } from '../../lib/types'
import { renderMarkdown } from '../../lib/markdown'
import { useSkillStore } from '../../stores/skillStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'

const IcFolder = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
const IcTrash = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg>
const IcEye = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></svg>
const IcCode = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6l-6 6 6 6M16 6l6 6-6 6" /></svg>

export function SkillDetail({ skillKey, onBack }: { skillKey: string; onBack: () => void }) {
  const [data, setData] = useState<SkillDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [view, setView] = useState<'preview' | 'source'>('preview')
  const [menu, setMenu] = useState(false)
  const storeSkill = useSkillStore((s) => s.installed.find((x) => x.key === skillKey))
  const toggle = useSkillStore((s) => s.toggle)
  const uninstall = useSkillStore((s) => s.uninstall)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api.skillDetail(skillKey)
      .then((r) => { if (alive) setData(r.skill) })
      .catch(() => { if (alive) toast('读取技能失败') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [skillKey])

  useEffect(() => {
    if (!menu) return
    const h = () => setMenu(false)
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [menu])

  const disabled = storeSkill?.disabled ?? data?.disabled ?? false
  const name = data?.name ?? storeSkill?.name ?? skillKey

  const tryIt = () => {
    useLoadoutStore.getState().summonSkills([name])
    useChatStore.getState().startDraft('试试 · ' + name)
    useUIStore.getState().setView('home')
    toast('已挂载「' + name + '」· 去试试')
  }
  const reveal = () => {
    api.revealSkill(skillKey).then(() => toast('已打开文件夹')).catch(() => toast('无法打开目录'))
    setMenu(false)
  }
  const doUninstall = () => { void uninstall(skillKey); setMenu(false); onBack() }

  return (
    <div className="hub-pane show">
      <div className="skd-head">
        <button className="btn-ghost" onClick={onBack}>‹ 技能</button>
      </div>

      {loading && !data ? (
        <div className="hub-blank">加载中…</div>
      ) : !data ? (
        <div className="hub-blank">未找到该技能</div>
      ) : (
        <>
          <div className="skd-top">
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="skd-title">{name}{data.version && <span className="skd-ver">v{data.version}</span>}</div>
              {data.description && <div className="skd-desc">{data.description}</div>}
            </div>
            <div className="skd-actions">
              <button className="hub-act" onClick={tryIt}>去试试</button>
              <div
                className={`sw ${disabled ? '' : 'on'}`.trim()} role="switch" aria-checked={!disabled}
                title={disabled ? '已关闭 · 点击启用' : '已启用 · 点击关闭'}
                onClick={() => toggle(skillKey, !disabled)}
              />
              <div className="more-wrap" onClick={(e) => e.stopPropagation()}>
                <button className="hc-more" aria-label="更多" onClick={() => setMenu((v) => !v)}>⋯</button>
                {menu && (
                  <div className="card-menu open skd-menu">
                    <div className="more-item" onClick={reveal}><IcFolder />打开文件夹</div>
                    <div className="more-item div" onClick={doUninstall}><IcTrash />卸载</div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="skd-card">
            <div className="skd-viewtoggle">
              <button className={view === 'preview' ? 'on' : ''} aria-label="预览" title="预览" onClick={() => setView('preview')}><IcEye /></button>
              <button className={view === 'source' ? 'on' : ''} aria-label="源码" title="源码" onClick={() => setView('source')}><IcCode /></button>
            </div>
            {view === 'preview' ? (
              <div className="skd-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(data.body || data.markdown) }} />
            ) : (
              <pre className="skd-src">{data.markdown}</pre>
            )}
          </div>

          {data.references.length > 0 && (
            <div className="skd-refs">
              <span className="skd-refs-l">references</span>
              {data.references.map((r) => <span className="ec-tag" key={r}>{r}</span>)}
            </div>
          )}
        </>
      )}
    </div>
  )
}
