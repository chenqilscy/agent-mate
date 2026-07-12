import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { ModelOption, Provider } from '../../lib/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

// 模型管理（WB-128）。上半：内置厂商渠道——每个厂商填一次 API Key 即启用其模型（可增删模型名）；
// 下半：自由填写的自定义模型（WB-124 兜底，接预置外的厂商/自建）。API Key 只写不回读（后端脱敏，铁律#4）。
// 套 .np-* / mc- 类，token 化天然暗色。

const BLANK = { name: '', model_id: '', api_base: '', api_key: '', icon: '🧩', mult: '' }

export function ModelConfigModal({ onClose }: { onClose: () => void }) {
  const reloadModels = useSettingsStore((s) => s.reloadModels)
  const [providers, setProviders] = useState<Provider[]>([])
  const [custom, setCustom] = useState<ModelOption[]>([])
  const [effective, setEffective] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [keyDraft, setKeyDraft] = useState<Record<string, string>>({})
  const [modelDraft, setModelDraft] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  // custom form
  const [editing, setEditing] = useState<ModelOption | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ ...BLANK })

  const load = async () => {
    try {
      const r = await api.models()
      setProviders(r.providers)
      setCustom(r.custom)
      setEffective(r.effective)
    } catch {
      toast('加载模型列表失败')
    }
  }
  useEffect(() => { load() }, [])

  const refresh = async () => { await load(); await reloadModels() }

  // ---- providers ----
  const saveKey = async (p: Provider) => {
    const v = (keyDraft[p.id] ?? '').trim()
    if (busy) return
    // 已配置且输入为空 = 不改（撤销走单独按钮）
    if (!v && p.has_key) return
    setBusy(true)
    try {
      await api.setProviderKey(p.id, v)
      toast(v ? `已保存 · ${p.name}` : `已撤销 · ${p.name}`)
      setKeyDraft({ ...keyDraft, [p.id]: '' })
      await refresh()
    } catch { toast('保存失败') } finally { setBusy(false) }
  }
  const clearKey = async (p: Provider) => {
    if (busy || !window.confirm(`撤销「${p.name}」的 API Key？其模型将不可用。`)) return
    setBusy(true)
    try { await api.setProviderKey(p.id, ''); toast('已撤销'); await refresh() }
    catch { toast('操作失败') } finally { setBusy(false) }
  }
  const toggleModel = async (p: Provider, mid: string, hidden: boolean) => {
    if (busy) return
    setBusy(true)
    try { await api.hideProviderModel(p.id, mid, hidden); await refresh() }
    catch { toast('操作失败') } finally { setBusy(false) }
  }
  const addModel = async (p: Provider) => {
    const v = (modelDraft[p.id] ?? '').trim()
    if (!v || busy) return
    setBusy(true)
    try {
      await api.addProviderModel(p.id, v); toast('已添加模型')
      setModelDraft({ ...modelDraft, [p.id]: '' }); await refresh()
    } catch { toast('添加失败') } finally { setBusy(false) }
  }

  // ---- custom fallback ----
  const startNew = () => { setEditing(null); setForm({ ...BLANK }); setShowForm(true) }
  const startEdit = (m: ModelOption) => {
    setEditing(m)
    setForm({ name: m.name, model_id: m.model_id || '', api_base: m.api_base || '', api_key: '', icon: m.icon || '🧩', mult: '' })
    setShowForm(true)
  }
  const cancelForm = () => { setShowForm(false); setEditing(null); setForm({ ...BLANK }) }
  const saveCustom = async () => {
    const name = form.name.trim(); const modelId = form.model_id.trim()
    if (!name || !modelId || busy) return
    setBusy(true)
    try {
      const payload = {
        name, model_id: modelId, api_base: form.api_base.trim(), icon: form.icon.trim() || '🧩',
        ...(form.api_key ? { api_key: form.api_key } : {}),
      }
      if (editing?.id) await api.updateCustomModel(editing.id, payload)
      else await api.createCustomModel(payload)
      toast(editing ? '已保存' : '已添加模型'); cancelForm(); await refresh()
    } catch (e) { toast(String(e).includes('409') ? '已有同名模型' : '保存失败') }
    finally { setBusy(false) }
  }
  const delCustom = async (m: ModelOption) => {
    if (!m.id || busy || !window.confirm(`删除自定义模型「${m.name}」？`)) return
    setBusy(true)
    try { await api.deleteCustomModel(m.id); toast('已删除'); if (editing?.id === m.id) cancelForm(); await refresh() }
    catch { toast('删除失败') } finally { setBusy(false) }
  }

  return (
    <div className="np-overlay open" style={{ zIndex: 170 }} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="模型管理">
        <div className="np-h">模型管理<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">内置厂商<small className="mc-lblhint">填一次 API Key 即启用该厂商模型 · Key 只存本机后端</small></div>
          {providers.map((p) => {
            const open = expanded === p.id
            return (
              <div className={`mc-prov ${open ? 'open' : ''}`.trim()} key={p.id}>
                <div className="mc-provhd" onClick={() => setExpanded(open ? null : p.id)}>
                  <span className="mc-ic" style={p.color ? { background: p.color, color: '#fff' } : undefined}>{p.icon}</span>
                  <span className="mc-info">
                    <span className="mc-name">{p.name}</span>
                    <span className="mc-sub">{p.has_key ? `已启用 · ${p.models.filter((m) => !m.hidden).length} 个模型` : '未配置 Key'}</span>
                  </span>
                  {p.has_key && <span className="mc-badge on">已启用</span>}
                  <span className="mc-caret">{open ? '▾' : '▸'}</span>
                </div>
                {open && (
                  <div className="mc-provbody">
                    <div className="mc-keyrow">
                      <input
                        className="np-input" type="password" autoComplete="off"
                        placeholder={p.has_key ? '已配置，输入新 Key 覆盖（留空不改）' : `API Key，如 ${p.key_hint}`}
                        value={keyDraft[p.id] ?? ''} onChange={(e) => setKeyDraft({ ...keyDraft, [p.id]: e.target.value })}
                      />
                      <button className="btn-dark" disabled={busy || (!(keyDraft[p.id] ?? '').trim() && p.has_key)} onClick={() => saveKey(p)}>保存</button>
                      {p.has_key && <button className="btn-ghost danger-b" disabled={busy} onClick={() => clearKey(p)}>撤销</button>}
                    </div>
                    <div className="mc-provmeta">Base：{p.base_url} · <a href={p.site} target="_blank" rel="noreferrer">获取 Key ↗</a></div>
                    <div className="mc-modlist">
                      {p.models.map((m) => (
                        <div className={`mc-mod ${m.hidden ? 'off' : ''}`.trim()} key={m.model_id}>
                          <span className="mc-modname">{m.model_id}{!m.preset && <span className="mc-tag">自加</span>}</span>
                          {m.preset
                            ? <button className="mc-act" disabled={busy} onClick={() => toggleModel(p, m.model_id, !m.hidden)}>{m.hidden ? '恢复' : '隐藏'}</button>
                            : <button className="mc-act danger" disabled={busy} onClick={() => toggleModel(p, m.model_id, true)}>删除</button>}
                        </div>
                      ))}
                    </div>
                    <div className="mc-keyrow">
                      <input className="np-input" placeholder="补充模型名（厂商上新时），如 deepseek-chat" value={modelDraft[p.id] ?? ''} onChange={(e) => setModelDraft({ ...modelDraft, [p.id]: e.target.value })} />
                      <button className="btn-ghost" disabled={busy || !(modelDraft[p.id] ?? '').trim()} onClick={() => addModel(p)}>＋ 加模型</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          <div className="np-lbl" style={{ marginTop: 20 }}>
            自定义模型<small className="mc-lblhint">预置厂商之外（自建/代理站）</small>
            {!showForm && <button className="np-tplbtn" onClick={startNew}>＋ 添加</button>}
          </div>
          {custom.length === 0 && !showForm && <div className="mc-empty">没有自定义模型。预置厂商够用就不必加。</div>}
          {custom.map((m) => (
            <div className="mc-row" key={m.id}>
              <span className="mc-ic">{m.icon}</span>
              <span className="mc-info">
                <span className="mc-name">{m.name}</span>
                <span className="mc-sub">{m.model_id}{m.api_base ? ` · ${m.api_base}` : ''}{m.has_key ? ' · 🔑' : ''}</span>
              </span>
              <button className="mc-act" onClick={() => startEdit(m)}>编辑</button>
              <button className="mc-act danger" onClick={() => delCustom(m)}>删除</button>
            </div>
          ))}
          {showForm && (
            <div className="mc-form">
              <div className="mc-frow">
                <input className="np-input" style={{ width: 56, textAlign: 'center', flexShrink: 0 }} value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} maxLength={4} aria-label="图标 emoji" />
                <input className="np-input" style={{ flex: 1 }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} placeholder="显示名，如 我的自建 Llama" />
              </div>
              <input className="np-input" style={{ marginTop: 8 }} value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} maxLength={120} placeholder="模型 id" />
              <input className="np-input" style={{ marginTop: 8 }} value={form.api_base} onChange={(e) => setForm({ ...form, api_base: e.target.value })} maxLength={300} placeholder="API Base（留空用后端默认），如 https://host/v1" />
              <input className="np-input" type="password" style={{ marginTop: 8 }} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} maxLength={400} placeholder={editing?.has_key ? 'API Key（已保存，留空不改）' : 'API Key（留空则用后端默认凭据）'} autoComplete="off" />
              <div className="mc-hint">Key 只存本机后端、绝不回传前端。</div>
              <div className="mc-fbtns">
                <button className="btn-ghost" onClick={cancelForm}>取消</button>
                <button className="btn-dark" disabled={!form.name.trim() || !form.model_id.trim() || busy} onClick={saveCustom}>{editing ? '保存' : '添加'}</button>
              </div>
            </div>
          )}

          <div className="mc-empty" style={{ marginTop: 18 }}>选择器里的「默认 · {effective}」跟随后端 .env 配置，未选其它时就用它——始终可用。</div>
        </div>
        <div className="np-foot">
          <span className="np-hint" style={{ marginRight: 'auto' }} />
          <button className="btn-dark" onClick={onClose}>完成</button>
        </div>
      </div>
    </div>
  )
}
