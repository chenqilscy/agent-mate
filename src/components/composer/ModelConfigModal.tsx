import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { ModelGovernance, ModelMeta, ModelOption, ModelPolicy, Provider } from '../../lib/types'
import { useSettingsStore } from '../../stores/settingsStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'
import { App as AntApp } from 'antd'
import { IconPicker } from '../ui/IconPicker'

// 模型管理（WB-128/129/132）。内置厂商渠道（填一次 Key 即启用，Base URL 可改、可在线拉取真实模型）
// + 自定义模型兜底；每个模型可记「能力(模态/工具/推理)+成本」为 Auto 铺路。Key 只写不回读（铁律#4）。
// 套 .np-* / mc- 类，token 化天然暗色。

const BLANK = { name: '', model_id: '', api_base: '', api_key: '', icon: '🧩', mult: '' }
const EMPTY_POLICY = {
  allowlist: '', fallback: '', dailySoftTokens: '', dailyHardTokens: '',
  monthlySoftTokens: '', monthlyHardTokens: '', dailySoftCost: '', dailyHardCost: '',
  monthlySoftCost: '', monthlyHardCost: '', currency: 'USD', healthTtl: '900', credentialMaxAge: '90',
}

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

// embedded=true 时只渲染 np-body 内容（供「设置中心」模型 tab 内嵌，WB-146），不带自己的 overlay/标题/底栏。
export function ModelConfigModal({ onClose, embedded }: { onClose: () => void; embedded?: boolean }) {
  const { modal } = AntApp.useApp()
  const reloadModels = useSettingsStore((s) => s.reloadModels)
  const [providers, setProviders] = useState<Provider[]>([])
  const [custom, setCustom] = useState<ModelOption[]>([])
  // 账号默认模型 ref（WB-136）：未显式选模型时跟随它。'' = 未设置。
  const [defaultRef, setDefaultRef] = useState('')
  const [governance, setGovernance] = useState<ModelGovernance | null>(null)
  const [budgetDraft, setBudgetDraft] = useState('')
  const [policyDraft, setPolicyDraft] = useState({ ...EMPTY_POLICY })
  const [expanded, setExpanded] = useState<string | null>(null)
  const [keyDraft, setKeyDraft] = useState<Record<string, string>>({})
  const [modelDraft, setModelDraft] = useState<Record<string, string>>({})
  const [cfgDraft, setCfgDraft] = useState<Record<string, string>>({}) // 仅 Base URL（WB-132：去掉 chat_path 输入）
  const [fetched, setFetched] = useState<Record<string, string[]>>({})
  const [busy, setBusy] = useState(false)
  // 模型能力/成本编辑（WB-132）。metaEditing = 正在编辑的 model_ref。
  const [metaEditing, setMetaEditing] = useState<string | null>(null)
  const [metaDraft, setMetaDraft] = useState({ caps: [] as string[], input: '', cached: '', output: '', ctx: '', maxOutput: '', currency: '', note: '' })
  // custom form
  const [editing, setEditing] = useState<ModelOption | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ ...BLANK })

  const load = async () => {
    try {
      const [r, g] = await Promise.all([api.models(), api.modelGovernance()])
      setProviders(r.providers)
      setCustom(r.custom)
      setDefaultRef(r.default_model)
      setGovernance(g)
      setBudgetDraft(String(g.policy.default_run_token_budget || ''))
      setPolicyDraft({
        allowlist: g.policy.allowlist.join(', '), fallback: g.policy.fallback_chain.join(', '),
        dailySoftTokens: String(g.policy.daily_soft_tokens || ''), dailyHardTokens: String(g.policy.daily_hard_tokens || ''),
        monthlySoftTokens: String(g.policy.monthly_soft_tokens || ''), monthlyHardTokens: String(g.policy.monthly_hard_tokens || ''),
        dailySoftCost: String(g.policy.daily_soft_cost || ''), dailyHardCost: String(g.policy.daily_hard_cost || ''),
        monthlySoftCost: String(g.policy.monthly_soft_cost || ''), monthlyHardCost: String(g.policy.monthly_hard_cost || ''),
        currency: g.policy.currency || 'USD', healthTtl: String(g.policy.provider_health_ttl_seconds || 900),
        credentialMaxAge: String(g.policy.credential_max_age_days ?? 90),
      })
    } catch {
      toast('加载模型列表失败')
    }
  }
  useEffect(() => { load() }, [])

  const refresh = async () => { await load(); await reloadModels() }

  const saveGovernance = async () => {
    if (busy) return
    const parsed = Number.parseInt(budgetDraft.trim() || '0', 10)
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 10_000_000) {
      toast('请输入 0–10000000 的整数 token 预算')
      return
    }
    const integer = (value: string) => Number.parseInt(value.trim() || '0', 10)
    const decimal = (value: string) => Number.parseFloat(value.trim() || '0')
    const splitRefs = (value: string) => [...new Set(value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean))]
    const policy: ModelPolicy & { default_run_token_budget: number } = {
      default_run_token_budget: parsed,
      allowlist: splitRefs(policyDraft.allowlist), fallback_chain: splitRefs(policyDraft.fallback),
      daily_soft_tokens: integer(policyDraft.dailySoftTokens), daily_hard_tokens: integer(policyDraft.dailyHardTokens),
      monthly_soft_tokens: integer(policyDraft.monthlySoftTokens), monthly_hard_tokens: integer(policyDraft.monthlyHardTokens),
      daily_soft_cost: decimal(policyDraft.dailySoftCost), daily_hard_cost: decimal(policyDraft.dailyHardCost),
      monthly_soft_cost: decimal(policyDraft.monthlySoftCost), monthly_hard_cost: decimal(policyDraft.monthlyHardCost),
      currency: policyDraft.currency.trim().toUpperCase() || 'USD',
      provider_health_ttl_seconds: integer(policyDraft.healthTtl) || 900,
      credential_max_age_days: integer(policyDraft.credentialMaxAge),
    }
    if (Object.entries(policy).some(([key, value]) => key !== 'currency' && key !== 'allowlist' && key !== 'fallback_chain' && (!Number.isFinite(value as number) || (value as number) < 0))) {
      toast('预算与健康 TTL 必须是非负数字')
      return
    }
    setBusy(true)
    try {
      const g = await api.setModelGovernance(policy)
      setGovernance(g)
      setBudgetDraft(String(g.policy.default_run_token_budget || ''))
      toast('已保存模型治理策略')
    } catch { toast('保存失败') } finally { setBusy(false) }
  }

  // 设/清默认模型（WB-136）：再点当前默认 = 取消。写后端 DB 后刷新（picker 顶部「默认」条随之更新）。
  const setDefault = async (ref: string) => {
    if (busy) return
    const next = defaultRef === ref ? '' : ref
    setBusy(true)
    try {
      const r = await api.setDefaultModel(next)
      toast(next ? '已设为默认模型' : '已取消默认模型')
      setDefaultRef(r.default_model)
      await reloadModels()
    } catch { toast('操作失败') } finally { setBusy(false) }
  }

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
  const clearKey = (p: Provider) => {
    if (busy) return
    modal.confirm({
      title: `撤销「${p.name}」的 API Key？`,
      content: '撤销后，该厂商下的模型将不可用。',
      okText: '确认撤销',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setBusy(true)
        try { await api.setProviderKey(p.id, ''); toast('已撤销'); await refresh() }
        catch { toast('操作失败') }
        finally { setBusy(false) }
      },
    })
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
      cached: meta?.input_cost_cached != null ? String(meta.input_cost_cached) : '',
      output: meta?.output_cost != null ? String(meta.output_cost) : '',
      ctx: meta?.context_window != null ? String(meta.context_window) : '',
      maxOutput: meta?.max_output_tokens != null ? String(meta.max_output_tokens) : '',
      currency: meta?.currency ?? '',
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
        capabilities: metaDraft.caps, input_cost: num(metaDraft.input), input_cost_cached: num(metaDraft.cached),
        output_cost: num(metaDraft.output), context_window: int(metaDraft.ctx), max_output_tokens: int(metaDraft.maxOutput),
        currency: metaDraft.currency.trim() || null, note: metaDraft.note.trim() || null,
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
  const checkHealth = async (p: Provider) => {
    if (busy || !p.has_key) return
    setBusy(true)
    try {
      const result = await api.checkProviderHealth(p.id)
      toast(result.status === 'healthy' ? `连接健康 · ${result.latency_ms}ms` : `连接异常 · ${result.error_code}`)
      await refresh()
    } catch { toast('健康检查失败') } finally { setBusy(false) }
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
    const apiBase = form.api_base.trim(); const apiKey = form.api_key.trim()
    if (!name || !modelId || !apiBase || (!editing?.has_key && !apiKey) || busy) return
    setBusy(true)
    try {
      const payload = {
        name, model_id: modelId, api_base: apiBase, icon: form.icon.trim() || '🧩',
        ...(apiKey ? { api_key: apiKey } : {}),
      }
      if (editing?.id) await api.updateCustomModel(editing.id, payload)
      else await api.createCustomModel(payload)
      toast(editing ? '已保存' : '已添加模型'); cancelForm(); await refresh()
    } catch (e) { toast(String(e).includes('409') ? '已有同名模型' : '保存失败') }
    finally { setBusy(false) }
  }
  const delCustom = (m: ModelOption) => {
    if (!m.id || busy) return
    const modelId = m.id
    modal.confirm({
      title: `删除自定义模型「${m.name}」？`,
      content: '删除后不可恢复。',
      okText: '删除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        setBusy(true)
        try { await api.deleteCustomModel(modelId); toast('已删除'); if (editing?.id === modelId) cancelForm(); await refresh() }
        catch { toast('删除失败') }
        finally { setBusy(false) }
      },
    })
  }

  const cur = (meta?: ModelMeta) => meta?.currency || ''
  const capBadges = (meta?: ModelMeta) => (
    <span className="mc-caps">
      {(meta?.capabilities ?? []).map((c) => <span className="mc-cap" key={c} title={capLabel(c)}>{capIcon(c)}</span>)}
      {meta?.input_cost != null && <span className="mc-cost" title={`每百万 token 输入/输出价${meta.input_cost_cached != null ? `（缓存命中输入 ${meta.input_cost_cached}）` : ''}${meta.note ? ' · ' + meta.note : ''}`}>{cur(meta)}{meta.input_cost}/{meta.output_cost ?? '?'}</span>}
      {meta?.source === 'preset' && <span className="mc-src" title="来自厂商官方文档的默认值，可编辑">官方</span>}
    </span>
  )
  const metaEditor = (ref: string) => (
    <div className="mc-metaed">
      <div className="mc-caprow">
        {CAPS.map((c) => (
          <WbButton key={c.k} className={`mc-capchip ${metaDraft.caps.includes(c.k) ? 'on' : ''}`.trim()} onClick={() => toggleCap(c.k)}>{c.icon} {c.label}</WbButton>
        ))}
      </div>
      <div className="mc-costrow">
        <WbInput className="np-input" inputMode="decimal" placeholder="输入价/百万tok" value={metaDraft.input} onChange={(e) => setMetaDraft((d) => ({ ...d, input: e.target.value }))} />
        <WbInput className="np-input" inputMode="decimal" placeholder="缓存命中输入价" value={metaDraft.cached} onChange={(e) => setMetaDraft((d) => ({ ...d, cached: e.target.value }))} />
        <WbInput className="np-input" inputMode="decimal" placeholder="输出价/百万tok" value={metaDraft.output} onChange={(e) => setMetaDraft((d) => ({ ...d, output: e.target.value }))} />
      </div>
      <div className="mc-costrow">
        <WbInput className="np-input" inputMode="numeric" placeholder="上下文 tokens" value={metaDraft.ctx} onChange={(e) => setMetaDraft((d) => ({ ...d, ctx: e.target.value }))} />
        <WbInput className="np-input" inputMode="numeric" placeholder="单次输出 tokens" value={metaDraft.maxOutput} onChange={(e) => setMetaDraft((d) => ({ ...d, maxOutput: e.target.value }))} />
        <WbInput className="np-input" style={{ maxWidth: 96 }} placeholder="币种 ¥/$" maxLength={8} value={metaDraft.currency} onChange={(e) => setMetaDraft((d) => ({ ...d, currency: e.target.value }))} />
      </div>
      <div className="mc-fbtns">
        <WbButton className="btn-ghost" disabled={busy} onClick={() => resetMeta(ref)}>恢复默认</WbButton>
        <WbButton className="btn-dark" disabled={busy} onClick={() => saveMeta(ref)}>保存能力/成本</WbButton>
      </div>
    </div>
  )

  const body = (
        <div className="np-body">
          <section className="mc-governance" aria-label="本月模型用量与预算">
            <div className="mc-govhd">
              <div>
                <div className="np-lbl">本月模型用量</div>
                <div className="mc-hint">按 Run 的实际 token 与创建时价格估算；不同币种分别展示，不做汇率换算。</div>
              </div>
              <span className="mc-govperiod">
                {governance ? new Date(governance.usage.period_start * 1000).toLocaleDateString() : '—'} 起
              </span>
            </div>
            <div className="mc-govstats">
              <div className="set-stat"><span className="set-stat-n">{governance?.usage.runs ?? '—'}</span><span className="set-stat-l">运行</span></div>
              <div className="set-stat"><span className="set-stat-n">{governance ? governance.usage.total_tokens.toLocaleString() : '—'}</span><span className="set-stat-l">tokens</span></div>
              <div className="set-stat"><span className="set-stat-n mc-govcost">{governance?.usage.costs.length ? governance.usage.costs.map((c) => `${c.currency} ${c.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })}`).join(' · ') : '—'}</span><span className="set-stat-l">估算成本</span></div>
              <div className="set-stat"><span className="set-stat-n">{governance ? governance.usage.unpriced_runs + governance.usage.unresolved_runs : '—'}</span><span className="set-stat-l">未计价运行</span></div>
            </div>
            <div className="mc-budgetrow">
              <div className="mc-info">
                <span className="mc-name">默认单次 token 预算</span>
                <span className="mc-sub">仅在调用方未指定预算时生效；自动化、编排等显式预算优先。填 0 或留空表示不限制。</span>
              </div>
              <WbInput className="np-input" inputMode="numeric" aria-label="默认单次 token 预算" placeholder="0 = 不限制" value={budgetDraft} onChange={(e) => setBudgetDraft(e.target.value)} />
              <WbButton className="btn-dark" disabled={busy} onClick={saveGovernance}>保存策略</WbButton>
            </div>
            <div className="mc-budgetrow">
              <div className="mc-info">
                <span className="mc-name">允许模型与故障转移</span>
                <span className="mc-sub">模型 ref 用逗号分隔（如 @deepseek:deepseek-chat）；允许列表留空表示不限制，fallback 按顺序尝试最近健康的已配置模型。</span>
              </div>
              <WbInput className="np-input" aria-label="模型允许列表" placeholder="允许列表（留空=全部）" value={policyDraft.allowlist} onChange={(e) => setPolicyDraft((d) => ({ ...d, allowlist: e.target.value }))} />
              <WbInput className="np-input" aria-label="模型故障转移链" placeholder="fallback 顺序" value={policyDraft.fallback} onChange={(e) => setPolicyDraft((d) => ({ ...d, fallback: e.target.value }))} />
            </div>
            <div className="mc-budgetrow">
              <div className="mc-info">
                <span className="mc-name">日 / 月 token 软硬预算</span>
                <span className="mc-sub">软预算只提示；硬预算在调用前拒绝，并把剩余额度收紧为本次 Run 上限。0 表示不限制。</span>
              </div>
              <WbInput className="np-input" inputMode="numeric" aria-label="每日 token 软预算" placeholder="日软" value={policyDraft.dailySoftTokens} onChange={(e) => setPolicyDraft((d) => ({ ...d, dailySoftTokens: e.target.value }))} />
              <WbInput className="np-input" inputMode="numeric" aria-label="每日 token 硬预算" placeholder="日硬" value={policyDraft.dailyHardTokens} onChange={(e) => setPolicyDraft((d) => ({ ...d, dailyHardTokens: e.target.value }))} />
              <WbInput className="np-input" inputMode="numeric" aria-label="每月 token 软预算" placeholder="月软" value={policyDraft.monthlySoftTokens} onChange={(e) => setPolicyDraft((d) => ({ ...d, monthlySoftTokens: e.target.value }))} />
              <WbInput className="np-input" inputMode="numeric" aria-label="每月 token 硬预算" placeholder="月硬" value={policyDraft.monthlyHardTokens} onChange={(e) => setPolicyDraft((d) => ({ ...d, monthlyHardTokens: e.target.value }))} />
            </div>
            <div className="mc-budgetrow">
              <div className="mc-info">
                <span className="mc-name">日 / 月成本软硬预算</span>
                <span className="mc-sub">按 Run 价格快照估算，不做汇率换算；仅统计所填币种。</span>
              </div>
              <WbInput className="np-input" inputMode="decimal" aria-label="每日成本软预算" placeholder="日软" value={policyDraft.dailySoftCost} onChange={(e) => setPolicyDraft((d) => ({ ...d, dailySoftCost: e.target.value }))} />
              <WbInput className="np-input" inputMode="decimal" aria-label="每日成本硬预算" placeholder="日硬" value={policyDraft.dailyHardCost} onChange={(e) => setPolicyDraft((d) => ({ ...d, dailyHardCost: e.target.value }))} />
              <WbInput className="np-input" inputMode="decimal" aria-label="每月成本软预算" placeholder="月软" value={policyDraft.monthlySoftCost} onChange={(e) => setPolicyDraft((d) => ({ ...d, monthlySoftCost: e.target.value }))} />
              <WbInput className="np-input" inputMode="decimal" aria-label="每月成本硬预算" placeholder="月硬" value={policyDraft.monthlyHardCost} onChange={(e) => setPolicyDraft((d) => ({ ...d, monthlyHardCost: e.target.value }))} />
              <WbInput className="np-input" aria-label="预算币种" placeholder="USD" value={policyDraft.currency} onChange={(e) => setPolicyDraft((d) => ({ ...d, currency: e.target.value }))} />
              <WbInput className="np-input" inputMode="numeric" aria-label="健康状态有效秒数" placeholder="健康 TTL" value={policyDraft.healthTtl} onChange={(e) => setPolicyDraft((d) => ({ ...d, healthTtl: e.target.value }))} />
              <WbInput className="np-input" inputMode="numeric" aria-label="凭据轮换提醒天数" placeholder="Key 轮换天数" value={policyDraft.credentialMaxAge} onChange={(e) => setPolicyDraft((d) => ({ ...d, credentialMaxAge: e.target.value }))} />
            </div>
            {governance?.organization_policy && (
              <div className="mc-hint">当前项目继承组织策略 rev.{governance.organization_policy.revision}；运行时会取用户与组织策略中更严格的限制。</div>
            )}
          </section>
          <div className="np-lbl">内置厂商<small className="mc-lblhint">填一次 API Key 即启用该厂商模型 · Key 只存本机后端</small></div>
          {providers.map((p) => {
            const open = expanded === p.id
            return (
              <div className={`mc-prov ${open ? 'open' : ''}`.trim()} key={p.id}>
                <div className="mc-provhd" {...clickable} onClick={() => setExpanded(open ? null : p.id)}>
                  <span className="mc-ic" style={p.color ? { background: p.color, color: '#fff' } : undefined}>{p.icon}</span>
                  <span className="mc-info">
                    <span className="mc-name">{p.name}</span>
                    <span className="mc-sub">{p.has_key ? `已启用 · ${p.models.filter((m) => !m.hidden).length} 个模型${p.credential_updated_at ? ` · Key 更新于 ${new Date(p.credential_updated_at * 1000).toLocaleDateString()}` : ''}${p.credential_rotation_due ? ' · 建议轮换' : ''}` : '未配置 Key'}</span>
                  </span>
                  {p.has_key && <span className="mc-badge on">已启用</span>}
                  <span className="mc-caret">{open ? '▾' : '▸'}</span>
                </div>
                {open && (
                  <div className="mc-provbody">
                    <div className="mc-keyrow">
                      <WbInput
                        className="np-input" type="password" autoComplete="off"
                        placeholder={p.has_key ? '已配置，输入新 Key 覆盖（留空不改）' : `API Key，如 ${p.key_hint}`}
                        value={keyDraft[p.id] ?? ''} onChange={(e) => setKeyDraft({ ...keyDraft, [p.id]: e.target.value })}
                      />
                      <WbButton className="btn-dark" disabled={busy || (!(keyDraft[p.id] ?? '').trim() && p.has_key)} onClick={() => saveKey(p)}>保存</WbButton>
                      {p.has_key && <WbButton className="btn-ghost danger-b" disabled={busy} onClick={() => clearKey(p)}>撤销</WbButton>}
                    </div>
                    <div className="mc-cfg">
                      <div className="mc-cfglbl">接入地址（可改成你的实际网关/代理）<a href={p.site} target="_blank" rel="noreferrer">获取 Key ↗</a></div>
                      <div className="mc-frow">
                        <WbInput className="np-input" style={{ flex: 1 }} placeholder="Base URL，如 https://api.deepseek.com/v1" value={cfgOf(p)} onChange={(e) => setCfgDraft({ ...cfgDraft, [p.id]: e.target.value })} />
                        <WbButton className="btn-dark" disabled={busy} onClick={() => saveCfg(p)}>保存地址</WbButton>
                        {overridden(p) && <WbButton className="btn-ghost" disabled={busy} onClick={() => resetCfg(p)}>恢复默认</WbButton>}
                      </div>
                    </div>
                    <div className="mc-modhd">
                      <span>模型</span>
                      {p.has_key && <span className={`mc-badge ${p.health?.status === 'healthy' ? 'on' : ''}`.trim()}>{p.health ? (p.health.status === 'healthy' ? `健康 ${p.health.latency_ms}ms` : `异常 ${p.health.error_code}`) : '未检查'}</span>}
                      <WbButton className="mc-act" disabled={!p.has_key || busy} onClick={() => checkHealth(p)}>健康检查</WbButton>
                      <WbButton className="mc-act" disabled={!p.has_key || busy} onClick={() => fetchModels(p)} title={!p.has_key ? '先填 API Key' : '从厂商在线列举真实模型'}>↻ 拉取最新</WbButton>
                    </div>
                    <div className="mc-modlist">
                      {p.models.filter((m) => !m.hidden).map((m) => {
                        const ref = `@${p.id}:${m.model_id}`
                        return (
                          <div key={m.model_id}>
                            <div className="mc-mod">
                              <span className="mc-modname">{m.model_id}{!m.preset && <span className="mc-tag">自加</span>}{defaultRef === ref && <span className="mc-tag on">默认</span>}</span>
                              {capBadges(m.meta)}
                              {p.has_key && <WbButton className={`mc-act ${defaultRef === ref ? 'on' : ''}`.trim()} disabled={busy} onClick={() => setDefault(ref)} title="未显式选模型时用它">{defaultRef === ref ? '默认 ✓' : '设为默认'}</WbButton>}
                              <WbButton className={`mc-act ${metaEditing === ref ? 'on' : ''}`.trim()} disabled={busy} onClick={() => toggleMeta(ref, m.meta)}>能力</WbButton>
                              <WbButton className="mc-act danger" disabled={busy} onClick={() => deleteModel(p, m.model_id)}>删除</WbButton>
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
                              {exists ? <span className="mc-tag">已有</span> : <WbButton className="mc-act" disabled={busy} onClick={() => addFetched(p, mid)}>添加</WbButton>}
                            </div>
                          )
                        })}
                      </div>
                    )}
                    <div className="mc-keyrow">
                      <WbInput className="np-input" placeholder="手动补充模型名" value={modelDraft[p.id] ?? ''} onChange={(e) => setModelDraft({ ...modelDraft, [p.id]: e.target.value })} />
                      <WbButton className="btn-ghost" disabled={busy || !(modelDraft[p.id] ?? '').trim()} onClick={() => addModel(p)}>＋ 加模型</WbButton>
                    </div>
                  </div>
                )}
              </div>
            )
          })}

          <div className="np-lbl" style={{ marginTop: 20 }}>
            自定义模型<small className="mc-lblhint">预置厂商之外（自建/代理站）</small>
            {!showForm && <WbButton className="np-tplbtn" onClick={startNew}>＋ 添加</WbButton>}
          </div>
          {custom.length === 0 && !showForm && <div className="mc-empty">没有自定义模型。预置厂商够用就不必加。</div>}
          {custom.map((m) => (
            <div key={m.id}>
              <div className="mc-row">
                <span className="mc-ic">{m.icon}</span>
                <span className="mc-info">
                  <span className="mc-name">{m.name}{defaultRef === m.key && <span className="mc-tag on">默认</span>}{capBadges(m.meta)}</span>
                  <span className="mc-sub">{m.model_id}{m.api_base ? ` · ${m.api_base}` : ''}{m.has_key ? ' · 🔑' : ''}</span>
                </span>
                <WbButton className={`mc-act ${defaultRef === m.key ? 'on' : ''}`.trim()} disabled={busy} onClick={() => setDefault(m.key)} title="未显式选模型时用它">{defaultRef === m.key ? '默认 ✓' : '设为默认'}</WbButton>
                <WbButton className={`mc-act ${metaEditing === m.key ? 'on' : ''}`.trim()} onClick={() => toggleMeta(m.key, m.meta)}>能力</WbButton>
                <WbButton className="mc-act" onClick={() => startEdit(m)}>编辑</WbButton>
                <WbButton className="mc-act danger" onClick={() => delCustom(m)}>删除</WbButton>
              </div>
              {metaEditing === m.key && metaEditor(m.key)}
            </div>
          ))}
          {showForm && (
            <div className="mc-form">
              <div className="mc-frow">
                <IconPicker compact value={form.icon} onChange={(icon) => setForm({ ...form, icon })} ariaLabel="选择模型图标" />
                <WbInput className="np-input" style={{ flex: 1 }} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={80} placeholder="显示名，如 我的自建 Llama" />
              </div>
              <WbInput className="np-input" style={{ marginTop: 8 }} value={form.model_id} onChange={(e) => setForm({ ...form, model_id: e.target.value })} maxLength={120} placeholder="模型 id" />
              <WbInput className="np-input" style={{ marginTop: 8 }} value={form.api_base} onChange={(e) => setForm({ ...form, api_base: e.target.value })} maxLength={300} placeholder="API Base（必填），如 https://host/v1" />
              <WbInput className="np-input" type="password" style={{ marginTop: 8 }} value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} maxLength={400} placeholder={editing?.has_key ? 'API Key（已保存，留空不改）' : 'API Key（必填）'} autoComplete="off" />
              <div className="mc-hint">API Base 和 Key 只存本机后端模型 DB，绝不回传前端，也不依赖配置文件。</div>
              <div className="mc-fbtns">
                <WbButton className="btn-ghost" onClick={cancelForm}>取消</WbButton>
                <WbButton className="btn-dark" disabled={!form.name.trim() || !form.model_id.trim() || !form.api_base.trim() || (!editing?.has_key && !form.api_key.trim()) || busy} onClick={saveCustom}>{editing ? '保存' : '添加'}</WbButton>
              </div>
            </div>
          )}

          <div className="mc-empty" style={{ marginTop: 18 }}>
            {defaultRef
              ? '给某个模型点「设为默认」后，模型菜单顶部的「默认」条与未显式选模型的新会话都用它。再点一次可取消。'
              : '还没有设置默认模型：给上面任一已启用的模型点「设为默认」。未设置时，新会话需在模型菜单里手动选一个模型。'}
          </div>
        </div>
  )

  if (embedded) return body
  return (
    <AntModalBridge onClose={onClose} zIndex={170}>
      <div className="np-modal" role="dialog" aria-modal="true" aria-label="模型管理">
        <div className="np-h">模型管理<WbButton className="np-x" onClick={onClose}>×</WbButton></div>
        {body}
        <div className="np-foot">
          <span className="np-hint" style={{ marginRight: 'auto' }} />
          <WbButton className="btn-dark" onClick={onClose}>完成</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
