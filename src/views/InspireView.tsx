import { WbButton } from '../components/ui/Primitives'
import { useState } from 'react'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'
import { Input, Segmented, Tag, Tooltip } from 'antd'
import { ProCard } from '@ant-design/pro-components'
import { clickable } from '../lib/a11y'

export function InspireView() {
  const [cat, setCat] = useState('全部')
  const [faved, setFaved] = useState<Set<number>>(new Set())
  const [query, setQuery] = useState('')
  const { INSP, INSP_CATS } = useCatalog()
  const shown = INSP.filter(([, title, desc]) => (!query || `${title} ${desc}`.toLowerCase().includes(query.toLowerCase())))

  const toggleFav = (i: number) => {
    setFaved((prev) => {
      const next = new Set(prev)
      if (next.has(i)) { next.delete(i); toast('已取消收藏') } else { next.add(i); toast('已收藏') }
      return next
    })
  }

  return (
    <section className="view active" data-view="inspire">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>灵感</h1>
            <div className="sub">常见工作流沉淀成可复用的任务起点</div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 6 }}>
            <WbButton className="cap-act" onClick={() => toast('我的收藏')}>我的收藏</WbButton>
            <Input.Search className="search-box" allowClear style={{ margin: 0, width: 220 }} placeholder="搜索灵感" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
        </div>

        <Segmented className="cats" style={{ marginTop: 20 }} value={cat} onChange={(value) => setCat(String(value))} options={INSP_CATS} />

        <div className="insp-cols">
          {shown.map(([bg, title, desc]) => {
            const i = INSP.findIndex((item) => item[1] === title)
            return <ProCard className="insp" key={title} hoverable styles={{ body: { padding: 0 } }} {...clickable} onClick={() => toast('打开灵感 · ' + title)}>
              <div className="insp-prev" style={{ height: 140, background: bg, display: 'grid', placeItems: 'center', padding: 16 }}>
                <span style={{ color: '#fff', fontWeight: 800, fontSize: 16, textShadow: '0 1px 4px rgba(0,0,0,.35)', textAlign: 'center' }}>{title}</span>
              </div>
              <div className="insp-body">
                <div className="insp-t">{title}<Tag className="html">HTML</Tag></div>
                <div className="insp-d">{desc}</div>
                <div className="insp-f">
                  <Tag className="off">官方</Tag>
                  <Tooltip title={faved.has(i) ? '取消收藏' : '收藏'}><WbButton className={`hea ${faved.has(i) ? 'on' : ''}`.trim()} onClick={(e) => { e.stopPropagation(); toggleFav(i) }}>
                    {faved.has(i) ? '♥' : '♡'}
                  </WbButton></Tooltip>
                </div>
              </div>
            </ProCard>
          })}
        </div>
      </div>
    </section>
  )
}
