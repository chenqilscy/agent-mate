import { toast } from '../stores/toastStore'
import { AUTO } from '../data/catalog'

export function AutomationView() {
  return (
    <section className="view active" data-view="automation">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>自动化</h1>
            <div className="sub">管理自动化任务并查看近期运行记录。</div>
          </div>
          <button className="btn-line" style={{ marginTop: 0 }} onClick={() => toast('已添加自动化任务')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>添加
          </button>
        </div>
        <div className="sec-title">从模板入手</div>
        <div className="card-grid g3">
          {AUTO.map(([ic, n, d]) => (
            <div className="tpl" key={n} onClick={() => toast('已添加自动化 · ' + n)}>
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
