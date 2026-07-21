import { WbButton } from '../ui/Primitives'
// 技能详情页（WB-056 + WB-215）。
//
// 已安装：读取本地 SKILL.md/源码/references；未安装：只展示商店卡元数据，不下载技能包。
// 安装成功后就地切换为本地完整详情。
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { SkillCard, SkillDetail as SkillDetailData } from '../../lib/types'
import { renderMarkdown } from '../../lib/markdown'
import { useSkillStore } from '../../stores/skillStore'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { Alert, Empty, Spin } from 'antd'

// 详情入口：已安装用 key；AgentMate 自有目录用 catalog+slug；第三方未安装项必须带商店卡元数据。
export type SkillTarget = { key?: string; slug?: string; name?: string; catalog?: boolean; card?: SkillCard }

const IcFolder = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></svg>
const IcTrash = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6" /></svg>
const IcEye = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7-11-7-11-7z" /><circle cx="12" cy="12" r="3" /></svg>
const IcCode = () => <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6l-6 6 6 6M16 6l6 6-6 6" /></svg>
const IcSpin = () => <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9" /></svg>

export function SkillDetail({ target, onBack }: { target: SkillTarget; onBack: () => void }) {
  const [data, setData] = useState<SkillDetailData | null>(null)
  const [loading, setLoading] = useState(Boolean(target.key || target.catalog))
  const [installedKey, setInstalledKey] = useState(target.key || '')
  const [view, setView] = useState<'preview' | 'source'>('preview')
  const [menu, setMenu] = useState(false)
  const [installing, setInstalling] = useState(false)
  const toggle = useSkillStore((s) => s.toggle)
  const uninstall = useSkillStore((s) => s.uninstall)
  const storeSkill = useSkillStore((s) => {
    const identity = data?.key || installedKey || target.card?.slug || target.card?.name || ''
    const match = identity ? s.installed.find((x) => x.key === identity || x.slug === identity || x.name === identity) : undefined
    return target.catalog && match?.source !== 'agentmate' ? undefined : match
  })

  useEffect(() => {
    let alive = true
    if (!target.catalog && !installedKey) {
      setData(null)
      setLoading(false)
      return () => { alive = false }
    }
    setLoading(true)
    const p = target.catalog && target.slug
      ? api.skillCatalogDetail(target.slug)
      : api.skillDetail(installedKey)
    p.then((r) => { if (alive) setData(r.skill) })
      .catch(() => { if (alive) { setData(null); toast('读取技能失败') } })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [installedKey, target.slug, target.catalog])

  useEffect(() => {
    if (!menu) return
    const h = () => setMenu(false)
    document.addEventListener('click', h)
    return () => document.removeEventListener('click', h)
  }, [menu])

  const marketCard = target.card
  const installed = storeSkill ? true : (data?.installed ?? Boolean(installedKey))
  const disabled = storeSkill?.disabled ?? data?.disabled ?? false
  const name = data?.name ?? marketCard?.name ?? target.name ?? target.key ?? ''
  const description = data?.description ?? marketCard?.description ?? ''
  const version = data?.version ?? marketCard?.version ?? ''
  const source = data?.source ?? marketCard?.source ?? ''
  const category = data?.category ?? marketCard?.skillhub_category_name ?? marketCard?.category ?? ''
  const localKey = data?.key || installedKey || ''

  const tryIt = () => {
    useLoadoutStore.getState().summonSkills([data?.slug || localKey || name])
    useChatStore.getState().startDraft('试试 · ' + name)
    useUIStore.getState().setView('home')
    toast('已挂载「' + name + '」· 去试试')
  }
  const doInstall = async () => {
    setInstalling(true)
    if (target.catalog && target.slug) await useSkillStore.getState().installCatalog(name, target.slug)
    else await useSkillStore.getState().install(name, marketCard?.slug ?? target.slug)
    setInstalling(false)
    const installedSkill = useSkillStore.getState().installed.find((x) =>
      (x.slug === (marketCard?.slug ?? target.slug) || x.name === name)
      && (!target.catalog || x.source === 'agentmate'),
    )
    if (installedSkill) setInstalledKey(installedSkill.key)
  }
  const doUpgrade = async () => {
    const slug = data?.slug || target.slug || ''
    if (!slug) return
    setInstalling(true)
    await useSkillStore.getState().upgradeCatalog(name, slug)
    try {
      const refreshed = await api.skillCatalogDetail(slug)
      setData(refreshed.skill)
      if (refreshed.skill.key) setInstalledKey(refreshed.skill.key)
    } catch { /* toast 已由 store 处理，保留当前详情 */ }
    setInstalling(false)
  }
  const reveal = () => {
    if (localKey) api.revealSkill(localKey).then(() => toast('已打开文件夹')).catch(() => toast('无法打开目录'))
    setMenu(false)
  }
  const doUninstall = () => { if (localKey) void uninstall(localKey); setMenu(false); onBack() }

  return (
    <div className="cap-pane show">
      <div className="skd-head">
        <WbButton className="btn-ghost" onClick={onBack}>‹ 技能</WbButton>
      </div>

      {loading && !data ? (
        <Spin className="cap-blank" tip="加载中…" />
      ) : !data && !marketCard ? (
        <Empty className="cap-blank" image={Empty.PRESENTED_IMAGE_SIMPLE} description="未找到该技能" />
      ) : (
        <>
          <div className="skd-top">
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="skd-title">
                {name}
                {version && <span className="skd-ver">v{version}</span>}
                {source && <span className="skd-ver">{source}</span>}
                {!installed && <span className="skd-ver skd-preview">未安装</span>}
              </div>
              {description && <div className="skd-desc">{description}</div>}
            </div>
            <div className="skd-actions">
              {installed ? (
                <>
                  {data?.update_available && (
                    <WbButton className="btn-dark" disabled={installing || data.compatible === false} onClick={doUpgrade}>
                      {installing ? <><IcSpin /> 升级中…</> : `升级${data.catalog_version ? '到 v' + data.catalog_version : ''}`}
                    </WbButton>
                  )}
                  <WbButton className="cap-act" onClick={tryIt}>去试试</WbButton>
                  <div
                    className={`sw ${disabled ? '' : 'on'}`.trim()} role="switch" aria-checked={disabled ? 'false' : 'true'}
                    title={disabled ? '已关闭 · 点击启用' : '已启用 · 点击关闭'}
                    onClick={() => toggle(localKey, !disabled)}
                  />
                  <div className="more-wrap" onClick={(e) => e.stopPropagation()}>
                    <WbButton className="hc-more" aria-label="更多" onClick={() => setMenu((v) => !v)}>⋯</WbButton>
                    {menu && (
                      <div className="card-menu open skd-menu">
                        <div className="more-item" onClick={reveal}><IcFolder />打开文件夹</div>
                        <div className="more-item div" onClick={doUninstall}><IcTrash />卸载</div>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <WbButton className="btn-dark" disabled={installing || data?.compatible === false} onClick={doInstall}>
                  {installing ? <><IcSpin /> 安装中…</> : '安装'}
                </WbButton>
              )}
            </div>
          </div>

          {data?.compatible === false && (
            <Alert
              type="warning"
              showIcon
              message="当前 App 与此技能版本不兼容"
              description={data.compatibility_error || `需要 AgentMate ${data.min_app_version || '更高版本'}`}
            />
          )}

          {data && installed ? (
            <div className="skd-card">
              <div className="skd-viewtoggle">
                <WbButton className={view === 'preview' ? 'on' : ''} aria-label="预览" title="预览" onClick={() => setView('preview')}><IcEye /></WbButton>
                <WbButton className={view === 'source' ? 'on' : ''} aria-label="源码" title="源码" onClick={() => setView('source')}><IcCode /></WbButton>
              </div>
              {view === 'preview' ? (
                <div className="skd-md" dangerouslySetInnerHTML={{ __html: renderMarkdown(data.body || data.markdown) }} />
              ) : (
                <pre className="skd-src">{data.markdown}</pre>
              )}
            </div>
          ) : (
            <div className="skd-card skd-market-card">
              <div className="skd-market-title">技能介绍</div>
              <div className="skd-market-copy">{description || '该技能暂未提供描述信息。'}</div>
              <div className="skd-market-note">安装后可查看 SKILL.md、源码、引用文件并管理本地技能。</div>
            </div>
          )}

          {installed && data && data.references.length > 0 && (
            <div className="skd-refs">
              <span className="skd-refs-l">references</span>
              {data.references.map((r) => <span className="ec-tag" key={r}>{r}</span>)}
            </div>
          )}
          {(category || (data?.tools?.length ?? 0) > 0 || (marketCard?.tags?.length ?? 0) > 0 || marketCard?.downloads !== undefined || marketCard?.stars !== undefined) && (
            <div className="skd-refs">
              {category && <><span className="skd-refs-l">分类</span><span className="ec-tag">{category}</span></>}
              {(data?.tools?.length ?? 0) > 0 && <span className="skd-refs-l">工具</span>}
              {data?.tools?.map((tool) => <span className="ec-tag" key={tool}>{tool}</span>)}
              {(marketCard?.tags?.length ?? 0) > 0 && <span className="skd-refs-l">标签</span>}
              {marketCard?.tags?.map((tag) => <span className="ec-tag" key={tag}>{tag}</span>)}
              {marketCard?.downloads !== undefined && <span className="ec-tag">下载 {marketCard.downloads}</span>}
              {marketCard?.stars !== undefined && <span className="ec-tag">收藏 {marketCard.stars}</span>}
            </div>
          )}
        </>
      )}
    </div>
  )
}
