import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { KdocsFile } from '../lib/types'
import { toast } from '../stores/toastStore'

// 侧栏「更多 → 金山文档」面板（WB-140）：直接浏览/搜索/打开自己的金山云文档。
// 两种模式（对齐金山文档网页版）：「最近」= 最近访问的扁平列表 + 全局搜索；
// 「我的云文档」= 真实文件夹树，面包屑逐层下钻。后端能力（kdocs 连接器 + WPS OAuth）
// 在 WB-052 已打通，这里只是消费它的视图。未安装/未授权 → 诚实降级引导，不假装正常。

type Conn = 'loading' | 'not_installed' | 'need_auth' | 'connecting' | 'ready'
type Mode = 'recent' | 'folder'
interface Crumb { id: string; name: string }

// 后缀 → 一个 emoji 图标 + 中文类型名，纯展示，不影响取数。
const KIND: Record<string, [string, string]> = {
  otl: ['📝', '智能文档'], docx: ['📄', 'Word'], doc: ['📄', 'Word'],
  xlsx: ['📊', '表格'], xls: ['📊', '表格'], ksheet: ['🧮', '智能表格'],
  dbt: ['🗃️', '多维表格'], pptx: ['📽️', '演示'], ppt: ['📽️', '演示'],
  pdf: ['📕', 'PDF'], form: ['🧾', '表单'], txt: ['📃', '文本'], md: ['📃', 'Markdown'],
}
const kindOf = (ext: string): [string, string] => KIND[ext] || ['📄', ext ? ext.toUpperCase() : '文档']

