import { toast } from '../../stores/toastStore'
import type { ChatMessage } from '../../lib/types'
import { clickable } from '../../lib/a11y'
import { useChatStore } from '../../stores/chatStore'
import { useIdeaStore } from '../../stores/ideaStore'

const ACTS: [string, string][] = [
  ['收为想法', 'M12 3a7 7 0 00-4 12.7V19h8v-3.3A7 7 0 0012 3zM9 22h6M9 14h6'],
  ['复制', 'M9 9h11v11H9zM5 15V5a2 2 0 012-2h10'],
  ['赞', 'M7 11v9H4v-9zM7 11l4-8a2 2 0 013 2l-1 6h5a2 2 0 012 2l-2 7H7'],
  ['踩', 'M17 13V4h3v9zM17 13l-4 8a2 2 0 01-3-2l1-6H6a2 2 0 01-2-2l2-7h11'],
  ['朗读', 'M11 5L6 9H3v6h3l5 4zM16 9a4 4 0 010 6'],
  ['分享', 'M14 5h5v5M19 5l-8 8M10 5H7a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-3'],
]

export function BotActions({ msg, simple = false }: { msg: ChatMessage; simple?: boolean }) {
  const createIdea = useIdeaStore((state) => state.createIdea)
  const copy = () => {
    navigator.clipboard?.writeText(msg.content).then(() => toast('已复制')).catch(() => toast('复制失败'))
  }
  const captureIdea = async () => {
    const chat = useChatStore.getState()
    try {
      const result = await createIdea({
        content: msg.content,
        project_id: chat.activeProjectId,
        source_type: 'message',
        source_session_id: chat.activeId,
        source_message_id: chat.activeId ? msg.id : null,
      })
      toast(result.created ? '已收进想法收集箱' : '这条消息已经收为想法')
    } catch {
      toast('保存想法失败，请检查项目权限或本地服务')
    }
  }
  const actions = simple ? ACTS.slice(0, 2) : ACTS
  return (
    <div className="bot-acts">
      {actions.map(([label, path]) => (
        <div className="a" key={label} aria-label={label} {...clickable} onClick={() => {
          if (label === '复制') copy()
          else if (label === '收为想法') void captureIdea()
          else toast(label)
        }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d={path} /></svg>
        </div>
      ))}
      {msg.usage && (
        <span className="bot-meta">
          <span className="meta-use" data-tipd="真实 token 统计">
            共消耗 ◇ {((msg.usage.prompt + msg.usage.completion) / 1000).toFixed(2)}K
          </span>
        </span>
      )}
    </div>
  )
}
