// 技能详情页（WB-056 + WB-057）—— 渲染真实 SKILL.md，安装前也能看。
//
// 已安装：走本地详情 GET /api/skills/{key}；未安装：走预览 GET /api/skills/preview
// （后端临时下载读 SKILL.md，不落盘）。未安装时动作是「安装」，装完就地刷成已装态。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { SkillDetail as SkillDetailData } from '../../lib/types'
import { renderMarkdown } from '../../lib/markdown'
import { useSkillStore } from '../../stores/skillStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'

// 详情入口：已安装用 key；未安装用 slug/name（后端预览解析）。
export type SkillTarget = { key?: string; slug?: string; name?: string }

const IcFolder = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
const IcTrash = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg>
const IcEye = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></svg>
const IcCode = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6l-6 6 6 6M16 6l6 6-6 6" /></svg>
const IcSpin = () => <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg>

export function SkillDetail({ target, onBack }: { target: SkillTarget; onBack: () => void }) {
  const [data, setData] = useState<SkillDetailData | null>(null)
  const [loading, setLoading] = useState(true)
  const [reloadN, setReloadN] = useState(0)
  const [view, setView] = useState<'preview' | 'source'>('preview')
  const [menu, setMenu] = useState(false)
  const [installing, setInstalling] = useState(false)
  const toggle = useSkillStore((s) => s.toggle)
  const uninstall = useSkillStore((s) => s.uninstall)
  // 已装态从 store 取（toggle 联动）；预览态从 data 取。
  const storeSkill = useSkillStore((s) => (data?.key ? s.installed.find((x) => x.key === data.key) : undefined))

  useEffect(() => {
    let alive = true
    setLoading(true)
    const p = target.key
      ? api.skillDetail(target.key)
      : api.skillPreview({ slug: target.slug, name: target.name })
    p.then((r) => { if (alive) setData(r.skill) })
      .catch(() => { if (alive) { setData(null); toast('读取技能失败') } })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [target.key, target.slug, target.name, reloadN])

  useEffect(() => {
    if (!menu) return
    const h = () => setMenu(false)
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [menu])

  const installed = storeSkill ? true : (data?.installed ?? !!target.key)
  const disabled = storeSkill?.disabled ?? data?.disabled ?? false
  const name = data?.name ?? target.name ?? target.key ?? ''
  const localKey = data?.key || target.key || ''

  const tryIt = () => {
    useLoadoutStore.getState().summonSkills([name])
    useChatStore.getState().startDraft('试试 · ' + name)
    useUIStore.getState().setView('home')
    toast('已挂载「' + name + '」· 去试试')
  }
  const doInstall = async () => {
    setInstalling(true)
    await useSkillStore.getState().install(name, data?.slug ?? target.slug)
    setInstalling(false)
    setReloadN((n) => n + 1) // 就地刷新为已装态
  }
  const reveal = () => {
    if (localKey) api.revealSkill(localKey).then(() => toast('已打开文件夹')).catch(() => toast('无法打开目录'))
    setMenu(false)
  }
  const doUninstall = () => { if (localKey) void uninstall(localKey); setMenu(false); onBack() }

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
              <div className="skd-title">
                {name}
                {data.version && <span className="skd-ver">v{data.version}</span>}
                {!installed && <span className="skd-ver skd-preview">未安装 · 预览</span>}
              </div>
              {data.description && <div className="skd-desc">{data.description}</div>}
            </div>
            <div className="skd-actions">
              {installed ? (
                <>
                  <button className="hub-act" onClick={tryIt}>去试试</button>
                  <div
                    className={`sw ${disabled ? '' : 'on'}`.trim()} role="switch" aria-checked={disabled ? 'false' : 'true'}
                    title={disabled ? '已关闭 · 点击启用' : '已启用 · 点击关闭'}
                    onClick={() => toggle(localKey, !disabled)}
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
                </>
              ) : (
                <button className="btn-dark" disabled={installing} onClick={doInstall}>
                  {installing ? <><IcSpin /> 安装中…</> : '安装'}
                </button>
              )}
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
