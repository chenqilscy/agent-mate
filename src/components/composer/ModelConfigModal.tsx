import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { ModelOption } from '../../lib/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

// 配置自定义模型（WB-124）。管理按 owner 隔离、多厂商的自定义模型（显示名 + model id +
// api base + api key），以及隐藏/恢复用不到的内置项。API Key 只写不回读（后端脱敏，铁律#4）。
// 套 .np-* 表单/弹窗类，天然暗色；列表行用 mc- 前缀。

const BLANK = { name: '', model_id: '', api_base: '', api_key: '', icon: '🧩', mult: '' }

export function ModelConfigModal({ onClose }: { onClose: () => void }) {
  const reloadModels = useSettingsStore((s) => s.reloadModels)
  const [models, setModels] = useState<ModelOption[]>([])
  const [editing, setEditing] = useState<ModelOption | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ ...BLANK })
  const [busy, setBusy] = useState(false)

  const custom = models.filter((m) => m.group === 'custom')
  const builtin = models.filter((m) => m.group === 'builtin')

  const load = async () => {
    try {
      const r = await api.models(true) // 含隐藏内置
      setModels(r.models)
    } catch {
      toast('加载模型列表失败')
    }
  }
  useEffect(() => { load() }, [])

  const startNew = () => { setEditing(null); setForm({ ...BLANK }); setShowForm(true) }
  const startEdit = (m: ModelOption) => {
    setEditing(m)
    setForm({ name: m.name, model_id: m.model_id || '', api_base: m.api_base || '', api_key: '', icon: m.icon || '🧩', mult: m.mult || '' })
    setShowForm(true)
  }
  const cancelForm = () => { setShowForm(false); setEditing(null); setForm({ ...BLANK }) }

  const save = async () => {
    const name = form.name.trim()
    const modelId = form.model_id.trim()
    if (!name || !modelId || busy) return
    setBusy(true)
    try {
      const payload = {
        name, model_id: modelId,
        api_base: form.api_base.trim(),
        icon: form.icon.trim() || '🧩',
        mult: form.mult.trim(),
        // 编辑时留空 = 不改动已存的 key；新建时留空 = 无独立 key（走 .env 默认）。
        ...(form.api_key ? { api_key: form.api_key } : {}),
      }
      if (editing?.id) await api.updateCustomModel(editing.id, payload)
      else await api.createCustomModel(payload)
      toast(editing ? '已保存' : '已添加模型')
      cancelForm()
      await load()
      await reloadModels()
    } catch (e) {
      toast(String(e).includes('409') ? '已有同名模型' : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const del = async (m: ModelOption) => {
    if (!m.id || busy) return
    if (!window.confirm(`删除自定义模型「${m.name}」？`)) return
    setBusy(true)
    try {
      await api.deleteCustomModel(m.id)
      toast('已删除')
      if (editing?.id === m.id) cancelForm()
      await load()
      await reloadModels()
    } catch {
      toast('删除失败')
    } finally {
      setBusy(false)
    }
  }

  const toggleHide = async (m: ModelOption) => {
    if (busy) return
    setBusy(true)
    try {
      await api.hideBuiltinModel(m.name, !m.hidden)
      await load()
      await reloadModels()
    } catch {
      toast('操作失败')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="np-overlay open" style={{ zIndex: 170 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="配置自定义模型">
        <div className="np-h">模型管理<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">
            自定义模型
            {!showForm && <button className="np-tplbtn" onClick={startNew}>＋ 添加</button>}
          </div>
          {custom.length === 0 && !showForm && <div className="mc-empty">还没有自定义模型。点「＋ 添加」接入你自己的厂商（OpenAI / GLM / Kimi…）。</div>}
          {custom.map((m) => (
            <div className="mc-row" key={m.id}>
              <span className="mc-ic">{m.icon}</span>
              <span className="mc-info">
                <span className="mc-name">{m.name}</span>
                <span className="mc-sub">{m.model_id}{m.api_base ? ` · ${m.api_base}` : ''}{m.has_key ? ' · 🔑' : ''}</span>
              </span>
              <button className="mc-act" onClick={() => startEdit(m)}>编辑</button>
              <button className="mc-act danger" onClick={() => del(m)}>删除</button>
            </div>
          ))}

          {showForm && (
            <div className="mc-form">
              <div className="mc-frow">
                <input className="np-input" style={{ width: 56, textAlign: 'center', flexShrink: 0 }} value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} maxLength={4} aria-label="图标 emoji" />
                <input className="np-input" style={{ flex: 1 }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} placeholder="显示名，如 我的 GPT-4o" />
              </div>
              <input className="np-input" style={{ marginTop: 8 }} value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} maxLength={120} placeholder="模型 id，如 gpt-4o / deepseek-chat" />
              <input className="np-input" style={{ marginTop: 8 }} value={form.api_base} onChange={(e) => setForm({ ...form, api_base: e.target.value })} maxLength={300} placeholder="API Base（留空用后端默认），如 https://api.openai.com/v1" />
              <input className="np-input" type="password" style={{ marginTop: 8 }} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} maxLength={400} placeholder={editing?.has_key ? 'API Key（已保存，留空不改）' : 'API Key（留空则用后端默认凭据）'} autoComplete="off" />
              <div className="mc-hint">Key 只存本机后端、绝不回传前端，也不进前端存储。</div>
              <div className="mc-fbtns">
                <button className="btn-ghost" onClick={cancelForm}>取消</button>
                <button className="btn-dark" disabled={!form.name.trim() || !form.model_id.trim() || busy} onClick={save}>{editing ? '保存' : '添加'}</button>
              </div>
            </div>
          )}

          <div className="np-lbl" style={{ marginTop: 20 }}>内置模型<small className="mc-lblhint">隐藏用不到的项，不再出现在选择器</small></div>
          {builtin.map((m) => (
            <div className={`mc-row ${m.hidden ? 'off' : ''}`.trim()} key={m.name}>
              <span className="mc-ic" style={m.color ? { background: m.color, color: '#fff' } : undefined}>{m.icon}</span>
              <span className="mc-info"><span className="mc-name">{m.name}</span></span>
              <button className="mc-act" onClick={() => toggleHide(m)}>{m.hidden ? '恢复' : '隐藏'}</button>
            </div>
          ))}
        </div>
        <div className="np-foot">
          <span className="np-hint" style={{ marginRight: 'auto' }} />
          <button className="btn-dark" onClick={onClose}>完成</button>
        </div>
      </div>
    </div>
  )
}
