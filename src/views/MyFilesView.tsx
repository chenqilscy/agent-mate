import { WbButton, WbInput } from '../components/ui/Primitives'
import { useState } from 'react'
import { toast } from '../stores/toastStore'

export function MyFilesView() {
  const [tab, setTab] = useState<'results' | 'cloud'>('results')
  const [fav, setFav] = useState(false)

  return (
    <section className="view active" data-view="myfiles">
      <div className="page-scroll">
        <h1 style={{ fontSize: 22, fontWeight: 800 }}>我的文件</h1>
        <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6 }}>快捷查看任务成果，上传到云端网盘开启跨端同步。</div>

        <div className="mf-tabs">
          <div className={`mf-tab ${tab === 'results' ? 'active' : ''}`.trim()} onClick={() => setTab('results')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>任务成果
          </div>
          <div className={`mf-tab ${tab === 'cloud' ? 'active' : ''}`.trim()} onClick={() => setTab('cloud')}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 18a4 4 0 010-8 6 6 0 0111.6-1.5A4.5 4.5 0 0117 18z" /></svg>云端网盘
          </div>
        </div>

        {tab === 'results' && (
          <div>
            <div className="mf-filter">
              <div className="mf-type" onClick={() => toast('筛选类型')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 5h18l-7 8v6l-4-2v-4z" /></svg>
                <span className="ft-lb">全部类型</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ width: 11, height: 11 }}><path d="M6 9l6 6 6-6" /></svg>
              </div>
              <div className="search-box" style={{ margin: 0, width: 260 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
                <WbInput placeholder="搜索文件、任务或工作空间" />
              </div>
              <label className={`mf-check ${fav ? 'on' : ''}`.trim()} onClick={() => setFav((v) => !v)}>
                <span className="bx">✓</span>我的收藏
              </label>
            </div>
            <div className="mf-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg>暂无文件
            </div>
          </div>
        )}

        {tab === 'cloud' && (
          <div>
            <div className="mf-filter">
              <WbButton className="cap-act" onClick={() => toast('新建文件夹')}>新建文件夹</WbButton>
              <WbButton className="cap-act" onClick={() => toast('上传文件')}>上传文件</WbButton>
              <span className="mf-store">存储空间已用 880.1 KB / 5.00 GB <i title="存储说明">ⓘ</i></span>
              <span style={{ flex: 1 }} />
              <div className="search-box" style={{ margin: 0, width: 200 }}>
                <WbInput placeholder="搜索文件或文件夹..." />
              </div>
            </div>
            <div className="mf-crumb"><span>云端网盘</span>/<span>配置文件</span>/<b>2072364915794640896</b></div>
            <div className="mf-empty">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg>暂无文件
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
