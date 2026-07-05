// Conversation export (分享对话). Serialises the active chat to Markdown and
// hands it to the user via clipboard or a .md download — pure client-side, no
// backend. The trace (think/steps) is omitted so the export reads as clean prose.
import type { ChatMessage } from './types'

export function conversationToMarkdown(title: string, messages: ChatMessage[]): string {
  const out: string[] = [`# ${title || '对话'}`, '']
  for (const m of messages) {
    const body = m.content.trim()
    if (m.role === 'user') {
      if (body) out.push('## 🧑 我', '', body, '')
    } else {
      if (!body && !m.error) continue
      out.push('## 🐝 WorkBuddy', '')
      if (body) out.push(body, '')
      if (m.error) out.push(`> ⚠ ${m.error}`, '')
    }
  }
  out.push('---', '', '_由 WorkBuddy 导出_')
  return out.join('\n')
}

export function safeFilename(title: string): string {
  const base = (title || '对话').replace(/[\\/:*?"<>|]+/g, '_').trim().slice(0, 40) || '对话'
  return `${base}.md`
}

export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
