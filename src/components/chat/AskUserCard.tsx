import { WbButton, WbInput } from '../ui/Primitives'
import { useState } from 'react'
import type { AskQuestion } from '../../lib/types'
import { clickable } from '../../lib/a11y'

// The ask-user card (spec 4.2): the agent's real clarifying questions. Answers
// are collected across the 1..N questions; submitting POSTs them back, which
// wakes the suspended agent on the still-open SSE stream.
export function AskUserCard({
  questions,
  onAnswer,
}: {
  questions: AskQuestion[]
  onAnswer: (answers: string[]) => void
}) {
  const total = questions.length
  const [qi, setQi] = useState(0)
  const [answers, setAnswers] = useState<string[]>(() => Array(total).fill(''))
  const [other, setOther] = useState('')

  const q = questions[qi]

  const finish = (arr: string[]) => {
    onAnswer(arr.map((a, i) => a || questions[i].options[0] || '（跳过）'))
  }

  const record = (val: string) => {
    const next = [...answers]
    next[qi] = val
    setAnswers(next)
    setOther('')
    if (qi < total - 1) setQi(qi + 1)
    else finish(next)
  }

  return (
    <div className="ask-card">
      <div className="ak-h">
        <span className="ak-q">{q.q}</span>
        <span className="ak-pg">
          <span className="ak-ar" {...(qi > 0 ? clickable : {})} aria-disabled={qi === 0} onClick={() => qi > 0 && setQi(qi - 1)}>‹</span>
          <span>{qi + 1}/{total}</span>
          <span className="ak-ar" {...(qi < total - 1 ? clickable : {})} aria-disabled={qi === total - 1} onClick={() => qi < total - 1 && setQi(qi + 1)}>›</span>
        </span>
        <span className="ak-x" {...clickable} onClick={() => finish(answers)}>×</span>
      </div>
      <div>
        {q.options.map((o, j) => (
          <div className="ak-opt" key={j} {...clickable} onClick={() => record(o)}>
            <span className="ak-n">{j + 1}</span>
            <span className="ak-t">{o}</span>
            <span className="ak-go">→</span>
          </div>
        ))}
      </div>
      <div className="ak-opt ak-other">
        <span className="ak-n">✎</span>
        <WbInput
          placeholder="其他补充..."
          value={other}
          onChange={(e) => setOther(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && other.trim()) record(other.trim())
          }}
        />
      </div>
      <div className="ak-f">
        <WbButton className="btn-ghost" style={{ height: 30, padding: '0 14px' }} onClick={() => record(q.options[0] ?? '（跳过）')}>
          跳过
        </WbButton>
      </div>
    </div>
  )
}
