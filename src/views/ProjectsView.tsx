import { toast } from '../stores/toastStore'
import { PROJ_TPL } from '../data/catalog'

export function ProjectsView() {
  return (
    <section className="view active" data-view="projects">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>项目</h1>
            <div className="sub">多人协同，打造超级团队</div>
            <button className="btn-line" onClick={() => toast('新建项目（M4 落地完整流程）')}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>新建项目
            </button>
          </div>
          <svg className="ph-illus" viewBox="0 0 300 150" aria-hidden="true">
            <rect width="300" height="150" rx="12" fill="#F4FAF7" />
            <circle cx="70" cy="80" r="22" fill="#CFEADC" opacity=".6" />
            <circle cx="150" cy="70" r="26" fill="#16B37A" opacity=".18" />
            <circle cx="230" cy="82" r="20" fill="#BFE3F5" opacity=".6" />
            <rect x="120" y="30" width="60" height="30" rx="8" fill="#fff" stroke="#DDE7E1" />
            <path d="M132 45h36M132 52h24" stroke="#B7C6BD" strokeWidth="2" />
          </svg>
        </div>

        <div className="sec-row">
          <div className="sec-title">我的项目</div>
          <div className="search-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input placeholder="搜索项目" />
          </div>
        </div>
        <div id="myProjList">
          <div className="my-proj" onClick={() => toast('打开项目 · 项目新手指引')}>
            <span className="t-ic" style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--brand-soft)', display: 'grid', placeItems: 'center', color: 'var(--brand-600)' }}>🧭</span>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 700 }}>项目新手指引</div>
              <div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>添加于 2 天前</div>
            </div>
            <span className="mp-more">⋮</span>
          </div>
        </div>

        <div className="sec-title">从模版创建</div>
        <div className="card-grid g4">
          {PROJ_TPL.map(([ic, n, d]) => (
            <div className="tpl" key={n} onClick={() => toast('从模板创建 · ' + n)}>
              <span className="t-ic">{ic}</span>
              <div>
                <div className="t-n">{n}</div>
                <div className="t-d">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
