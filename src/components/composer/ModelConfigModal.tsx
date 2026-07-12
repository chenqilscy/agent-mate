import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { ModelMeta, ModelOption, Provider } from '../../lib/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'

// 模型管理（WB-128/129/132）。内置厂商渠道（填一次 Key 即启用，Base URL 可改、可在线拉取真实模型）
// + 自定义模型兜底；每个模型可记「能力(模态/工具/推理)+成本」为 Auto 铺路。Key 只写不回读（铁律#4）。
// 套 .np-* / mc- 类，token 化天然暗色。

const BLANK = { name: '', model_id: '', api_base: '', api_key: '', icon: '🧩', mult: '' }

// 能力词表（WB-132），与后端 CAPABILITIES 对齐。
const CAPS: { k: string; label: string; icon: string }[] = [
  { k: 'text', label: '文本', icon: '📝' },
  { k: 'image', label: '图片', icon: '🖼' },
  { k: 'audio', label: '音频', icon: '🎧' },
  { k: 'video', label: '视频', icon: '🎬' },
  { k: 'tools', label: '工具', icon: '🔧' },
  { k: 'reasoning', label: '推理', icon: '🧠' },
]
const capIcon = (k: string) => CAPS.find((c) => c.k === k)?.icon ?? ''
const capLabel = (k: string) => CAPS.find((c) => c.k === k)?.label ?? k

