import { useEffect, useMemo, useState } from 'react'
import { Empty, Input, Select, Tag } from 'antd'
import type { Idea, IdeaDetail, IdeaRelationType, IdeaSettlementType, ProjectInfo } from '../../lib/types'
import { api } from '../../lib/api'
import { clickable } from '../../lib/a11y'
import { useIdeaStore } from '../../stores/ideaStore'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { WbButton, WbTextArea } from '../ui/Primitives'

const RELATION_LABEL: Record<IdeaRelationType, string> = {
  related: '相关', derived: '派生自', duplicate: '重复',
}
const SETTLEMENT_LABEL: Record<IdeaSettlementType, string> = {
  work_item: '项目任务', decision: '项目决策', memory: '项目知识',
}

function excerpt(idea: Idea): string {
  const value = (idea.processed_content || idea.content).replace(/\s+/g, ' ').trim()
  return value.length > 88 ? `${value.slice(0, 88)}…` : value
}

function relativeTime(timestamp: number): string {
  const seconds = Math.max(0, Date.now() / 1000 - timestamp)
  if (seconds < 60) return '刚刚'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}小时前`
  return `${Math.floor(seconds / 86400)}天前`
}

function matchesIdea(idea: Idea, query: string): boolean {
  const needle = query.trim().toLocaleLowerCase()
  if (!needle) return true
  return [idea.title, idea.content, idea.processed_content, ...idea.tags]
    .some((value) => value.toLocaleLowerCase().includes(needle))
}

function IdeaRows({ ideas, onOpen, empty }: {
  ideas: Idea[]; onOpen: (idea: Idea) => void; empty: string
}) {
  if (!ideas.length) return <Empty className="idea-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description={empty} />
  return <div className="idea-rows">
    {ideas.map((idea) => (
      <div className="idea-row" key={idea.id} {...clickable} onClick={() => onOpen(idea)}>
        <span className="idea-bulb">💡</span>
        <span className="idea-row-main">
          <b>{idea.title}</b>
          <small>{excerpt(idea)}</small>
        </span>
        <span className="idea-row-meta">
          {idea.status === 'settled' ? '已沉淀' : idea.project_id ? '项目中' : '待归属'} · {relativeTime(idea.updated_at)}
        </span>
      </div>
    ))}
  </div>
}

function projectOptions(projects: ProjectInfo[]) {
  return [
    { value: '', label: '待归属（个人收集箱）' },
    ...projects.map((project) => ({
      value: project.id,
      label: project.name,
      disabled: project.role === 'Viewer',
    })),
  ]
}

function IdeaDetailModal({ initial, projects, onClose }: {
  initial: Idea; projects: ProjectInfo[]; onClose: () => void
}) {
  const ideas = useIdeaStore((state) => state.ideas)
  const getDetail = useIdeaStore((state) => state.getDetail)
  const updateIdea = useIdeaStore((state) => state.updateIdea)
  const addRelation = useIdeaStore((state) => state.addRelation)
  const removeRelation = useIdeaStore((state) => state.removeRelation)
  const applyProcessing = useIdeaStore((state) => state.applyProcessing)
  const settle = useIdeaStore((state) => state.settle)
  const [idea, setIdea] = useState<IdeaDetail | null>(null)
  const [title, setTitle] = useState(initial.title)
  const [content, setContent] = useState(initial.content)
  const [tags, setTags] = useState(initial.tags.join('，'))
  const [projectId, setProjectId] = useState(initial.project_id || '')
  const [relation, setRelation] = useState<IdeaRelationType>('related')
  const [targetId, setTargetId] = useState('')
  const [confirmKind, setConfirmKind] = useState<IdeaSettlementType | null>(null)
  const [memoryPreview, setMemoryPreview] = useState<Awaited<ReturnType<typeof api.ideaMemoryPreview>> | null>(null)
  const [busy, setBusy] = useState(false)

  const refresh = async () => {
    const detail = await getDetail(initial.id)
    setIdea(detail)
    setTitle(detail.title)
    setContent(detail.content)
    setTags(detail.tags.join('，'))
    setProjectId(detail.project_id || '')
  }
  useEffect(() => { void refresh().catch(() => onClose()) }, [initial.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const canMutate = !!idea?.can_write && idea.status !== 'settled'
  const writable = canMutate && idea.status !== 'archived'
  const candidates = useMemo(() => ideas.filter((item) => (
    item.id !== initial.id && item.project_id === (projectId || null) && item.status !== 'archived'
  )), [ideas, initial.id, projectId])

  const save = async () => {
    if (!title.trim() || !content.trim()) { toast('标题和内容不能为空'); return null }
    setBusy(true)
    try {
      const updated = await updateIdea(initial.id, {
        title: title.trim(), content: content.trim(), project_id: projectId || null,
        tags: tags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean),
      })
      setIdea(updated)
      toast('想法已保存')
      return updated
    } catch {
      toast('保存失败，请检查项目权限')
      return null
    } finally { setBusy(false) }
  }

  const openSession = async (sessionId: string) => {
    await useChatStore.getState().openSession(sessionId)
    useUIStore.getState().setView(idea?.project_id ? 'projexec' : 'chat', {
      projectId: idea?.project_id ?? undefined, sessionId,
    })
    onClose()
  }

  const processWithAgent = async () => {
    const saved = await save()
    if (!saved?.project_id) { toast('请先把想法归入项目'); return }
    const prompt = [
      '请整理下面这条项目想法。只输出建议稿，不要创建任务、修改项目或写入长期记忆。',
      '请按“一句话总结、背景与问题、关键假设、可选方案、风险与待确认问题、建议下一步”组织。',
      `\n标题：${saved.title}\n原始想法：\n${saved.content}`,
    ].join('\n')
    const chat = useChatStore.getState()
    chat.startProject(saved.project_id, `整理想法：${saved.title}`.slice(0, 26))
    useUIStore.getState().setView('projexec', { projectId: saved.project_id })
    onClose()
    toast('已创建真实 Agent 加工会话')
    void chat.send(prompt).then(async (sessionId) => {
      if (sessionId) await useIdeaStore.getState().updateIdea(saved.id, { processing_session_id: sessionId })
    }).catch(() => {})
  }

  const applyAgentResult = async () => {
    setBusy(true)
    try {
      const updated = await applyProcessing(initial.id)
      setIdea(updated)
      toast('已应用加工会话的最后一条完整回复')
    } catch { toast('加工会话还没有可应用的完整回复') }
    finally { setBusy(false) }
  }

  const beginSettle = async (kind: IdeaSettlementType) => {
    const saved = await save()
    if (!saved?.project_id) { toast('请先把想法归入项目'); return }
    setMemoryPreview(null)
    setConfirmKind(kind)
    if (kind === 'memory') {
      try { setMemoryPreview(await api.ideaMemoryPreview(initial.id)) }
      catch { toast('项目知识预览失败'); setConfirmKind(null) }
    }
  }

  const confirmSettle = async () => {
    if (!confirmKind) return
    if (confirmKind === 'memory' && (!memoryPreview || memoryPreview.would_exceed)) {
      toast('项目知识超过长度上限，不能写入')
      return
    }
    setBusy(true)
    try {
      const updated = await settle(initial.id, confirmKind, memoryPreview?.base_sha256)
      setIdea(updated)
      setConfirmKind(null)
      toast(`已沉淀为${SETTLEMENT_LABEL[updated.settled_type as IdeaSettlementType]}`)
    } catch { toast(confirmKind === 'memory' ? '项目知识已变化，请重新预览' : '沉淀失败，请检查项目或 Server 状态') }
    finally { setBusy(false) }
  }

  const addLink = async () => {
    if (!targetId) return
    setBusy(true)
    try {
      const saved = await updateIdea(initial.id, {
        title: title.trim(), content: content.trim(), project_id: projectId || null,
        tags: tags.split(/[，,]/).map((tag) => tag.trim()).filter(Boolean),
      })
      setIdea(saved)
      setIdea(await addRelation(initial.id, targetId, relation))
      setTargetId('')
      toast('关联已保存')
    } catch { toast('关联失败，只能关联同一项目中的想法') }
    finally { setBusy(false) }
  }

  if (!idea) return null
  return <AntModalBridge onClose={onClose}>
    <div className="np-modal idea-modal" role="dialog" aria-modal="true" aria-label="想法详情">
      <div className="np-h">
        <div>想法详情 <Tag>{idea.status === 'settled' ? '已沉淀' : idea.status === 'archived' ? '已归档' : idea.project_id ? '项目中' : '待归属'}</Tag></div>
        <WbButton className="np-x" aria-label="关闭" onClick={onClose}>×</WbButton>
      </div>
      <div className="np-body idea-body">
        <label className="np-lbl">标题</label>
        <Input value={title} disabled={!writable} maxLength={200} onChange={(event) => setTitle(event.target.value)} />
        <label className="np-lbl">原始想法</label>
        <WbTextArea value={content} disabled={!writable} maxLength={20_000} autoSize={{ minRows: 4, maxRows: 10 }} onChange={(event) => setContent(event.target.value)} />
        <div className="idea-form-grid">
          <div><label className="np-lbl">所属项目</label><Select value={projectId} disabled={!writable} options={projectOptions(projects)} onChange={setProjectId} /></div>
          <div><label className="np-lbl">标签</label><Input value={tags} disabled={!writable} placeholder="多个标签用逗号分隔" onChange={(event) => setTags(event.target.value)} /></div>
        </div>

        {(idea.source_session_id || idea.processing_session_id) && <div className="idea-trace">
          <b>来源与加工</b>
          {idea.source_session_id && <WbButton className="btn-ghost" onClick={() => void openSession(idea.source_session_id!)}>打开来源会话</WbButton>}
          {idea.processing_session_id && <WbButton className="btn-ghost" onClick={() => void openSession(idea.processing_session_id!)}>打开加工会话</WbButton>}
          {idea.processing_session_id && writable && <WbButton className="btn-ghost" disabled={busy} onClick={() => void applyAgentResult()}>应用最后回复</WbButton>}
        </div>}
        {idea.processed_content && <><label className="np-lbl">已确认的加工结果</label><div className="idea-processed">{idea.processed_content}</div></>}

        <div className="idea-rel-head"><b>关联想法</b><span>只在同一项目或同一待归属收集箱内关联</span></div>
        {idea.relations.length > 0 && <div className="idea-relations">{idea.relations.map((item) => <div key={`${item.source_idea_id}-${item.target_idea_id}-${item.relation}`}>
          <Tag>{RELATION_LABEL[item.relation]}</Tag><span>{item.related.title}</span>
          {writable && <WbButton className="idea-unlink" aria-label="移除关联" onClick={() => void removeRelation(initial.id, item.related.id, item.relation).then(setIdea)}>×</WbButton>}
        </div>)}</div>}
        {writable && <div className="idea-rel-add">
          <Select value={relation} onChange={setRelation} options={Object.entries(RELATION_LABEL).map(([value, label]) => ({ value, label }))} />
          <Select value={targetId || undefined} showSearch optionFilterProp="label" placeholder="选择关联想法" onChange={setTargetId} options={candidates.map((item) => ({ value: item.id, label: item.title }))} />
          <WbButton className="btn-ghost" disabled={!targetId || busy} onClick={() => void addLink()}>关联</WbButton>
        </div>}

        {confirmKind && <div className="idea-confirm">
          <b>确认沉淀为{SETTLEMENT_LABEL[confirmKind]}</b>
          <p>{confirmKind === 'memory' ? '以下内容将追加到本机项目 MEMORY.md；想法原文不会自动上云。' : '将使用当前确认内容创建真实项目记录，并保留反向追溯标识。'}</p>
          {confirmKind === 'memory' && memoryPreview && <WbTextArea readOnly value={memoryPreview.proposed} autoSize={{ minRows: 5, maxRows: 10 }} />}
          <div><WbButton className="btn-ghost" onClick={() => setConfirmKind(null)}>取消</WbButton><WbButton className="btn-dark" disabled={busy || (memoryPreview?.would_exceed ?? false)} onClick={() => void confirmSettle()}>确认写入</WbButton></div>
        </div>}
      </div>
      <div className="np-foot idea-foot">
        {writable && <WbButton className="btn-ghost" disabled={busy} onClick={() => void save()}>保存</WbButton>}
        {writable && projectId && <WbButton className="btn-ghost" disabled={busy} onClick={() => void processWithAgent()}>交给 Agent 整理</WbButton>}
        {writable && projectId && <>
          <WbButton className="btn-ghost" disabled={busy} onClick={() => void beginSettle('work_item')}>转为任务</WbButton>
          <WbButton className="btn-ghost" disabled={busy} onClick={() => void beginSettle('decision')}>记录决策</WbButton>
          <WbButton className="btn-dark" disabled={busy} onClick={() => void beginSettle('memory')}>写入项目知识</WbButton>
        </>}
        {canMutate && <WbButton className="idea-archive" disabled={busy} onClick={() => void updateIdea(initial.id, { status: idea.status === 'archived' ? (idea.project_id ? 'active' : 'inbox') : 'archived' }).then(setIdea)}>{idea.status === 'archived' ? '恢复' : '归档'}</WbButton>}
        {idea.status === 'settled' && <span className="idea-settled">已沉淀为{SETTLEMENT_LABEL[idea.settled_type as IdeaSettlementType]}</span>}
      </div>
    </div>
  </AntModalBridge>
}

export function HomeIdeaInbox({ projects }: { projects: ProjectInfo[] }) {
  const ideas = useIdeaStore((state) => state.ideas)
  const loaded = useIdeaStore((state) => state.loaded)
  const load = useIdeaStore((state) => state.load)
  const createIdea = useIdeaStore((state) => state.createIdea)
  const [text, setText] = useState('')
  const [projectId, setProjectId] = useState('')
  const [selected, setSelected] = useState<Idea | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  useEffect(() => { if (!loaded) void load().catch(() => {}) }, [loaded, load])
  const activeIdeas = ideas.filter((idea) => idea.status !== 'archived')
  const visible = activeIdeas.filter((idea) => matchesIdea(idea, query)).slice(0, expanded ? undefined : 5)
  const capture = async () => {
    if (!text.trim()) return
    try {
      const result = await createIdea({ content: text.trim(), project_id: projectId || null })
      setText('')
      toast(result.idea.project_id ? '已记录到项目想法' : '已记录到待归属收集箱')
    } catch { toast('记录失败，请检查项目权限或本地服务') }
  }
  return <>
    <div className="idea-home">
      <div className="idea-card-head"><div><b>想法收集箱</b><span>先记下来，再交给 Agent 整理或转成项目行动</span></div><div className="idea-head-actions"><Tag>{ideas.filter((idea) => idea.status === 'inbox').length} 条待归属</Tag><WbButton className="btn-ghost" onClick={() => { setExpanded(!expanded); if (expanded) setQuery('') }}>{expanded ? '收起' : '查看全部'}</WbButton></div></div>
      <div className="idea-capture">
        <Input value={text} maxLength={20_000} placeholder="快速记录一个零散想法…" onChange={(event) => setText(event.target.value)} onPressEnter={() => void capture()} />
        <Select value={projectId} options={projectOptions(projects)} onChange={setProjectId} />
        <WbButton className="btn-dark" disabled={!text.trim()} onClick={() => void capture()}>记录</WbButton>
      </div>
      {expanded && <Input className="idea-search" allowClear value={query} placeholder="搜索标题、正文、加工结果或标签" onChange={(event) => setQuery(event.target.value)} />}
      <IdeaRows ideas={visible} onOpen={setSelected} empty={query ? '没有匹配的想法。' : '还没有想法。记录后可稍后归入项目。'} />
    </div>
    {selected && <IdeaDetailModal initial={selected} projects={projects} onClose={() => setSelected(null)} />}
  </>
}

export function ProjectIdeaPanel({ project, projects, canWrite }: {
  project: ProjectInfo; projects: ProjectInfo[]; canWrite: boolean
}) {
  const ideas = useIdeaStore((state) => state.ideas)
  const loaded = useIdeaStore((state) => state.loaded)
  const load = useIdeaStore((state) => state.load)
  const createIdea = useIdeaStore((state) => state.createIdea)
  const [text, setText] = useState('')
  const [selected, setSelected] = useState<Idea | null>(null)
  const [expanded, setExpanded] = useState(false)
  const [query, setQuery] = useState('')
  useEffect(() => { if (!loaded) void load().catch(() => {}) }, [loaded, load])
  const projectIdeas = ideas.filter((idea) => idea.project_id === project.id && idea.status !== 'archived')
  const visible = projectIdeas.filter((idea) => matchesIdea(idea, query)).slice(0, expanded ? undefined : 4)
  const capture = async () => {
    if (!text.trim() || !canWrite) return
    try {
      await createIdea({ content: text.trim(), project_id: project.id })
      setText('')
      toast('已记录到项目想法')
    } catch { toast('记录失败，请检查项目权限') }
  }
  return <>
    <div className="idea-project-card">
      <div className="idea-card-head"><div><b>项目想法</b><span>任务形成前的轻量缓冲层，正文仅保存在本机</span></div><div className="idea-head-actions"><Tag>{projectIdeas.length}</Tag><WbButton className="btn-ghost" onClick={() => { setExpanded(!expanded); if (expanded) setQuery('') }}>{expanded ? '收起' : '查看全部'}</WbButton></div></div>
      {canWrite && <div className="idea-capture compact"><Input value={text} placeholder="记录一个项目想法…" onChange={(event) => setText(event.target.value)} onPressEnter={() => void capture()} /><WbButton className="btn-dark" disabled={!text.trim()} onClick={() => void capture()}>记录</WbButton></div>}
      {expanded && <Input className="idea-search" allowClear value={query} placeholder="搜索当前项目的想法" onChange={(event) => setQuery(event.target.value)} />}
      <IdeaRows ideas={visible} onOpen={setSelected} empty={query ? '没有匹配的项目想法。' : '还没有项目想法。可先记录，确认后再转成任务或决策。'} />
    </div>
    {selected && <IdeaDetailModal initial={selected} projects={projects} onClose={() => setSelected(null)} />}
  </>
}
