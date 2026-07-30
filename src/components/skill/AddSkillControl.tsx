import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useRef, useState } from 'react'
import { api, SkillSecurityError } from '../../lib/api'
import type { InstalledSkill, SkillSecurityReport } from '../../lib/types'
import { useSkillStore } from '../../stores/skillStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'
import { App as AntApp } from 'antd'

type DirectoryFile = File & { webkitRelativePath?: string }

function toBase64(file: File): Promise<string> {
  return file.arrayBuffer().then((buffer) => {
    const bytes = new Uint8Array(buffer)
    let binary = ''
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000))
    }
    return btoa(binary)
  })
}

function ImportSkillModal({ open, onClose, onImported }: {
  open: boolean
  onClose: () => void
  onImported: (skill: InstalledSkill) => void
}) {
  const { modal } = AntApp.useApp()
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setError('')
    setDragging(false)
    if (folderInput.current) folderInput.current.setAttribute('webkitdirectory', '')
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && !busy) onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, busy, onClose])

  if (!open) return null

  const warningContent = (report: SkillSecurityReport) => (
    <>
      <p>扫描到以下需要确认的行为。脚本只会作为静态文件保存，不会自动执行：</p>
      <ul>
        {report.findings.map((finding) => (
          <li key={`${finding.code}:${finding.path}:${finding.line}`}>
            {finding.message}（{finding.path}:{finding.line}）
          </li>
        ))}
      </ul>
    </>
  )

  const finish = async (
    request: (acceptSecurityWarnings: boolean) => Promise<{ skill: InstalledSkill }>,
    accepted = false,
  ) => {
    setBusy(true)
    setError('')
    try {
      const result = await request(accepted)
      await useSkillStore.getState().load(true)
      toast('已导入 · ' + result.skill.name)
      onImported(result.skill)
      onClose()
    } catch (reason) {
      if (
        reason instanceof SkillSecurityError
        && reason.code === 'skill_security_confirmation_required'
        && !accepted
      ) {
        modal.confirm({
          title: '确认导入存在风险提示的技能？',
          content: warningContent(reason.report),
          okText: '我已了解，继续导入',
          cancelText: '取消',
          onOk: () => finish(request, true),
        })
        return
      }
      setError(reason instanceof Error ? reason.message : '技能导入失败')
    } finally {
      setBusy(false)
    }
  }

  const importFile = (file?: File) => {
    if (!file || busy) return
    if (!/\.(md|zip)$/i.test(file.name)) {
      setError('请选择 .md 或 .zip 技能文件')
      return
    }
    void finish((accepted) => api.importSkillFile(file, accepted))
  }

  const importFolder = async (list: FileList | null) => {
    if (!list?.length || busy) return
    setBusy(true)
    setError('')
    try {
      const files = await Promise.all(Array.from(list).map(async (file: DirectoryFile) => ({
        path: file.webkitRelativePath || file.name,
        content: await toBase64(file),
      })))
      await finish((accepted) => api.importSkillDirectory(files, accepted))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '技能导入失败')
      setBusy(false)
    }
  }

  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy} zIndex={170}>
      <div className="np-modal skill-import-modal" role="dialog" aria-modal="true" aria-label="导入技能">
        <div className="np-h">导入技能<WbButton className="np-x" onClick={onClose} disabled={busy}>×</WbButton></div>
        <div className="np-body">
          <div
            className={`skill-import-drop ${dragging ? 'dragging' : ''}`.trim()}
            {...clickable}
            aria-disabled={busy}
            onClick={() => { if (!busy) fileInput.current?.click() }}
            onDragOver={(e) => { e.preventDefault(); if (!busy) setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              importFile(e.dataTransfer.files[0])
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path d="M4 8.5h16v11H4zM8 8.5V5h8v3.5M12 17V11m0 0-3 3m3-3 3 3" />
            </svg>
            <b>{busy ? '正在校验并导入…' : '拖拽文件或点击上传'}</b>
            <span>支持 SKILL.md 与 .zip 技能包</span>
          </div>
          <WbInput ref={fileInput} type="file" accept=".md,.zip" hidden onChange={(e) => { importFile(e.target.files?.[0]); e.currentTarget.value = '' }} />
          <WbInput ref={folderInput} type="file" multiple hidden onChange={(e) => { void importFolder(e.target.files); e.currentTarget.value = '' }} />

          <WbButton className="skill-folder-btn" disabled={busy} onClick={() => folderInput.current?.click()}>
            <span>📁</span>选择本地技能文件夹
          </WbButton>

          {error && <div className="skill-import-error" role="alert">{error}</div>}

          <div className="skill-import-requirements">
            <b>文件要求</b>
            <ul>
              <li>文件夹或 .zip 中必须且只能包含一个 SKILL.md</li>
              <li>.md 文件需包含 YAML 格式的技能名称和描述</li>
              <li>单个技能包最多 20MB、256 个文件</li>
            </ul>
          </div>
        </div>
      </div>
    </AntModalBridge>
  )
}

export function AddSkillControl({ onCreate, onImported }: {
  onCreate: () => void
  onImported: (skill: InstalledSkill) => void
}) {
  const root = useRef<HTMLDivElement>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)

  useEffect(() => {
    if (!menuOpen) return
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onPointer); document.removeEventListener('keydown', onKey) }
  }, [menuOpen])

  const choose = (action: () => void) => { setMenuOpen(false); action() }

  return (
    <>
      <div className="skill-add-wrap" ref={root}>
        <WbButton className={`cap-act ${menuOpen ? 'on' : ''}`.trim()} aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((value) => !value)}>
          ＋ 添加技能
        </WbButton>
        {menuOpen && (
          <div className="skill-add-menu" role="menu">
            <WbButton className="skill-add-menu-action" role="menuitem" onClick={() => choose(() => setImportOpen(true))}>上传技能</WbButton>
            <WbButton className="skill-add-menu-action" role="menuitem" onClick={() => choose(onCreate)}>创建技能</WbButton>
          </div>
        )}
      </div>
      <ImportSkillModal open={importOpen} onClose={() => setImportOpen(false)} onImported={onImported} />
    </>
  )
}
