import { useEffect, useMemo, useState } from 'react'
import { Input, Tag } from 'antd'
import { api } from '../../lib/api'
import { streamOrchestration } from '../../lib/sse'
import type { Orchestration } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { WbButton } from '../ui/Primitives'

const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const STATUS: Record<string, string> = {
  planning: '规划中', running: '专家执行中', reviewing: '主编审稿中', completed: '已完成',
  failed: '执行失败', cancelled: '已取消', pending: '等待依赖', skipped: '依赖失败，已跳过',
}

function freshKey() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function TeamOrchestrationPanel({ teamName, suggestedGoal }: { teamName: string; suggestedGoal?: string }) {
  const [goal, setGoal] = useState(suggestedGoal || '')
  const [item, setItem] = useState<Orchestration | null>(null)
  const [busy, setBusy] = useState(false)
  const active = item && !TERMINAL.has(item.status)

  useEffect(() => {
    if (!active || !item) return
    let alive = true
    let retryTimer: number | undefined
    let controller = new AbortController()
    let warned = false
    const connect = async () => {
      try {
        await streamOrchestration(item.id, {
          signal: controller.signal,
          onSnapshot: (snapshot) => { if (alive) setItem(snapshot) },
        })
        warned = false
      } catch (error) {
        if (!alive || (error as Error).name === 'AbortError') return
        if (!warned) {
          toast('专家团状态流已断开，正在自动重连')
          warned = true
        }
        retryTimer = window.setTimeout(() => {
          controller = new AbortController()
          void connect()
        }, 1500)
      }
    }
    void connect()
    return () => {
      alive = false
      controller.abort()
      if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    }
  }, [active, item?.id])

  const finalOutput = useMemo(
    () => item?.nodes.find((node) => node.node_key === 'reviewer')?.output || '',
    [item],
  )
  const tokens = (item?.prompt_tokens || 0) + (item?.completion_tokens || 0)

  const start = async () => {
    const trimmed = goal.trim()
    if (!trimmed) { toast('请先填写专家团目标'); return }
    setBusy(true)
    try {
      const result = await api.createOrchestration({
        team_name: teamName, goal: trimmed, idempotency_key: freshKey(),
        max_nodes: 7, max_parallel: 3, max_total_tokens: 24000,
      })
      setItem(result.orchestration)
      toast(`已启动 · ${teamName}`)
    } catch {
      toast('启动失败，请确认默认模型与团队配置')
    } finally { setBusy(false) }
  }

  const cancel = async () => {
    if (!item) return
    setBusy(true)
    try {
      const result = await api.cancelOrchestration(item.id)
      setItem(result.orchestration)
      toast(result.cancelled ? '已取消专家团执行' : '专家团执行已结束')
    } catch { toast('取消失败，执行可能已结束') } finally { setBusy(false) }
  }

  return (
    <div>
      <div className="sec-title" style={{ margin: '18px 0 8px' }}>专家团协作执行</div>
      {!item && (
        <>
          <Input.TextArea
            value={goal} onChange={(event) => setGoal(event.target.value)} rows={4}
            maxLength={50000} showCount placeholder="描述目标、已知事实、约束和期望交付…"
            aria-label="专家团执行目标"
          />
          <WbButton className="btn-dark" style={{ width: '100%', justifyContent: 'center', marginTop: 10 }} disabled={busy} onClick={() => void start()}>
            {busy ? '正在启动…' : '启动真实专家 DAG'}
          </WbButton>
        </>
      )}
      {item && (
        <div aria-live="polite">
          <div className="pkc-row" style={{ cursor: 'default' }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="pn">{STATUS[item.status] || item.status}</div>
              <div className="pd">{tokens.toLocaleString()} tokens · {item.nodes.length} 个节点</div>
            </div>
            <Tag className="ec-tag">{item.status}</Tag>
          </div>
          {item.nodes.map((node) => (
            <div className="pkc-row" key={node.id} style={{ cursor: 'default', alignItems: 'flex-start' }}>
              <span className="pi">{node.status === 'completed' ? '✓' : node.status === 'failed' ? '!' : '·'}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="pn">{node.title} · {node.role}</div>
                <div className="pd">
                  {STATUS[node.status] || node.status} · {node.prompt_tokens + node.completion_tokens} tokens
                  {node.attempts.length > 1 ? ` · ${node.attempts.length} 次尝试` : ''}
                </div>
                {node.error && <div className="pd" style={{ color: 'var(--color-error)' }}>{node.error}</div>}
              </div>
            </div>
          ))}
          {finalOutput && (
            <div className="ec-d" style={{ marginTop: 10, maxHeight: 260, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
              {finalOutput}
            </div>
          )}
          {item.artifact && <div className="pd" style={{ marginTop: 8 }}>交付产物：{item.artifact.name}</div>}
          {item.error && <div className="pd" style={{ marginTop: 8, color: 'var(--color-error)' }}>失败原因：{item.error}</div>}
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            {active && <WbButton className="btn-ghost" disabled={busy} onClick={() => void cancel()}>取消执行</WbButton>}
            {TERMINAL.has(item.status) && <WbButton className="btn-ghost" onClick={() => setItem(null)}>发起新任务</WbButton>}
          </div>
        </div>
      )}
    </div>
  )
}
