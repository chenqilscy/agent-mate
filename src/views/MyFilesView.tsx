import { WbButton, WbInput } from '../components/ui/Primitives'
import { useState } from 'react'
import { toast } from '../stores/toastStore'
import { Breadcrumb, Checkbox, Empty, Select, Tabs, Tooltip } from 'antd'

export function MyFilesView() {
  const [tab, setTab] = useState<'results' | 'cloud'>('results')
  const [fav, setFav] = useState(false)

  return (
    <section className="view active" data-view="myfiles">
      <div className="page-scroll">
        <h1 style={{ fontSize: 22, fontWeight: 800 }}>我的文件</h1>
        <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6 }}>快捷查看任务成果，上传到云端网盘开启跨端同步。</div>

        <Tabs
          className="mf-tabs"
          activeKey={tab}
          onChange={(key) => setTab(key as 'results' | 'cloud')}
          items={[
            { key: 'results', label: <span className="mf-tab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>任务成果</span> },
            { key: 'cloud', label: <span className="mf-tab"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 18a4 4 0 010-8 6 6 0 0111.6-1.5A4.5 4.5 0 0117 18z" /></svg>云端网盘</span> },
          ]}
        />

        {tab === 'results' ? (
          <div>
            <div className="mf-filter">
              <Select className="mf-type" value="all" aria-label="文件类型" options={[{ value: 'all', label: '全部类型' }]} />
              <div className="search-box" style={{ margin: 0, width: 260 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
                <WbInput placeholder="搜索文件、任务或工作空间" />
              </div>
              <Checkbox className="mf-check" checked={fav} onChange={(e) => setFav(e.target.checked)}>我的收藏</Checkbox>
            </div>
            <Empty className="mf-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文件" />
          </div>
        ) : (
          <div>
            <div className="mf-filter">
              <WbButton className="cap-act" onClick={() => toast('新建文件夹')}>新建文件夹</WbButton>
              <WbButton className="cap-act" onClick={() => toast('上传文件')}>上传文件</WbButton>
              <span className="mf-store">存储空间已用 880.1 KB / 5.00 GB <Tooltip title="存储空间按当前账户统计"><i>ⓘ</i></Tooltip></span>
              <span style={{ flex: 1 }} />
              <div className="search-box" style={{ margin: 0, width: 200 }}>
                <WbInput placeholder="搜索文件或文件夹..." />
              </div>
            </div>
            <Breadcrumb className="mf-crumb" items={[{ title: '云端网盘' }, { title: '配置文件' }, { title: '2072364915794640896' }]} />
            <Empty className="mf-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无文件" />
          </div>
        )}
      </div>
    </section>
  )
}
