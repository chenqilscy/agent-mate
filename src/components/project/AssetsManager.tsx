import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useRef, useState } from 'react'
import { api, type FileEntry } from '../../lib/api'
import type { FileScope } from '../panel/FileTree'
import { FileViewer } from '../panel/FileViewer'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { Breadcrumb, Dropdown, Empty, Input, Progress, Table } from 'antd'
import { clickable } from '../../lib/a11y'

// 资产 = the project's cloud drive (§11 阶段 C): a real file manager over the
// project workspace — upload / download / rename / delete / new folder + quota.
function fmtSize(n: number | null): string {
  if (n == null) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}
function fmtTime(mtime?: number): string {
  if (!mtime) return '-'
  const diff = Date.now() / 1000 - mtime
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}
function typeLabel(e: FileEntry): string {
  if (e.type === 'd') return '文件夹'
  const ext = e.name.split('.').pop()?.toUpperCase()
  return ext && ext !== e.name.toUpperCase() ? ext : '文件'
}
function iconFor(e: FileEntry): string {
  if (e.type === 'd') return '📁'
  const map: Record<string, string> = { md: 'Ⓜ️', json: '🧾', html: '🌐', py: '🐍', svg: '🖼️', png: '🖼️', css: '🎨', pdf: '📕', txt: '📄' }
  return map[e.name.split('.').pop()?.toLowerCase() ?? ''] ?? '📄'
}

function entriesAt(entries: FileEntry[], cwd: string): FileEntry[] {
  if (!cwd) return entries
  let cur = entries
  for (const part of cwd.split('/')) {
    const node = cur.find((e) => e.type === 'd' && e.name === part)
    if (!node) return []
    cur = node.children ?? []
  }
  return cur
}

