import { useState } from 'react'
import { toast } from '../stores/toastStore'
import { useCatalog } from '../stores/catalogStore'

export function InspireView() {
  const [cat, setCat] = useState('全部')
  const [faved, setFaved] = useState<Set<number>>(new Set())
  const { INSP, INSP_CATS } = useCatalog()

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
            <button className="cap-act" onClick={() => toast('我的收藏')}>我的收藏</button>
            <div className="search-box" style={{ margin: 0, width: 220 }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
              <input placeholder="搜索灵感" />
            </div>
          </div>
        </div>

        <div className="cats" style={{ marginTop: 20 }}>
          {INSP_CATS.map((c) => (
            <div key={c} className={`cat ${cat === c ? 'active' : ''}`.trim()} onClick={() => setCat(c)}>{c}</div>
          ))}
        </div>

        <div className="insp-cols">
          {INSP.map(([bg, title, desc], i) => (
            <div className="insp" key={title} onClick={() => toast('打开灵感 · ' + title)}>
              <div className="insp-prev" style={{ height: 140, background: bg, display: 'grid', placeItems: 'center', padding: 16 }}>
                <span style={{ color: '#fff', fontWeight: 800, fontSize: 16, textShadow: '0 1px 4px rgba(0,0,0,.35)', textAlign: 'center' }}>{title}</span>
              </div>
              <div className="insp-body">
                <div className="insp-t">{title}<span className="html">HTML</span></div>
                <div className="insp-d">{desc}</div>
                <div className="insp-f">
                  <span className="off">官方</span>
                  <span className={`hea ${faved.has(i) ? 'on' : ''}`.trim()} onClick={(e) => { e.stopPropagation(); toggleFav(i) }}>
                    {faved.has(i) ? '♥' : '♡'}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
