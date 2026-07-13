import { useEffect, useRef, useState } from 'react'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useCatalog } from '../stores/catalogStore'
import type { KbDocument } from '../lib/types'
import type { KbTemplate } from '../data/catalog'
import { toast } from '../stores/toastStore'

// 知识库（GLM RAG · WB-144）：建库 / 传档 / 向量化状态 / 用量，并可「挂载到对话」，
// 让 agent 用 knowledge_retrieve 真检索作答。真调智谱 GLM（经本地 backend，key 只在后端）。
// 复用 ExpertsView / 通用视图的 class 与 token（视觉零重设计）。

// 建库图标可选项（对应 GLM icon 字段）。
const ICONS = ['book', 'question', 'seal', 'wrench', 'tag', 'horn', 'house'] as const
const ICON_EMOJI: Record<string, string> = {
  book: '📚', question: '❓', seal: '🔖', wrench: '🔧', tag: '🏷️', horn: '📣', house: '🏠',
}
const EMBEDDINGS: [number, string][] = [
  [11, 'Embedding-3（推荐）'],
  [12, 'Embedding-3-pro'],
  [3, 'Embedding-2'],
]

function fmtBytes(n: number): string {
  if (!n) return '0'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// embedding_stat：1 成功 · 2 失败 · 其它（0/空）处理中。
function docStatus(d: KbDocument): { label: string; color: string; done: boolean } {
  if (d.embedding_stat === 1) return { label: '✓ 已向量化', color: 'var(--brand)', done: true }
  if (d.embedding_stat === 2) return { label: '✗ ' + (d.failInfo?.embedding_msg || '失败'), color: '#e5484d', done: true }
  return { label: '⏳ 向量化中…', color: 'var(--text-2)', done: false }
}

export function KnowledgeView() {
  const { kbs, capacity, loaded, load, create, remove, listDocs, uploadDoc, deleteDoc } = useKnowledgeStore()
  const knowledgeIds = useLoadoutStore((s) => s.knowledgeIds)
  const toggleLoadout = useLoadoutStore((s) => s.toggle)
  const { KB_TPLS } = useCatalog()

  const [openId, setOpenId] = useState<string | null>(null) // 打开详情的库 id
  const [prefill, setPrefill] = useState<KbTemplate | null>(null) // 「按模板新建」预填
  const [docs, setDocs] = useState<KbDocument[]>([])
  const [docsLoading, setDocsLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const poll = useRef<number | null>(null)
  const alive = useRef(true)

  const openKb = kbs.find((k) => k.id === openId) || null

  const stopPoll = () => { if (poll.current) { window.clearInterval(poll.current); poll.current = null } }

  useEffect(() => {
    alive.current = true
    void load()
    return () => { alive.current = false; stopPoll() }
  }, [load])

  const refreshDocs = async (id: string) => {
    try {
      const list = await listDocs(id)
      if (!alive.current) return
      setDocs(list)
      // 还有文档在向量化 → 起轮询，全部 done 则停。
      const pending = list.some((d) => !docStatus(d).done)
      if (pending && !poll.current) {
        poll.current = window.setInterval(() => { if (openId) void refreshDocs(openId) }, 4000)
      } else if (!pending) {
        stopPoll()
      }
    } catch {
      if (alive.current) toast('拉取文档失败')
    }
  }

  const openDetail = async (id: string) => {
    stopPoll()
    setOpenId(id)
    setDocs([])
    setDocsLoading(true)
    await refreshDocs(id)
    if (alive.current) setDocsLoading(false)
  }

  const closeDetail = () => { stopPoll(); setOpenId(null); setDocs([]) }

  const doUpload = async (files: FileList | null) => {
    if (!files || !files.length || !openId) return
    setUploading(true)
    let ok = 0
    for (const f of Array.from(files)) {
      try { await uploadDoc(openId, f); ok += 1 }
      catch (e) { toast(`「${f.name}」上传失败：${(e as Error).message}`) }
    }
    setUploading(false)
    if (ok) { toast(`已上传 ${ok} 个文档，向量化进行中…`); await refreshDocs(openId) }
    if (fileInput.current) fileInput.current.value = ''
  }

  const onDelDoc = async (d: KbDocument) => {
    if (!confirm(`删除文档「${d.name}」？`)) return
    try { await deleteDoc(d.id); if (openId) await refreshDocs(openId) }
    catch { toast('删除失败') }
  }

  const onDelKb = async (id: string, name: string) => {
    if (!confirm(`删除知识库「${name}」？其中所有文档将一并删除，且不可恢复。`)) return
    try { await remove(id); toast('已删除知识库'); if (openId === id) closeDetail() }
    catch { toast('删除失败') }
  }

  const onMount = (id: string, name: string) => {
    const on = knowledgeIds.includes(id)
    toggleLoadout('kb', id)
    toast(on ? `已从对话取消挂载「${name}」` : `已挂载「${name}」到对话，去输入框提问即可检索`)
  }

  const usedPct = capacity && capacity.total.length
    ? Math.min(100, (capacity.used.length / capacity.total.length) * 100)
    : 0

  return (
    <section className="view active" data-view="knowledge">
      <div className="page-scroll">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800 }}>📚 知识库</h1>
            <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6, lineHeight: 1.7 }}>
              基于智谱 GLM 的知识库：上传文档并向量化，在对话中「挂载」后让 AI 检索作答、注明来源。
              密钥只存本机后端，绝不进前端。
            </div>
          </div>
          {!openKb && (
            <button className="hub-act on" onClick={() => { setPrefill(null); setShowCreate(true) }}>+ 新建知识库</button>
          )}
        </div>

        {/* 用量条 + 计价提示 */}
        {capacity && (
          <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--panel-2, rgba(127,127,127,.06))', borderRadius: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--text-2)' }}>
              <span>存储用量</span>
              <span>{fmtBytes(capacity.used.length)} / {fmtBytes(capacity.total.length)}（{capacity.used.word_num.toLocaleString()} 字）</span>
            </div>
            <div style={{ height: 6, background: 'rgba(127,127,127,.18)', borderRadius: 4, marginTop: 6, overflow: 'hidden' }}>
              <div style={{ width: `${usedPct}%`, height: '100%', background: 'var(--brand)', borderRadius: 4 }} />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6 }}>
              1GB 免费额度，超出 0.04 元/GB/小时；Embedding-3 系列 0.5 元/百万 token；检索重排 0.8 元/百万 token。
            </div>
          </div>
        )}

        {/* 从模板新建（Manager 下发的策展模板，橱窗）*/}
        {!openKb && KB_TPLS.length > 0 && (
          <>
            <div className="sec-title" style={{ marginTop: 18 }}>从模板新建</div>
            <div className="card-grid g4" style={{ marginTop: 10 }}>
              {KB_TPLS.map((t) => (
                <div key={t.key} className="scard clickable" style={{ cursor: 'pointer' }}
                  onClick={() => { setPrefill(t); setShowCreate(true) }}>
                  <span className="sc-ic" style={{ fontSize: 22 }}>{t.icon || '📚'}</span>
                  <div className="sc-info" style={{ minWidth: 0 }}>
                    <div className="sc-n" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {t.name}
                      {!!t.contextual && <span className="ec-tag" style={{ fontSize: 10 }}>增强</span>}
                    </div>
                    <div className="sc-d">{t.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ── 列表态 ─────────────────────────────────────────────── */}
        {!openKb && (
          <>
            <div className="sec-title" style={{ marginTop: 18 }}>我的知识库</div>
            {!loaded && <div className="mf-empty">正在加载…</div>}
            {loaded && kbs.length === 0 && (
              <div className="mf-empty" style={{ flexDirection: 'column', gap: 8, textAlign: 'center', lineHeight: 1.7 }}>
                <div>还没有知识库。</div>
                <div style={{ fontSize: 12, color: 'var(--text-2)' }}>
                  点右上「新建知识库」创建一个，再上传文档。若提示需要配置密钥，请去左侧「更多 · 模型管理」为「智谱 AI·GLM」填入 API Key。
                </div>
              </div>
            )}
            {kbs.length > 0 && (
              <div className="card-grid g2" style={{ marginTop: 16 }}>
                {kbs.map((k) => {
                  const mounted = knowledgeIds.includes(k.id)
                  return (
                    <div key={k.id} className="scard" style={{ alignItems: 'flex-start' }}>
                      <span className="sc-ic" style={{ fontSize: 22 }}>{ICON_EMOJI[k.icon || 'book'] || '📚'}</span>
                      <div className="sc-info" style={{ minWidth: 0, flex: 1 }}>
                        <div className="sc-n" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {k.name}
                          {!!k.contextual && <span className="ec-tag" style={{ fontSize: 10 }}>上下文增强</span>}
                          {mounted && <span className="ec-tag" style={{ fontSize: 10, background: 'var(--brand)', color: '#fff' }}>已挂载</span>}
                        </div>
                        <div className="sc-d">{k.description || '（无描述）'}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                          {(k.document_size ?? 0)} 个文档{k.word_num ? ` · ${k.word_num.toLocaleString()} 字` : ''}
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                          <button className="btn-dark" onClick={() => openDetail(k.id)}>管理文档</button>
                          <button className={mounted ? 'btn-dark' : 'btn-ghost'} onClick={() => onMount(k.id, k.name)}>
                            {mounted ? '取消挂载' : '挂载到对话'}
                          </button>
                          <button className="btn-ghost" onClick={() => onDelKb(k.id, k.name)}>删除</button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {/* ── 详情态：某个库的文档管理 ───────────────────────────── */}
        {openKb && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <button className="btn-ghost" onClick={closeDetail}>← 返回</button>
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                {ICON_EMOJI[openKb.icon || 'book'] || '📚'} {openKb.name}
              </div>
              <span style={{ flex: 1 }} />
              <button className="btn-dark" onClick={() => fileInput.current?.click()} disabled={uploading}>
                {uploading ? '上传中…' : '+ 上传文档'}
              </button>
              <input ref={fileInput} type="file" multiple hidden
                accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv"
                onChange={(e) => doUpload(e.target.files)} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', margin: '8px 2px 0' }}>
              支持 txt / md / pdf / doc(x) / ppt(x) / xls(x) / csv，单文件 ≤ 50MB。上传后自动向量化，完成才可被检索。
            </div>

            {/* 拖拽上传区 */}
            <div
              onDragOver={(e) => { e.preventDefault() }}
              onDrop={(e) => { e.preventDefault(); void doUpload(e.dataTransfer.files) }}
              className="mf-empty"
              style={{ marginTop: 14, border: '1.5px dashed rgba(127,127,127,.35)', borderRadius: 10, cursor: 'pointer' }}
              onClick={() => fileInput.current?.click()}
            >
              {uploading ? '上传中…' : '拖拽文件到此，或点击选择文件上传'}
            </div>

            <div style={{ fontSize: 12, color: 'var(--text-2)', margin: '14px 2px 8px' }}>
              {docsLoading ? '加载中…' : `共 ${docs.length} 个文档`}
            </div>
            {docs.length === 0 && !docsLoading && (
              <div className="mf-empty">此知识库还没有文档，上传一个开始。</div>
            )}
            <div className="kd-list">
              {docs.map((d) => {
                const st = docStatus(d)
                return (
                  <div key={d.id} className="kd-item" style={{ cursor: 'default' }}>
                    <span className="kd-ic">📄</span>
                    <div className="kd-main">
                      <div className="kd-name">{d.name}</div>
                      <div className="kd-meta">
                        <span style={{ color: st.color }}>{st.label}</span>
                        {d.word_num ? ` · ${d.word_num.toLocaleString()} 字` : ''}
                      </div>
                    </div>
                    <button className="btn-ghost" onClick={() => onDelDoc(d)}>删除</button>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {/* 新建知识库弹窗 */}
      {showCreate && (
        <CreateKbModal
          creating={creating}
          tpl={prefill}
          onClose={() => setShowCreate(false)}
          onCreate={async (body) => {
            setCreating(true)
            try {
              await create(body)
              toast('已创建知识库')
              setShowCreate(false)
            } catch (e) {
              toast(`创建失败：${(e as Error).message}`)
            } finally {
              setCreating(false)
            }
          }}
        />
      )}
    </section>
  )
}

// 建库弹窗：名称 / 描述 / embedding 模型 / 图标 / 上下文增强开关。复用 np-* 弹窗 class。
// tpl（可选）= 从模板新建时的预填（Manager 下发的策展模板）。
function CreateKbModal(props: {
  creating: boolean
  tpl?: KbTemplate | null
  onClose: () => void
  onCreate: (body: { name: string; description: string; embedding_id: number; contextual: number; icon: string }) => void
}) {
  const t = props.tpl
  // 模板 icon 存的是 emoji；建库弹窗按 GLM icon 关键字选择，emoji 对不上就回退 book。
  const iconKey = t ? (ICONS.find((k) => ICON_EMOJI[k] === t.icon) ?? 'book') : 'book'
  const [name, setName] = useState(t?.name ?? '')
  const [description, setDescription] = useState(t?.desc ?? '')
  const [embeddingId, setEmbeddingId] = useState(t?.embedding_id ?? 11)
  const [icon, setIcon] = useState<string>(iconKey)
  const [contextual, setContextual] = useState(!!t?.contextual)

  return (
    <div className="np-overlay open" onClick={props.onClose}>
      <div className="np-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="np-h">
          新建知识库
          <button className="np-x" onClick={props.onClose}>✕</button>
        </div>
        <div className="np-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            名称
            <input className="np-input" style={{ marginTop: 6, width: '100%' }} value={name} autoFocus
              placeholder="如：产品手册库" onChange={(e) => setName(e.target.value)} />
          </label>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            描述（可选）
            <input className="np-input" style={{ marginTop: 6, width: '100%' }} value={description}
              placeholder="这个知识库放什么资料" onChange={(e) => setDescription(e.target.value)} />
          </label>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            向量模型
            <select className="np-input" style={{ marginTop: 6, width: '100%' }} value={embeddingId}
              onChange={(e) => setEmbeddingId(Number(e.target.value))}>
              {EMBEDDINGS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
          </label>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            图标
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              {ICONS.map((ic) => (
                <button key={ic} type="button"
                  className={icon === ic ? 'btn-dark' : 'btn-ghost'}
                  style={{ fontSize: 18, padding: '4px 8px' }}
                  onClick={() => setIcon(ic)}>{ICON_EMOJI[ic]}</button>
              ))}
            </div>
          </div>
          <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8 }}>
            <input type="checkbox" checked={contextual} onChange={(e) => setContextual(e.target.checked)} />
            开启上下文增强（长文档召回更准，建库后处理稍慢；免费）
          </label>
        </div>
        <div className="np-foot">
          <button className="btn-ghost" onClick={props.onClose}>取消</button>
          <button className="btn-dark" disabled={!name.trim() || props.creating}
            onClick={() => props.onCreate({ name: name.trim(), description: description.trim(), embedding_id: embeddingId, contextual: contextual ? 1 : 0, icon })}>
            {props.creating ? '创建中…' : '创建'}
          </button>
        </div>
      </div>
    </div>
  )
}