function fmtTime(sec: number): string {
  if (!sec) return ''
  const d = new Date(sec * 1000)
  const diff = Date.now() - d.getTime()
  const day = 86400000
  if (diff < day && d.getDate() === new Date().getDate()) return '今天'
  if (diff < 2 * day) return '昨天'
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function fmtSize(n: number): string {
  if (!n) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const ROOT_CRUMB: Crumb = { id: '0', name: '我的云文档' }

export function KdocsView() {
  const [conn, setConn] = useState<Conn>('loading')
  const [mode, setMode] = useState<Mode>('recent')
  const [files, setFiles] = useState<KdocsFile[]>([])
  const [loading, setLoading] = useState(false)
  const [kw, setKw] = useState('')
  const [active, setActive] = useState('') // keyword the recent list currently reflects
  const [driveId, setDriveId] = useState('') // discovered personal-cloud drive
  const [crumbs, setCrumbs] = useState<Crumb[]>([ROOT_CRUMB])
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const alive = useRef(true)
  const poll = useRef<number | null>(null)

  const stopPoll = () => { if (poll.current) { window.clearInterval(poll.current); poll.current = null } }

  const applyConn = (r: { installed: boolean; authenticated: boolean }): boolean => {
    if (!r.installed) { setConn('not_installed'); setFiles([]); return false }
    if (!r.authenticated) { setConn('need_auth'); setFiles([]); return false }
    setConn('ready')
    return true
  }

  // 最近 / 搜索（扁平）。也带连接标志，token 失效即翻回引导态。
  const loadRecent = async (keyword = '') => {
    setLoading(true)
    try {
      const r = await api.kdocsFiles(keyword)
      if (!alive.current) return
      if (!applyConn(r)) return
      setFiles(r.files)
      setActive(keyword.trim())
    } catch {
      if (alive.current) toast('拉取金山文档失败，请重试')
    } finally {
      if (alive.current) setLoading(false)
    }
  }

  // 目录浏览：driveId 空 → 后端发现根；crumb 末项的 id 即当前 parent_id。
  const loadFolder = async (nextCrumbs: Crumb[], drive = driveId) => {
    setLoading(true)
    try {
      const parent = nextCrumbs[nextCrumbs.length - 1].id
      const r = await api.kdocsFolder(drive, parent)
      if (!alive.current) return
      if (!applyConn(r)) return
      if (r.drive_id) setDriveId(r.drive_id)
      setCrumbs(nextCrumbs)
      setFiles(r.files)
    } catch {
      if (alive.current) toast('打开文件夹失败，请重试')
    } finally {
      if (alive.current) setLoading(false)
    }
  }

  useEffect(() => {
    alive.current = true
    void loadRecent('')
    return () => { alive.current = false; stopPoll() }
  }, [])

  const switchMode = (m: Mode) => {
    if (m === mode) return
    setMode(m)
    if (m === 'recent') void loadRecent(active)
    else void loadFolder([ROOT_CRUMB], '') // re-discover root each entry (cheap, always fresh)
  }

  const doConnect = async () => {
    setConn('connecting')
    try {
      const r = await api.kdocsConnect()
      if (!alive.current) return
      const after = () => { if (mode === 'folder') void loadFolder([ROOT_CRUMB], ''); else void loadRecent('') }
      if (r.status === 'connected') { toast('已连接 · 金山文档'); after(); return }
      if (r.authUrl) { setAuthUrl(r.authUrl); window.open(r.authUrl, '_blank', 'noopener,noreferrer') }
      toast('已打开授权页，请在浏览器完成 WPS 授权…')
      let tries = 0
      stopPoll()
      poll.current = window.setInterval(async () => {
        tries += 1
        const s = await api.kdocsStatus().catch(() => null)
        if (!alive.current) { stopPoll(); return }
        if (s?.authenticated) { stopPoll(); toast('已连接 · 金山文档'); after() }
        else if (tries >= 150) { stopPoll(); setConn('need_auth'); toast('授权超时，请重试') }
      }, 2000)
    } catch {
      if (alive.current) { setConn('need_auth'); toast('连接失败，请重试') }
    }
  }

  const submitSearch = () => { if (conn === 'ready') void loadRecent(kw) }
  const clearSearch = () => { setKw(''); void loadRecent('') }
  const enterFolder = (f: KdocsFile) => void loadFolder([...crumbs, { id: f.file_id, name: f.name }])
  const gotoCrumb = (i: number) => { if (i < crumbs.length - 1) void loadFolder(crumbs.slice(0, i + 1)) }
  const openFile = (f: KdocsFile) => {
    if (!f.link_url) { toast('该文件暂无在线链接'); return }
    window.open(f.link_url, '_blank', 'noopener,noreferrer')
  }
  const refresh = () => { if (mode === 'recent') void loadRecent(active); else void loadFolder(crumbs) }

  const dirs = files.filter((f) => f.is_folder).length

  return (
    <section className="view active" data-view="kdocs">
      <div className="page-scroll">
        <h1 style={{ fontSize: 22, fontWeight: 800 }}>📄 金山文档</h1>
        <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6 }}>
          浏览、搜索并打开你的金山云文档（WPS 云文档）。也可在对话里让 AI 直接搜、读、建你的金山文档。
        </div>

        {/* ── 连接态引导（未安装 / 未授权 / 连接中）───────────────────── */}
        {conn === 'loading' && <div className="mf-empty">正在加载…</div>}

        {conn === 'not_installed' && (
          <div className="mf-empty" style={{ flexDirection: 'column', gap: 10, textAlign: 'center', lineHeight: 1.7 }}>
            <div>未检测到金山文档命令行工具 <b>kdocs-cli</b>。</div>
            <div style={{ fontSize: 12, color: 'var(--text-2)' }}>请先在本机安装 kdocs-cli，再回到这里连接。</div>
          </div>
        )}

        {(conn === 'need_auth' || conn === 'connecting') && (
          <div className="mf-empty" style={{ flexDirection: 'column', gap: 12, textAlign: 'center', lineHeight: 1.7 }}>
            <div>尚未连接金山文档。连接后即可浏览你的云文档，凭据仅存本机、不进前端。</div>
            <button className="hub-act" onClick={doConnect} disabled={conn === 'connecting'}>
              {conn === 'connecting' ? '连接中…' : '连接金山文档'}
            </button>
            {authUrl && conn === 'connecting' && (
              <a href={authUrl} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: 'var(--brand)' }}>
                没有自动打开？点此手动打开授权页
              </a>
            )}
          </div>
        )}

        {/* ── 已连接：最近 / 我的云文档 两个模式 ─────────────────────── */}
        {conn === 'ready' && (
          <>
            <div className="mf-tabs">
              <div className={`mf-tab ${mode === 'recent' ? 'active' : ''}`.trim()} onClick={() => switchMode('recent')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>最近
              </div>
              <div className={`mf-tab ${mode === 'folder' ? 'active' : ''}`.trim()} onClick={() => switchMode('folder')}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" /></svg>我的云文档
              </div>
            </div>

            {mode === 'recent' && (
              <div className="mf-filter" style={{ marginTop: 14 }}>
                <div className="search-box" style={{ margin: 0, flex: 1, maxWidth: 360 }}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
                  <input placeholder="搜索金山文档…" value={kw}
                    onChange={(e) => setKw(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') submitSearch() }} />
                </div>
                <button className="hub-act" onClick={submitSearch} disabled={loading}>搜索</button>
                {active && <button className="hub-act" onClick={clearSearch} disabled={loading}>返回最近</button>}
                <span style={{ flex: 1 }} />
                <button className="hub-act" onClick={refresh} disabled={loading} title="刷新">刷新</button>
              </div>
            )}

            {mode === 'folder' && (
              <div className="mf-filter" style={{ marginTop: 14 }}>
                <div className="kd-crumb">
                  {crumbs.map((c, i) => (
                    <span key={c.id + i}>
                      {i > 0 && <i className="kd-sep">/</i>}
                      <span className={`kd-cr ${i === crumbs.length - 1 ? 'cur' : ''}`.trim()}
                        onClick={() => gotoCrumb(i)}>{c.name}</span>
                    </span>
                  ))}
                </div>
                <span style={{ flex: 1 }} />
                <button className="hub-act" onClick={refresh} disabled={loading} title="刷新">刷新</button>
              </div>
            )}

            <div style={{ fontSize: 12, color: 'var(--text-2)', margin: '10px 2px' }}>
              {mode === 'recent'
                ? (active ? `「${active}」的搜索结果` : '最近访问')
                : (dirs ? `${dirs} 个文件夹` : '') + (dirs && files.length - dirs ? ' · ' : '') + (files.length - dirs ? `${files.length - dirs} 个文件` : (dirs ? '' : '此文件夹'))}
              {loading ? ' · 加载中…' : ` · 共 ${files.length} 项`}
            </div>

            {files.length === 0 && !loading && (
              <div className="mf-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg>
                {mode === 'recent' ? (active ? '没有匹配的文档' : '暂无最近文档') : '空文件夹'}
              </div>
            )}

            <div className="kd-list">
              {files.map((f) => {
                if (f.is_folder) {
                  return (
                    <div key={f.file_id} className="kd-item" onClick={() => enterFolder(f)} role="button" tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter') enterFolder(f) }}>
                      <span className="kd-ic">📁</span>
                      <div className="kd-main">
                        <div className="kd-name">{f.name}</div>
                        <div className="kd-meta">文件夹{f.mtime ? ` · ${fmtTime(f.mtime)}` : ''}</div>
                      </div>
                      <svg className="kd-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M9 6l6 6-6 6" /></svg>
                    </div>
                  )
                }
                const [icon, kind] = kindOf(f.ext)
                return (
                  <div key={f.file_id || f.name} className="kd-item" onClick={() => openFile(f)} role="button" tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') openFile(f) }}>
                    <span className="kd-ic">{icon}</span>
                    <div className="kd-main">
                      <div className="kd-name">{f.name}</div>
                      <div className="kd-meta">
                        {kind}{f.owner ? ` · ${f.owner}` : ''}{f.mtime ? ` · ${fmtTime(f.mtime)}` : ''}{f.size ? ` · ${fmtSize(f.size)}` : ''}
                      </div>
                    </div>
                    <svg className="kd-open" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 5h5v5M19 5l-8 8M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5" /></svg>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>
    </section>
  )
}
