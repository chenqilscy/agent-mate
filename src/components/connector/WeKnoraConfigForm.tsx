import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import type { KnowledgeConfig } from '../../lib/types'
import { toast } from '../../stores/toastStore'

// WeKnora 连接配置表单（WB-188）——取代「改 backend/.env + 重启后端」。
// 配置存本机后端（按 owner；DB 优先、.env 兜底），API Key **只写不回读**：后端只回
// has_key 布尔，故输入框永远空起手，已配置时靠 placeholder 提示「输入新 Key 覆盖」，
// 撤销走单独按钮（与模型管理的厂商 Key 同一套语义）。
// 样式复用模型管理那套 mc-* / np-input / btn-* class，不新造（铁律#2）。

export function WeKnoraConfigForm({ onChange }: { onChange?: (c: KnowledgeConfig) => void }) {
  const [cfg, setCfg] = useState<KnowledgeConfig | null>(null)
  const [urlDraft, setUrlDraft] = useState('')
  const [keyDraft, setKeyDraft] = useState('')
  const [embDraft, setEmbDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState(false)

  const apply = (c: KnowledgeConfig) => {
    setCfg(c)
    setUrlDraft(c.url)
    setEmbDraft(c.embedding_model_id)
    setKeyDraft('')      // key 不回读，永远空起手
    onChange?.(c)
  }

  const load = async () => {
    try { apply(await api.knowledgeConfig()) } catch { /* 未登录/后端未起：保持空表单 */ }
  }
  useEffect(() => { void load() }, [])

  // 逐项即时保存（同 ModelConfigModal：每行各自一个按钮，无全局保存）。
  const save = async (patch: { url?: string; api_key?: string; embedding_model_id?: string }, msg: string) => {
    setBusy(true)
    try {
      apply(await api.saveKnowledgeConfig(patch))
      toast(msg)
    } catch (e) {
      toast(e instanceof Error ? e.message : '保存失败')
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setTesting(true)
    try {
      const r = await api.testKnowledgeConfig()
      // 后端约定：连不通也是 200，错误在 error 字段 —— 原样回显厂商/网络的真实错误。
      toast(r.ok ? `连接成功 · ${r.url} · ${r.kb_count} 个知识库` : (r.error || '连接失败'))
    } catch (e) {
      toast(e instanceof Error ? e.message : '测试失败')
    } finally {
      setTesting(false)
    }
  }

  if (!cfg) return <div className="mc-hint">读取配置中…</div>

  const urlDirty = urlDraft.trim().replace(/\/+$/, '') !== cfg.url
  const embDirty = embDraft.trim() !== cfg.embedding_model_id

  return (
    <div className="mc-form">
      {/* 服务地址 */}
      <div className="mc-cfg" style={{ marginTop: 0 }}>
        <div className="mc-cfglbl">服务地址（WeKnora 实例，默认 http://localhost:8080）</div>
        <div className="mc-frow">
          <WbInput
            className="np-input" placeholder="http://localhost:8080" value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)} spellCheck={false}
          />
          <WbButton
            type="button" className="btn-dark" disabled={busy || !urlDirty}
            onClick={() => void save({ url: urlDraft.trim() }, '已保存服务地址')}
          >保存</WbButton>
          {cfg.url_source === 'db' && (
            <WbButton
              type="button" className="btn-ghost" disabled={busy}
              onClick={() => void save({ url: '' }, '已恢复默认地址')}
            >恢复默认</WbButton>
          )}
        </div>
      </div>

      {/* API Key —— 只写不回读 */}
      <div className="mc-cfg">
        <div className="mc-cfglbl">API Key（WeKnora 账号页的租户 Key，sk- 开头）</div>
        <div className="mc-keyrow" style={{ marginTop: 0 }}>
          <WbInput
            className="np-input" type="password" autoComplete="off" spellCheck={false}
            placeholder={cfg.has_key ? '已配置，输入新 Key 覆盖（留空不改）' : 'API Key，如 sk-…'}
            value={keyDraft} onChange={(e) => setKeyDraft(e.target.value)}
          />
          <WbButton
            type="button" className="btn-dark" disabled={busy || !keyDraft.trim()}
            onClick={() => void save({ api_key: keyDraft.trim() }, '已保存 API Key')}
          >保存</WbButton>
          {cfg.key_source === 'db' && (
            <WbButton
              type="button" className="btn-ghost danger-b" disabled={busy}
              onClick={() => void save({ api_key: '' }, '已撤销 API Key')}
            >撤销</WbButton>
          )}
        </div>
      </div>

      {/* 嵌入模型 id（选填） */}
      <div className="mc-cfg">
        <div className="mc-cfglbl">嵌入模型 id（选填，留空则自动取 WeKnora 里第一个 Embedding 模型）</div>
        <div className="mc-frow">
          <WbInput
            className="np-input" placeholder="如 builtin:bge-m3 / 你在 WeKnora 注册的模型 id"
            value={embDraft} onChange={(e) => setEmbDraft(e.target.value)} spellCheck={false}
          />
          <WbButton
            type="button" className="btn-dark" disabled={busy || !embDirty}
            onClick={() => void save({ embedding_model_id: embDraft.trim() }, '已保存嵌入模型')}
          >保存</WbButton>
        </div>
      </div>

      <div className="mc-fbtns">
        <WbButton type="button" className="btn-ghost" disabled={testing || !cfg.has_key} onClick={() => void test()}>
          {testing ? '测试中…' : '测试连接'}
        </WbButton>
      </div>

      <div className="mc-hint">
        {cfg.has_key
          ? (cfg.key_source === 'env'
              ? 'Key 当前来自 backend/.env；在上面填一个即可改为本机 DB 存储（优先生效）。'
              : 'Key 已存本机后端（不回传前端，无法回显）。填错了就重填一个覆盖。')
          : '填入 API Key 后即可接入。密钥只存本机后端，绝不进前端。'}
      </div>
    </div>
  )
}
