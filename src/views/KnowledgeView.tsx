import { WbButton, WbInput } from '../components/ui/Primitives'
import { useEffect, useRef, useState } from 'react'
import { useKnowledgeStore } from '../stores/knowledgeStore'
import { useLoadoutStore } from '../stores/loadoutStore'
import { useCatalog } from '../stores/catalogStore'
import { api } from '../lib/api'
import type { KbDocument, KnowledgeConfig } from '../lib/types'
import type { KbTemplate } from '../data/catalog'
import { toast } from '../stores/toastStore'
import { WeKnoraConfigForm } from '../components/connector/WeKnoraConfigForm'
import { AntModalBridge } from '../components/ui/AntModalBridge'
import { Empty, List, Spin, Tag, Upload } from 'antd'
import { ProCard } from '@ant-design/pro-components'

// 知识库（自托管 WeKnora RAG · WB-173/174）：建库 / 传档 / 解析状态，并可「挂载到对话」，
// 让 agent 用 knowledge_retrieve 真检索作答。真调 WeKnora（经本地 backend，API Key 只在后端）。
// 复用 ExpertsView / 通用视图的 class 与 token（视觉零重设计）。

// 建库图标可选项（纯前端展示；WeKnora 侧无图标概念）。
const ICONS = ['book', 'question', 'seal', 'wrench', 'tag', 'horn', 'house'] as const
const ICON_EMOJI: Record<string, string> = {
  book: '📚', question: '❓', seal: '🔖', wrench: '🔧', tag: '🏷️', horn: '📣', house: '🏠',
}

// embedding_stat：1 成功 · 2 失败 · 其它（0/空）处理中。
function docStatus(d: KbDocument): { label: string; color: string; done: boolean } {
  if (d.embedding_stat === 1) return { label: '✓ 已向量化', color: 'var(--brand)', done: true }
  if (d.embedding_stat === 2) return { label: '✗ ' + (d.failInfo?.embedding_msg || '失败'), color: '#e5484d', done: true }
  return { label: '⏳ 向量化中…', color: 'var(--text-2)', done: false }
}

