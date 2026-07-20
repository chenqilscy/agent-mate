import { useEffect, useMemo, useState } from 'react'
import { api } from '../../lib/api'
import type { InstalledSkill } from '../../lib/types'
import { useSkillStore } from '../../stores/skillStore'
import { toast } from '../../stores/toastStore'

export function LocalSkillEditorModal({ skill, onClose }: { skill: InstalledSkill; onClose: () => void }) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [instructions, setInstructions] = useState('')
  const [initial, setInitial] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const fingerprint = useMemo(() => JSON.stringify([name, description, instructions]), [name, description, instructions])
  const dirty = Boolean(initial) && fingerprint !== initial

  useEffect(() => {
    let alive = true
    api.skillDetail(skill.key)
      .then(({ skill: detail }) => {
        if (!alive) return
        setName(detail.name)
        setDescription(detail.description)
        setInstructions(detail.body)
        setInitial(JSON.stringify([detail.name, detail.description, detail.body]))
      })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : '读取技能失败') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [skill.key])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') requestClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  const requestClose = () => {
    if (dirty && !window.confirm('有尚未保存的技能修改，确定放弃吗？')) return
    onClose()
  }
  const save = async () => {
    const payload = { name: name.trim(), description: description.trim(), instructions: instructions.trim() }
    if (!payload.name || !payload.description || !payload.instructions) {
      setError('名称、简介和技能指令均为必填项')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.updateSkill(skill.key, payload)
      await useSkillStore.getState().load(true)
      toast('已保存 · ' + payload.name)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose() }}>
      <div className="np-modal skill-local-edit-modal" role="dialog" aria-modal="true" aria-label={`编辑技能 ${skill.name}`}>
        <div className="np-h">编辑技能<button className="np-x" aria-label="关闭" onClick={requestClose}>×</button></div>
        <div className="np-body">
          {loading ? <div className="cap-blank">读取技能中…</div> : (
            <>
              <label className="np-lbl" htmlFor="local-skill-name">名称 <span className="np-required">必填</span></label>
              <input id="local-skill-name" className="np-input" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} autoFocus />
              <label className="np-lbl" htmlFor="local-skill-description">简介 <span className="np-required">必填</span></label>
              <textarea id="local-skill-description" className="np-ta" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />
              <label className="np-lbl" htmlFor="local-skill-instructions">技能指令 <span className="np-required">必填</span></label>
              <textarea id="local-skill-instructions" className="np-ta skill-local-instructions" maxLength={50000} value={instructions} onChange={(e) => setInstructions(e.target.value)} />
              <div className="mc-hint">只更新 SKILL.md；references、scripts 和其他文件保持不变。</div>
            </>
          )}
          {error && <div className="form-err" style={{ marginTop: 10 }}>{error}</div>}
        </div>
        <div className="np-foot">
          {dirty && <span className="np-hint">有未保存修改</span>}
          <button className="btn-ghost" disabled={saving} onClick={requestClose}>取消</button>
          <button className="btn-dark" disabled={loading || saving} onClick={save}>{saving ? '保存中…' : '保存技能'}</button>
        </div>
      </div>
    </div>
  )
}