export function ModelConfigModal({ onClose }: { onClose: () => void }) {
  const reloadModels = useSettingsStore((s) => s.reloadModels)
  const [providers, setProviders] = useState<Provider[]>([])
  const [custom, setCustom] = useState<ModelOption[]>([])
  const [effective, setEffective] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [keyDraft, setKeyDraft] = useState<Record<string, string>>({})
  const [modelDraft, setModelDraft] = useState<Record<string, string>>({})
  const [cfgDraft, setCfgDraft] = useState<Record<string, string>>({}) // 仅 Base URL（WB-132：去掉 chat_path 输入）
  const [fetched, setFetched] = useState<Record<string, string[]>>({})
  const [busy, setBusy] = useState(false)
  // 模型能力/成本编辑（WB-132）。metaEditing = 正在编辑的 model_ref。
  const [metaEditing, setMetaEditing] = useState<string | null>(null)
  const [metaDraft, setMetaDraft] = useState({ caps: [] as string[], input: '', output: '', ctx: '', note: '' })
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
  const deleteModel = async (p: Provider, mid: string) => {
    if (busy) return
    setBusy(true)
    try { await api.deleteProviderModel(p.id, mid); await refresh() }
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
  // Base URL 可编辑（WB-129/132：只留 base，chat_path 由后端 seed 兜底不暴露）
  const cfgOf = (p: Provider) => cfgDraft[p.id] ?? p.base_url
  const overridden = (p: Provider) => p.base_url !== p.default_base_url
  const saveCfg = async (p: Provider) => {
    if (busy) return
    setBusy(true)
    try {
      // chat_path 传 '' = 保持/回退到 seed 默认（含 MiniMax 非标路径）。
      await api.setProviderConfig(p.id, cfgOf(p).trim(), ''); toast('已保存接入地址')
      setCfgDraft((d) => { const n = { ...d }; delete n[p.id]; return n }); await refresh()
    } catch { toast('保存失败') } finally { setBusy(false) }
  }
  const resetCfg = async (p: Provider) => {
    if (busy) return
    setBusy(true)
    try {
      await api.setProviderConfig(p.id, '', ''); toast('已恢复默认地址')
      setCfgDraft((d) => { const n = { ...d }; delete n[p.id]; return n }); await refresh()
    } catch { toast('操作失败') } finally { setBusy(false) }
  }
  // ---- 模型能力/成本（WB-132）----
  const toggleMeta = (ref: string, meta?: ModelMeta) => {
    if (metaEditing === ref) { setMetaEditing(null); return }
    setMetaDraft({
      caps: [...(meta?.capabilities ?? [])],
      input: meta?.input_cost != null ? String(meta.input_cost) : '',
      output: meta?.output_cost != null ? String(meta.output_cost) : '',
      ctx: meta?.context_window != null ? String(meta.context_window) : '',
      note: meta?.note ?? '',
    })
    setMetaEditing(ref)
  }
  const toggleCap = (k: string) =>
    setMetaDraft((d) => ({ ...d, caps: d.caps.includes(k) ? d.caps.filter((x) => x !== k) : [...d.caps, k] }))
  const saveMeta = async (ref: string) => {
    if (busy) return
    const num = (s: string) => { const n = parseFloat(s); return s.trim() === '' || isNaN(n) ? null : n }
    const int = (s: string) => { const n = parseInt(s, 10); return s.trim() === '' || isNaN(n) ? null : n }
    setBusy(true)
    try {
      await api.setModelMeta(ref, {
        capabilities: metaDraft.caps, input_cost: num(metaDraft.input), output_cost: num(metaDraft.output),
        context_window: int(metaDraft.ctx), note: metaDraft.note.trim() || null,
      })
      toast('已保存能力/成本'); setMetaEditing(null); await refresh()
    } catch { toast('保存失败') } finally { setBusy(false) }
  }
  const resetMeta = async (ref: string) => {
    if (busy) return
    setBusy(true)
    try { await api.resetModelMeta(ref); toast('已恢复默认'); setMetaEditing(null); await refresh() }
    catch { toast('操作失败') } finally { setBusy(false) }
  }
  // 在线拉取厂商真实模型（WB-129）
  const fetchModels = async (p: Provider) => {
    if (busy) return
    setBusy(true)
    try {
      const r = await api.fetchProviderModels(p.id)
      if (r.ok && r.models) { setFetched({ ...fetched, [p.id]: r.models }); toast(`拉到 ${r.models.length} 个模型`) }
      else toast(r.error || '拉取失败')
    } catch { toast('拉取失败') } finally { setBusy(false) }
  }
  const addFetched = async (p: Provider, mid: string) => {
    if (busy) return
    setBusy(true)
    try { await api.addProviderModel(p.id, mid); await refresh() } catch { toast('添加失败') } finally { setBusy(false) }
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

  const capBadges = (meta?: ModelMeta) => (
    <span className="mc-caps">
      {(meta?.capabilities ?? []).map((c) => <span className="mc-cap" key={c} title={capLabel(c)}>{capIcon(c)}</span>)}
      {meta?.input_cost != null && <span className="mc-cost" title="每百万 token 输入/输出价">{meta.input_cost}/{meta.output_cost ?? '?'}</span>}
    </span>
  )
  const metaEditor = (ref: string) => (
    <div className="mc-metaed">
      <div className="mc-caprow">
        {CAPS.map((c) => (
          <button key={c.k} className={`mc-capchip ${metaDraft.caps.includes(c.k) ? 'on' : ''}`.trim()} onClick={() => toggleCap(c.k)}>{c.icon} {c.label}</button>
        ))}
      </div>
      <div className="mc-costrow">
        <input className="np-input" inputMode="decimal" placeholder="输入价/百万tok" value={metaDraft.input} onChange={(e) => setMetaDraft((d) => ({ ...d, input: e.target.value }))} />
        <input className="np-input" inputMode="decimal" placeholder="输出价/百万tok" value={metaDraft.output} onChange={(e) => setMetaDraft((d) => ({ ...d, output: e.target.value }))} />
        <input className="np-input" inputMode="numeric" placeholder="上下文 tokens" value={metaDraft.ctx} onChange={(e) => setMetaDraft((d) => ({ ...d, ctx: e.target.value }))} />
      </div>
      <div className="mc-fbtns">
        <button className="btn-ghost" disabled={busy} onClick={() => resetMeta(ref)}>恢复默认</button>
        <button className="btn-dark" disabled={busy} onClick={() => saveMeta(ref)}>保存能力/成本</button>
      </div>
    </div>
  )

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
                    <div className="mc-cfg">
                      <div className="mc-cfglbl">接入地址（可改成你的实际网关/代理）<a href={p.site} target="_blank" rel="noreferrer">获取 Key ↗</a></div>
                      <div className="mc-frow">
                        <input className="np-input" style={{ flex: 1 }} placeholder="Base URL，如 https://api.deepseek.com/v1" value={cfgOf(p)} onChange={(e) => setCfgDraft({ ...cfgDraft, [p.id]: e.target.value })} />
                        <button className="btn-dark" disabled={busy} onClick={() => saveCfg(p)}>保存地址</button>
                        {overridden(p) && <button className="btn-ghost" disabled={busy} onClick={() => resetCfg(p)}>恢复默认</button>}
                      </div>
                    </div>
                    <div className="mc-modhd">
                      <span>模型</span>
                      <button className="mc-act" disabled={!p.has_key || busy} onClick={() => fetchModels(p)} title={!p.has_key ? '先填 API Key' : '从厂商在线列举真实模型'}>↻ 拉取最新</button>
                    </div>
                    <div className="mc-modlist">
                      {p.models.filter((m) => !m.hidden).map((m) => {
                        const ref = `@${p.id}:${m.model_id}`
                        return (
                          <div key={m.model_id}>
                            <div className="mc-mod">
                              <span className="mc-modname">{m.model_id}{!m.preset && <span className="mc-tag">自加</span>}</span>
                              {capBadges(m.meta)}
                              <button className={`mc-act ${metaEditing === ref ? 'on' : ''}`.trim()} disabled={busy} onClick={() => toggleMeta(ref, m.meta)}>能力</button>
                              <button className="mc-act danger" disabled={busy} onClick={() => deleteModel(p, m.model_id)}>删除</button>
                            </div>
                            {metaEditing === ref && metaEditor(ref)}
                          </div>
                        )
                      })}
                    </div>
                    {fetched[p.id] && (
                      <div className="mc-fetched">
                        <div className="mc-fetchhd">厂商在线模型（{fetched[p.id].length}）</div>
                        {fetched[p.id].map((mid) => {
                          const exists = p.models.some((m) => m.model_id === mid && !m.hidden)
                          return (
                            <div className="mc-mod" key={mid}>
                              <span className="mc-modname">{mid}</span>
                              {exists ? <span className="mc-tag">已有</span> : <button className="mc-act" disabled={busy} onClick={() => addFetched(p, mid)}>添加</button>}
                            </div>
                          )
                        })}
                      </div>
                    )}
                    <div className="mc-keyrow">
                      <input className="np-input" placeholder="手动补充模型名" value={modelDraft[p.id] ?? ''} onChange={(e) => setModelDraft({ ...modelDraft, [p.id]: e.target.value })} />
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
            <div key={m.id}>
              <div className="mc-row">
                <span className="mc-ic">{m.icon}</span>
                <span className="mc-info">
                  <span className="mc-name">{m.name}{capBadges(m.meta)}</span>
                  <span className="mc-sub">{m.model_id}{m.api_base ? ` · ${m.api_base}` : ''}{m.has_key ? ' · 🔑' : ''}</span>
                </span>
                <button className={`mc-act ${metaEditing === m.key ? 'on' : ''}`.trim()} onClick={() => toggleMeta(m.key, m.meta)}>能力</button>
                <button className="mc-act" onClick={() => startEdit(m)}>编辑</button>
                <button className="mc-act danger" onClick={() => delCustom(m)}>删除</button>
              </div>
              {metaEditing === m.key && metaEditor(m.key)}
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
