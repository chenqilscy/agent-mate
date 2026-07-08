import { useEffect, useRef, useState } from 'react'
import { AssistantChat } from '../components/channel/AssistantChat'
import { AssistantSettingsForm } from '../components/channel/AssistantSettingsForm'
import { AssistantChannels } from '../components/channel/AssistantChannels'
import { api, type Assistant } from '../lib/api'
import type { ChatMessage } from '../lib/types'
import { toast } from '../stores/toastStore'

// 助理（多助理 · 多渠道）主从视图 —— WB-088。左侧助理列表 + 新建，右侧选中助理的
// 对话 / 设置 / 渠道 三 tab。后端 /api/assistants*（WB-087）。
type Tab = 'chat' | 'settings' | 'channels'

function statusDot(a: Assistant): string {
  if (a.channels.some((c) => c.running)) return '#16B37A'
  if (a.channels.some((c) => c.enabled)) return '#E5A400'
  return '#9AA0A6'
}

export function AssistantView() {
  const [assistants, setAssistants] = useState<Assistant[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<Assistant | null>(null)
  const [tab, setTab] = useState<Tab>('chat')
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState<string | null>(null)
  const selRef = useRef<string | null>(null)
  selRef.current = selectedId

  const loadList = async (): Promise<Assistant[]> => {
    try {
      const { assistants: al } = await api.listAssistants()
      setAssistants(al)
      return al
    } catch { return [] }
  }
  const loadDetail = async (id: string) => {
    try {
      const a = await api.getAssistant(id)
      if (selRef.current === id) setDetail(a)
    } catch { /* ignore */ }
  }
  const select = (id: string) => { setSelectedId(id); setDetail(null); setTab('chat'); loadDetail(id) }

  useEffect(() => {
    loadList().then((al) => { if (al.length && !selRef.current) select(al[0].id) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 轮询：列表状态点 + 选中助理的 transcript（Telegram 侧消息带外到达）。发送中暂停。
  useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState !== 'visible' || sending) return
      loadList()
      if (selRef.current && tab === 'chat') loadDetail(selRef.current)
    }, 4000)
    return () => clearInterval(t)
  }, [sending, tab])

  const onCreate = async () => {
    try {
      const a = await api.createAssistant({ name: '新助理', avatar: '🤖' })
      await loadList()
      select(a.id)
      setTab('settings')
      toast('已创建助理，去「设置」完善它')
    } catch { toast('创建失败') }
  }

  const onDelete = async () => {
    if (!detail) return
    try {
      await api.deleteAssistant(detail.id)
      const al = await loadList()
      setSelectedId(null); setDetail(null)
      if (al.length) select(al[0].id)
      toast('已删除助理')
    } catch { toast('删除失败') }
  }

  const onSend = async (text: string) => {
    if (!selectedId || sending) return
    setPending(text); setSending(true)
    try {
      await api.assistantSay(selectedId, text)
      await loadDetail(selectedId)
    } catch { toast('发送失败，请重试') }
    finally { setSending(false); setPending(null) }
  }

  const onSavedDetail = (a: Assistant) => { setDetail(a); loadList() }

  // transcript → ChatMessage[]（+ 发送中的乐观占位）
  const base: ChatMessage[] = (detail?.messages ?? []).map((m) => ({
    id: m.id, role: m.role, content: m.content, trace: [], status: 'done' as const,
  }))
  const display: ChatMessage[] = sending && pending != null
    ? [...base,
       { id: '_pending_u', role: 'user', content: pending, trace: [], status: 'done' as const },
       { id: '_pending_b', role: 'assistant', content: '', trace: [], status: 'running' as const }]
    : base

  return (
    <section className="view active" data-view="assistant">
      <div className="asst">
        <div className="asst-rail">
          <div className="asst-rail-h">
            <b>助理</b>
            <button className="asst-new" onClick={onCreate}>＋ 新建</button>
          </div>
          <div className="asst-list">
            {assistants.length === 0 && <div className="asst-empty" style={{ padding: '14px 10px' }}>还没有助理</div>}
            {assistants.map((a) => (
              <div key={a.id} className={`asst-item ${a.id === selectedId ? 'on' : ''}`.trim()} onClick={() => select(a.id)}>
                <span className="asst-av">{a.avatar || '🤖'}</span>
                <span className="asst-nm">{a.name}</span>
                <span className="asst-dot" style={{ background: statusDot(a) }} title={a.channels.length ? '' : '未配渠道'} />
              </div>
            ))}
          </div>
        </div>

        <div className="asst-main">
          {!detail ? (
            <div className="ov-center" style={{ paddingTop: 140 }}>
              <span style={{ fontSize: 34 }}>🤖</span>
              {assistants.length === 0 ? '还没有助理' : '选择一个助理'}
              <small>{assistants.length === 0 ? '点左上「＋ 新建」创建你的第一个助理' : '在左侧选择，或新建一个'}</small>
            </div>
          ) : (
            <>
              <div className="asst-tabs">
                <div className={`asst-tab ${tab === 'chat' ? 'on' : ''}`.trim()} onClick={() => setTab('chat')}>对话</div>
                <div className={`asst-tab ${tab === 'settings' ? 'on' : ''}`.trim()} onClick={() => setTab('settings')}>设置</div>
                <div className={`asst-tab ${tab === 'channels' ? 'on' : ''}`.trim()} onClick={() => setTab('channels')}>渠道</div>
                <div style={{ flex: 1 }} />
                <button className="asst-del" onClick={onDelete} title="删除助理">删除</button>
              </div>
              {tab === 'chat' ? (
                <AssistantChat
                  title={detail.name}
                  messages={display}
                  sending={sending}
                  onSend={onSend}
                  emptyHint={detail.channels.some((c) => c.type === 'telegram' && c.has_token)
                    ? '在下面对话，或在 Telegram 给这个助理的 bot 发消息。'
                    : '在下面直接对话，或去「渠道」接入 Telegram。'}
                />
              ) : (
                <div className="asst-pane">
                  {tab === 'settings'
                    ? <AssistantSettingsForm assistant={detail} onSaved={onSavedDetail} />
                    : <AssistantChannels assistant={detail} onChanged={() => loadDetail(detail.id)} />}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  )
}
