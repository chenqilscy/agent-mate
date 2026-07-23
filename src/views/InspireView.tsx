import { WbButton } from '../components/ui/Primitives'
import { useEffect, useMemo, useState } from 'react'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'
import { useChatStore } from '../stores/chatStore'
import { useUIStore } from '../stores/uiStore'
import { api } from '../lib/api'
import type { InspirationTemplate } from '../data/catalog'
import { Empty, Input, Segmented, Tag, Tooltip } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'
import { AntModalBridge } from '../components/ui/AntModalBridge'

function InspirationPreview({ template, compact = false }: { template: InspirationTemplate; compact?: boolean }) {
  return (
    <div className={`insp-artifact insp-artifact--${template.previewTheme} ${compact ? 'compact' : ''}`.trim()}>
      <div className="insp-artifact-bar">
        <span>{template.preview.eyebrow}</span>
        <span className="insp-artifact-type">{template.artifactType}</span>
      </div>
      <div className="insp-artifact-copy">
        <div className="insp-artifact-title">{template.preview.headline}</div>
        <div className="insp-artifact-summary">{template.preview.summary}</div>
      </div>
      {template.preview.metrics && (
        <div className="insp-artifact-metrics">
          {template.preview.metrics.map(([value, label]) => (
            <div className="insp-artifact-metric" key={`${value}-${label}`}>
              <strong>{value}</strong><span>{label}</span>
            </div>
          ))}
        </div>
      )}
      <div className="insp-artifact-items">
        {template.preview.items.map((item, index) => (
          <span key={item}><b>{String(index + 1).padStart(2, '0')}</b>{item}</span>
        ))}
      </div>
    </div>
  )
}

function InspirationDetail({
  template,
  favorite,
  onFavorite,
  onClose,
  onLaunch,
}: {
  template: InspirationTemplate
  favorite: boolean
  onFavorite: () => void
  onClose: () => void
  onLaunch: () => void
}) {
  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal insp-modal" role="dialog" aria-modal="true" aria-label={template.title}>
        <div className="np-h insp-modal-head">
          <div className="insp-modal-heading">
            <div>{template.title}</div>
            <div className="insp-detail-tags">
              <Tag>{template.artifactType}</Tag>
              <Tag>{template.category}</Tag>
              <Tag>{template.source}</Tag>
            </div>
          </div>
          <Tooltip title={favorite ? '取消收藏' : '收藏'}>
            <WbButton
              className={`insp-modal-fav ${favorite ? 'on' : ''}`.trim()}
              aria-label={favorite ? `取消收藏 ${template.title}` : `收藏 ${template.title}`}
              onClick={onFavorite}
            >
              {favorite ? '♥' : '♡'}
            </WbButton>
          </Tooltip>
          <WbButton className="np-x" aria-label="关闭" onClick={onClose}>×</WbButton>
        </div>
        <div className="np-body insp-modal-body">
          <InspirationPreview template={template} />
          <div className="insp-detail-copy">
            <div className="sec-title">模板说明</div>
            <p>{template.description}</p>
            <div className="sec-title">真实执行要求</div>
            <p>{template.prompt}</p>
          </div>
        </div>
        <div className="np-foot insp-modal-foot">
          <span className="insp-modal-source">由 {template.source} 提供 · 执行时由真实 Agent 处理</span>
          <WbButton className="btn-dark" onClick={onLaunch}>一键做同款 ↗</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}

export function InspireView() {
  const [cat, setCat] = useState('全部')
  const [favorites, setFavorites] = useState<Set<string>>(new Set())
  const [favoriteOnly, setFavoriteOnly] = useState(false)
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<InspirationTemplate | null>(null)
  const { INSP_TEMPLATES, INSP_CATS } = useCatalog()

  useEffect(() => {
    let active = true
    void api.inspirationFavorites()
      .then((result) => { if (active) setFavorites(new Set(result.ids)) })
      .catch(() => { /* 旧后端/离线时保持诚实空收藏，不阻断目录浏览 */ })
    return () => { active = false }
  }, [])

  const shown = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    return INSP_TEMPLATES.filter((template) => {
      const categoryMatch = cat === '全部'
        || (cat === '精选' ? template.featured : template.category === cat)
      const queryMatch = !needle
        || `${template.title} ${template.description} ${template.category} ${template.artifactType}`
          .toLocaleLowerCase().includes(needle)
      return categoryMatch && queryMatch && (!favoriteOnly || favorites.has(template.id))
    })
  }, [INSP_TEMPLATES, cat, favoriteOnly, favorites, query])

  const toggleFav = async (template: InspirationTemplate) => {
    const favorite = !favorites.has(template.id)
    try {
      const result = await api.setInspirationFavorite(template.id, favorite)
      setFavorites(new Set(result.ids))
      toast(favorite ? '已收藏，可在“我的收藏”查看' : '已取消收藏')
    } catch {
      toast('收藏状态保存失败，请确认本地服务已启动')
    }
  }

  const launch = (template: InspirationTemplate) => {
    const chat = useChatStore.getState()
    chat.startDraft(template.title)
    setSelected(null)
    useUIStore.getState().setView('chat')
    void chat.send(template.prompt)
    toast(`已按「${template.title}」创建真实任务`)
  }

  return (
    <section className="view active" data-view="inspire">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>灵感</h1>
            <div className="sub">常见工作流沉淀成可复用的任务起点</div>
          </div>
          <div className="insp-actions">
            <WbButton
              className={`cap-act ${favoriteOnly ? 'on' : ''}`.trim()}
              aria-pressed={favoriteOnly}
              onClick={() => setFavoriteOnly((value) => !value)}
            >
              我的收藏<span className="cap-act-n">{favorites.size}</span>
            </WbButton>
            <Input.Search
              className="search-box"
              allowClear
              placeholder="搜索灵感"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>

        <Segmented
          className="cats"
          value={cat}
          onChange={(value) => setCat(String(value))}
          options={INSP_CATS}
        />

        {shown.length > 0 ? (
          <div className="insp-cols">
            {shown.map((template) => (
              <ProCard
                className="insp"
                key={template.id}
                hoverable
                styles={{ body: { padding: 0 } }}
                {...clickable}
                onClick={() => setSelected(template)}
              >
                <div className="insp-prev"><InspirationPreview template={template} compact /></div>
                <div className="insp-body">
                  <div className="insp-t">{template.title}<Tag className="html">{template.artifactType}</Tag></div>
                  <div className="insp-d">{template.description}</div>
                  <div className="insp-f">
                    <Tag className="off">{template.source}</Tag>
                    <Tooltip title={favorites.has(template.id) ? '取消收藏' : '收藏'}>
                      <WbButton
                        className={`hea ${favorites.has(template.id) ? 'on' : ''}`.trim()}
                        aria-label={favorites.has(template.id) ? `取消收藏 ${template.title}` : `收藏 ${template.title}`}
                        onClick={(event) => { event.stopPropagation(); void toggleFav(template) }}
                      >
                        {favorites.has(template.id) ? '♥' : '♡'}
                      </WbButton>
                    </Tooltip>
                  </div>
                </div>
              </ProCard>
            ))}
          </div>
        ) : (
          <Empty
            className="cap-blank"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={favoriteOnly ? '当前筛选下还没有收藏的灵感' : '没有匹配的灵感模板'}
          />
        )}
      </div>

      {selected && (
        <InspirationDetail
          template={selected}
          favorite={favorites.has(selected.id)}
          onFavorite={() => { void toggleFav(selected) }}
          onClose={() => setSelected(null)}
          onLaunch={() => launch(selected)}
        />
      )}
    </section>
  )
}
