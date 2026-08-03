import { useMemo, useState } from 'react'
import type { ChatMessage } from '../../lib/types'
import { renderMarkdown } from '../../lib/markdown'
import { CatLogo } from '../../lib/icons'
import { TraceStream } from './TraceStream'
import { BotActions } from './BotActions'
import { clickable } from '../../lib/a11y'
import { WbButton } from '../ui/Primitives'

const SC_SM = (
  <svg className="sc" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M6 9l6 6 6-6" /></svg>
)

function BotMessage({ msg, streaming, onRetry }: { msg: ChatMessage; streaming: boolean; onRetry?: (messageId: string) => void }) {
  const [collapsed, setCollapsed] = useState(false)
  const running = msg.status === 'running'
  const html = useMemo(() => (msg.content ? renderMarkdown(msg.content) : ''), [msg.content])
  const hasTrace = msg.trace.length > 0

  return (
    <div className="msg bot" id={`msg-${msg.id}`}>
      <CatLogo className="bot-ic" />
      <div className="bot-body">
        <div className="bot-nm">AgentMate</div>
        <div
          className={`bot-st ${collapsed ? 'clpsd' : ''}`.trim()}
          {...(hasTrace ? clickable : {})}
          aria-expanded={hasTrace ? !collapsed : undefined}
          onClick={() => hasTrace && setCollapsed((v) => !v)}
        >
          {running ? (
            <><span className="run-ic" />执行中…</>
          ) : (
            <>已完成{msg.secs ? ` ${msg.secs}s` : ''} {hasTrace && SC_SM}</>
          )}
        </div>
        {hasTrace && !collapsed && <TraceStream trace={msg.trace} streaming={running && streaming} />}
        {!msg.content && running && !hasTrace && (
          <div className="typing"><i /><i /><i /></div>
        )}
        {html && <div dangerouslySetInnerHTML={{ __html: html }} />}
        {msg.error && <p style={{ color: '#E5484D' }}>⚠ {msg.error}</p>}
        {msg.pendingQuestion && (
          <div className="ask-card ask-recovery" role="status">
            <div className="ak-h"><span className="ak-q">上次运行在等待回答时中断</span></div>
            {msg.pendingQuestion.questions.map((question, index) => (
              <div className="ak-recovery-copy" key={`${index}-${question.q}`}>
                {index + 1}. {question.q}
                {question.options.length > 0 && <small>{question.options.join(' / ')}</small>}
              </div>
            ))}
            <div className="ak-f">原等待流已结束，不能直接提交答案；请重试本次运行。</div>
          </div>
        )}
        {onRetry && msg.runStatus && ['failed', 'cancelled', 'paused'].includes(msg.runStatus) && (
          <WbButton className="btn-ghost msg-retry" onClick={() => onRetry(msg.id)}>重试本次运行</WbButton>
        )}
        {!running && (msg.content || msg.error) && <BotActions msg={msg} />}
      </div>
    </div>
  )
}

export function MessageList({ messages, streaming, onRetry }: { messages: ChatMessage[]; streaming: boolean; onRetry?: (messageId: string) => void }) {
  return (
    <>
      {messages.map((m) =>
        m.role === 'user' ? (
          <div className="msg me" key={m.id} id={`msg-${m.id}`}>
            <div className="bub-me">{m.content}</div>
          </div>
        ) : (
          <BotMessage key={m.id} msg={m} streaming={streaming} onRetry={onRetry} />
        ),
      )}
    </>
  )
}