export function AssetsManager({ scope, canWrite = true }: { scope: FileScope; canWrite?: boolean }) {
  const viewerPath = useUIStore((s) => s.viewerPath)
  const openFile = useUIStore((s) => s.openFile)
  const closeFile = useUIStore((s) => s.closeFile)
  const [entries, setEntries] = useState<FileEntry[]>([])
  const [usage, setUsage] = useState<{ used: number; quota: number }>({ used: 0, quota: 0 })
  const [cwd, setCwd] = useState('')
  const [q, setQ] = useState('')
  const [renaming, setRenaming] = useState<string | null>(null)
  const [renameDraft, setRenameDraft] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const reload = async () => {
    const [t, u] = await Promise.all([api.filesTree(scope), api.fileUsage(scope)])
    setEntries(t.entries)
    setUsage(u)
  }
  useEffect(() => { reload(); setCwd('') /* eslint-disable-next-line */ }, [scope.project, scope.session])

  const rows = entriesAt(entries, cwd).filter((e) => e.name.toLowerCase().includes(q.trim().toLowerCase()))
  const inPath = (name: string) => (cwd ? `${cwd}/${name}` : name)

  const onUpload = async (files: FileList | null) => {
    if (!files || !files.length) return
    for (const f of Array.from(files)) {
      await api.uploadFile(inPath(f.name), f, scope).catch(() => toast('上传失败 · ' + f.name))
    }
    toast(`已上传 ${files.length} 个文件`)
    reload()
  }

  const newFolder = async () => {
    const existing = new Set(entriesAt(entries, cwd).map((e) => e.name))
    let name = '新建文件夹'
    for (let i = 2; existing.has(name); i++) name = `新建文件夹 ${i}`
    await api.mkdir(inPath(name), scope)
    reload()
  }

  const doRename = async (path: string) => {
    const nn = renameDraft.trim()
    setRenaming(null)
    if (!nn) return
    await api.renameFile(path, nn, scope).catch(() => toast('重命名失败'))
    reload()
  }
  const doDelete = async (e: FileEntry) => {
    await api.deleteFile(e.path, scope).catch(() => toast('删除失败'))
    toast('已删除 · ' + e.name)
    reload()
  }

  if (viewerPath) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, marginTop: -18, marginLeft: -24, marginRight: -24 }}>
        <FileViewer path={viewerPath} onClose={closeFile} scope={scope} />
      </div>
    )
  }

  const pct = usage.quota ? (usage.used / usage.quota) * 100 : 0

  return (
    <div>
      <div className="as-toolbar">
        {canWrite && <WbButton className="cap-act" onClick={newFolder}>新建文件夹</WbButton>}
        {canWrite && <WbButton className="cap-act" onClick={() => fileInput.current?.click()}>上传文件</WbButton>}
        {canWrite && <WbInput ref={fileInput} type="file" multiple hidden onChange={(e) => onUpload(e.target.files)} />}
        {!canWrite && <span className="as-quota">只读模式 · 可预览和下载项目资产</span>}
        <span className="as-quota">存储空间已用 {fmtSize(usage.used)} / {fmtSize(usage.quota)} <Progress percent={Number(pct.toFixed(2))} size="small" showInfo={false} /></span>
        <span style={{ flex: 1 }} />
        <Input.Search className="search-box" allowClear style={{ margin: 0, width: 220 }} placeholder="搜索文件或文件夹" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      <Breadcrumb className="as-crumb" items={[{ title: <span {...clickable} onClick={() => setCwd('')}>项目云盘</span> }, ...cwd.split('/').filter(Boolean).map((seg, i, arr) => ({ title: <span {...clickable} onClick={() => setCwd(arr.slice(0, i + 1).join('/'))}>{seg}</span> }))]} />

      <Table<FileEntry>
        className="as-table"
        rowKey="path"
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={canWrite ? '暂无文件，点「上传文件」或让 Agent 在本项目里生成产物' : '暂无项目资产'} /> }}
        onRow={() => ({ className: 'as-row' })}
        columns={[
          { title: '名称', dataIndex: 'name', render: (_, e) => (
                  renaming === e.path ? (
                    <WbInput
                      className="pj-kadd" autoFocus aria-label="重命名" placeholder="新名称" style={{ marginBottom: 0 }} value={renameDraft}
                      onChange={(ev) => setRenameDraft(ev.target.value)}
                      onKeyDown={(ev) => { if (ev.key === 'Enter') doRename(e.path); if (ev.key === 'Escape') setRenaming(null) }}
                      onBlur={() => setRenaming(null)}
                    />
                  ) : (
                    <span className="as-name" {...clickable} onClick={() => (e.type === 'd' ? setCwd(e.path) : openFile(e.path))}>
                      <span className="ic">{iconFor(e)}</span>{e.name}
                    </span>
                  )
                ) },
          { title: '类型', key: 'type', width: 90, className: 'as-col-t', render: (_, e) => typeLabel(e) },
          { title: '更新时间', dataIndex: 'mtime', width: 110, className: 'as-col-s', render: (value) => fmtTime(value) },
          { title: '大小', dataIndex: 'size', width: 90, className: 'as-col-s', render: (value) => fmtSize(value) },
          { title: '', key: 'actions', width: 50, render: (_, e) => {
            const items = [
              ...(e.type === 'f' ? [{ key: 'download', label: '下载' }] : []),
              ...(canWrite ? [{ key: 'rename', label: '重命名' }, { key: 'delete', label: '删除', danger: true }] : []),
            ]
            return items.length ? <Dropdown trigger={['click']} menu={{ items, onClick: ({ key, domEvent }) => { domEvent.stopPropagation(); if (key === 'download') void api.downloadFile(e.path, e.name, scope); else if (key === 'rename') { setRenaming(e.path); setRenameDraft(e.name) } else void doDelete(e) } }}><WbButton className="as-more" onClick={(event) => event.stopPropagation()}>⋯</WbButton></Dropdown> : null
          } },
        ]}
      />
    </div>
  )
}
