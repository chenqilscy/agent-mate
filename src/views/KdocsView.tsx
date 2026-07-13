import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import type { KdocsFile } from '../lib/types'
import { toast } from '../stores/toastStore'

// 侧栏「更多 → 金山文档」面板（WB-140）：直接浏览/搜索/打开自己的金山云文档。
// 后端能力（kdocs 连接器 + WPS OAuth）在 WB-052 已打通，这里只是一个消费它的视图。
// 未安装 kdocs-cli / 未授权 → 诚实降级到引导态，而不是空列表假装正常。

type Conn = 'loading' | 'not_installed' | 'need_auth' | 'connecting' | 'ready'

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
  const now = Date.now()
  const diff = now - d.getTime()
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

export function KdocsView() {
  const [conn, setConn] = useState<Conn>('loading')
  const [files, setFiles] = useState<KdocsFile[]>([])
  const [loading, setLoading] = useState(false)
  const [kw, setKw] = useState('')
  const [active, setActive] = useState('') // the keyword the current list reflects
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const alive = useRef(true)
  const poll = useRef<number | null>(null)

  const stopPoll = () => { if (poll.current) { window.clearInterval(poll.current); poll.current = null } }

  // Fetch files (recent when keyword empty, search otherwise). Also carries the
  // live connection flags, so an expired token flips the panel back to guidance.
  const load = async (keyword = '') => {
    setLoading(true)
    try {
      const r = await api.kdocsFiles(keyword)
      if (!alive.current) return
      if (!r.installed) { setConn('not_installed'); setFiles([]); return }
      if (!r.authenticated) { setConn('need_auth'); setFiles([]); return }
      setConn('ready')
      setFiles(r.files)
      setActive(keyword.trim())
    } catch {
      if (alive.current) toast('拉取金山文档失败，请重试')
    } finally {
      if (alive.current) setLoading(false)
    }
  }

  useEffect(() => {
    alive.current = true
    void load('')
    return () => { alive.current = false; stopPoll() }
  }, [])

  const doConnect = async () => {
    setConn('connecting')
    try {
      const r = await api.kdocsConnect()
      if (!alive.current) return
      if (r.status === 'connected') { toast('已连接 · 金山文档'); void load(''); return }
      if (r.authUrl) { setAuthUrl(r.authUrl); window.open(r.authUrl, '_blank', 'noopener,noreferrer') }
      toast('已打开授权页，请在浏览器完成 WPS 授权…')
      let tries = 0
      stopPoll()
      poll.current = window.setInterval(async () => {
        tries += 1
        const s = await api.kdocsStatus().catch(() => null)
        if (!alive.current) { stopPoll(); return }
        if (s?.authenticated) { stopPoll(); toast('已连接 · 金山文档'); void load('') }
        else if (tries >= 150) { stopPoll(); setConn('need_auth'); toast('授权超时，请重试') }
      }, 2000)
    } catch {
      if (alive.current) { setConn('need_auth'); toast('连接失败，请重试') }
    }
  }

  const submit = () => { if (conn === 'ready') void load(kw) }
  const clearSearch = () => { setKw(''); void load('') }
  const open = (f: KdocsFile) => {
    if (!f.link_url) { toast('该文件暂无在线链接'); return }
    window.open(f.link_url, '_blank', 'noopener,noreferrer')
  }

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

        {/* ── 已连接：搜索 + 文件列表 ─────────────────────────────────── */}
        {(conn === 'ready') && (
          <>
            <div className="mf-filter" style={{ marginTop: 16 }}>
              <div className="search-box" style={{ margin: 0, flex: 1, maxWidth: 360 }}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
                <input
                  placeholder="搜索金山文档…"
                  value={kw}
                  onChange={(e) => setKw(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
                />
              </div>
              <button className="hub-act" onClick={submit} disabled={loading}>搜索</button>
              {active && <button className="hub-act" onClick={clearSearch} disabled={loading}>返回最近</button>}
              <span style={{ flex: 1 }} />
              <button className="hub-act" onClick={() => load(active)} disabled={loading} title="刷新">刷新</button>
            </div>

            <div style={{ fontSize: 12, color: 'var(--text-2)', margin: '10px 2px' }}>
              {active ? `「${active}」的搜索结果` : '最近访问'}{loading ? ' · 加载中…' : ` · ${files.length} 项`}
            </div>

            {files.length === 0 && !loading && (
              <div className="mf-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M14 3v5h5M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z" /></svg>
                {active ? '没有匹配的文档' : '暂无最近文档'}
              </div>
            )}

            <div className="kd-list">
              {files.map((f) => {
                const [icon, kind] = kindOf(f.ext)
                return (
                  <div key={f.file_id || f.name} className="kd-item" onClick={() => open(f)} role="button" tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') open(f) }}>
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