export function KnowledgeView() {
  const { kbs, loaded, load, create, remove, listDocs, uploadDoc, deleteDoc } = useKnowledgeStore()
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
  // 未接入 WeKnora 时就地给配置表单（WB-188），而不是让用户去改 .env / 找管理员。
  const [cfg, setCfg] = useState<KnowledgeConfig | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const poll = useRef<number | null>(null)
  const alive = useRef(true)

  const openKb = kbs.find((k) => k.id === openId) || null
  // 配置未知（还在拉 / 拉失败）时按「已接入」渲染：列表自己会报错或给空态，
  // 总比整页空白好。只有**确知**未接入才把页面换成配置表单。
  const configured = cfg ? cfg.configured : true

  const stopPoll = () => { if (poll.current) { window.clearInterval(poll.current); poll.current = null } }

  useEffect(() => {
    alive.current = true
    void load()
    api.knowledgeConfig().then((c) => { if (alive.current) setCfg(c) }).catch(() => {})
    return () => { alive.current = false; stopPoll() }
  }, [load])

  const refreshDocs = async (id: string) => {
    try {
      const list = await listDocs(id)
      if (!alive.current) return
      setDocs(list)
      // 还有文档在向量化 → 起轮询，全部 done 则停。用 id 参数（不是 openId state——
      // openDetail 调用时 openId 闭包还是旧值 null，会让轮询守卫恒假空转，WB-151）。
      const pending = list.some((d) => !docStatus(d).done)
      if (pending && !poll.current) {
        poll.current = window.setInterval(() => { void refreshDocs(id) }, 4000)
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

  const doUpload = async (files: FileList | File[] | null) => {
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

  return (
    <section className="view active" data-view="knowledge">
      <div className="page-scroll">
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 22, fontWeight: 800 }}>📚 知识库</h1>
            <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 6, lineHeight: 1.7 }}>
              基于自托管 WeKnora 的知识库：上传文档由 WeKnora 解析并向量化，在对话中「挂载」后让 AI 检索作答、注明来源。
              API Key 只存本机后端，绝不进前端。
            </div>
          </div>
          {!openKb && configured && (
            <WbButton className="cap-act on" onClick={() => { setPrefill(null); setShowCreate(true) }}>+ 新建知识库</WbButton>
          )}
        </div>

        {/* 未接入：就地给连接配置表单（WB-188），填完即用 —— 不必改配置文件、不必重启 */}
        {cfg && !cfg.configured && (
          <>
            <div className="sec-title" style={{ marginTop: 18 }}>接入知识库</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 6, lineHeight: 1.65 }}>
              还没接入 WeKnora。填下面的服务地址与 API Key 即可开始建库、传档（也可在「连接器 → WeKnora知识库」里配置）。
              WeKnora 本身的部署见 docs/weknora-部署.md。
            </div>
            <WeKnoraConfigForm onChange={(c) => { setCfg(c); if (c.configured) void load() }} />
          </>
        )}

        {/* 从模板新建（Console 下发的策展模板，橱窗）。未接入时不给——点了必然 400。*/}
        {!openKb && configured && KB_TPLS.length > 0 && (
          <>
            <div className="sec-title" style={{ marginTop: 18 }}>从模板新建</div>
            <div className="card-grid g4" style={{ marginTop: 10 }}>
              {KB_TPLS.map((t) => (
                 <ProCard key={t.key} className="scard clickable" hoverable styles={{ body: { display: 'contents' } }}
                   onClick={() => { setPrefill(t); setShowCreate(true) }}>
                  <span className="sc-ic" style={{ fontSize: 22 }}>{t.icon || '📚'}</span>
                  <div className="sc-info" style={{ minWidth: 0 }}>
                    <div className="sc-n" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      {t.name}
                      {!!t.contextual && <Tag className="ec-tag">增强</Tag>}
                    </div>
                    <div className="sc-d">{t.desc}</div>
                  </div>
                </ProCard>
              ))}
            </div>
          </>
        )}

        {/* ── 列表态 ─────────────────────────────────────────────── */}
        {!openKb && configured && (
          <>
            <div className="sec-title" style={{ marginTop: 18 }}>我的知识库</div>
            {!loaded && <Spin className="mf-empty" tip="正在加载…" />}
            {loaded && kbs.length === 0 && configured && (
              <Empty className="mf-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有知识库。点右上「新建知识库」创建一个，再上传文档。" />
            )}
            {kbs.length > 0 && (
              <div className="card-grid g2" style={{ marginTop: 16 }}>
                {kbs.map((k) => {
                  const mounted = knowledgeIds.includes(k.id)
                  return (
                    <ProCard key={k.id} className="scard" styles={{ body: { display: 'contents' } }}>
                      <span className="sc-ic" style={{ fontSize: 22 }}>{ICON_EMOJI[k.icon || 'book'] || '📚'}</span>
                      <div className="sc-info" style={{ minWidth: 0, flex: 1 }}>
                        <div className="sc-n" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          {k.name}
                          {mounted && <Tag color="success" className="ec-tag">已挂载</Tag>}
                        </div>
                        <div className="sc-d">{k.description || '（无描述）'}</div>
                        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                          {(k.document_size ?? 0)} 个文档{k.word_num ? ` · ${k.word_num.toLocaleString()} 字` : ''}
                        </div>
                        <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
                          <WbButton className="btn-dark" onClick={() => openDetail(k.id)}>管理文档</WbButton>
                          <WbButton className={mounted ? 'btn-dark' : 'btn-ghost'} onClick={() => onMount(k.id, k.name)}>
                            {mounted ? '取消挂载' : '挂载到对话'}
                          </WbButton>
                          <WbButton className="btn-ghost" onClick={() => onDelKb(k.id, k.name)}>删除</WbButton>
                        </div>
                      </div>
                    </ProCard>
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
              <WbButton className="btn-ghost" onClick={closeDetail}>← 返回</WbButton>
              <div style={{ fontSize: 16, fontWeight: 700 }}>
                {ICON_EMOJI[openKb.icon || 'book'] || '📚'} {openKb.name}
              </div>
              <span style={{ flex: 1 }} />
              <WbButton className="btn-dark" onClick={() => fileInput.current?.click()} disabled={uploading}>
                {uploading ? '上传中…' : '+ 上传文档'}
              </WbButton>
              <WbInput ref={fileInput} type="file" multiple hidden
                accept=".txt,.md,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.csv,.html,.htm,.png,.jpg,.jpeg,.gif,.bmp,.webp"
                onChange={(e) => doUpload(e.target.files)} />
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', margin: '8px 2px 0' }}>
              支持 pdf / doc(x) / ppt(x) / xls(x) / txt / md / html / csv / 图片，单文件 ≤ 50MB。上传后由 WeKnora 解析向量化，完成才可被检索。
            </div>

            {/* Ant Upload.Dragger 统一拖拽、键盘和文件选择交互；上传仍走本地真实 API。 */}
            <Upload.Dragger
              className="mf-empty"
              multiple
              showUploadList={false}
              disabled={uploading}
              beforeUpload={(file, fileList) => {
                if (file === fileList[0]) void doUpload(fileList)
                return Upload.LIST_IGNORE
              }}
            >
              {uploading ? <Spin tip="上传中…" /> : <p>拖拽文件到此，或点击选择文件上传</p>}
            </Upload.Dragger>

            <div style={{ fontSize: 12, color: 'var(--text-2)', margin: '14px 2px 8px' }}>
              {docsLoading ? '加载中…' : `共 ${docs.length} 个文档`}
            </div>
            {docs.length === 0 && !docsLoading && (
              <Empty className="mf-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="此知识库还没有文档，上传一个开始。" />
            )}
            <List className="kd-list" dataSource={docs} renderItem={(d) => {
                 const st = docStatus(d)
                 return (
                  <List.Item key={d.id} className="kd-item" style={{ cursor: 'default' }}>
                    <span className="kd-ic">📄</span>
                    <div className="kd-main">
                      <div className="kd-name">{d.name}</div>
                      <div className="kd-meta">
                        <span style={{ color: st.color }}>{st.label}</span>
                        {d.word_num ? ` · ${d.word_num.toLocaleString()} 字` : ''}
                      </div>
                    </div>
                    <WbButton className="btn-ghost" onClick={() => onDelDoc(d)}>删除</WbButton>
                  </List.Item>
                )
              }} />
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

// 建库弹窗：名称 / 描述 / 图标。复用 np-* 弹窗 class。嵌入模型由 WeKnora 服务端配置，前端无需选。
// tpl（可选）= 从模板新建时的预填（Console 下发的策展模板）。
function CreateKbModal(props: {
  creating: boolean
  tpl?: KbTemplate | null
  onClose: () => void
  onCreate: (body: { name: string; description: string; icon: string }) => void
}) {
  const t = props.tpl
  // 模板 icon 存的是 emoji；建库弹窗按 icon 关键字选择，emoji 对不上就回退 book。
  const iconKey = t ? (ICONS.find((k) => ICON_EMOJI[k] === t.icon) ?? 'book') : 'book'
  const [name, setName] = useState(t?.name ?? '')
  const [description, setDescription] = useState(t?.desc ?? '')
  const [icon, setIcon] = useState<string>(iconKey)

  return (
    <AntModalBridge onClose={props.onClose} closeOnMask={!props.creating}>
      <div className="np-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 460 }}>
        <div className="np-h">
          新建知识库
          <WbButton className="np-x" onClick={props.onClose}>✕</WbButton>
        </div>
        <div className="np-body" style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            名称
            <WbInput className="np-input" style={{ marginTop: 6, width: '100%' }} value={name} autoFocus
              placeholder="如：产品手册库" onChange={(e) => setName(e.target.value)} />
          </label>
          <label style={{ fontSize: 13, fontWeight: 600 }}>
            描述（可选）
            <WbInput className="np-input" style={{ marginTop: 6, width: '100%' }} value={description}
              placeholder="这个知识库放什么资料" onChange={(e) => setDescription(e.target.value)} />
          </label>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            图标
            <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
              {ICONS.map((ic) => (
                <WbButton key={ic} type="button"
                  className={icon === ic ? 'btn-dark' : 'btn-ghost'}
                  style={{ fontSize: 18, padding: '4px 8px' }}
                  onClick={() => setIcon(ic)}>{ICON_EMOJI[ic]}</WbButton>
              ))}
            </div>
          </div>
        </div>
        <div className="np-foot">
          <WbButton className="btn-ghost" onClick={props.onClose}>取消</WbButton>
          <WbButton className="btn-dark" disabled={!name.trim() || props.creating}
            onClick={() => props.onCreate({ name: name.trim(), description: description.trim(), icon })}>
            {props.creating ? '创建中…' : '创建'}
          </WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
