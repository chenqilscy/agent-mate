// SSE-over-POST reader.
//
// /api/chat is a POST that returns text/event-stream, so the browser's
// EventSource (GET-only) can't consume it. We read the fetch body stream and
// parse `event:`/`data:` frames ourselves, dispatching typed events. An
// AbortController lets the Composer's stop button cancel the request client-side
// (the /stop endpoint stops it server-side too).

import { API_BASE } from './api'
import type { SSEEvent } from './types'

export interface ChatStreamOptions {
  text: string
  sessionId?: string
  title?: string
  space?: string
  model?: string
  plan?: boolean
  ask?: boolean
  projectId?: string
  experts?: string[]
  skills?: string[]
  connectors?: string[]
  refs?: { name: string; content: string }[]
  signal?: AbortSignal
  onEvent: (ev: SSEEvent) => void
}

export async function streamChat(opts: ChatStreamOptions): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined

  // The whole request lives in the try: a failed fetch (backend down / network
  // error) must surface as error+done to the caller, not reject out of streamChat
  // and become an unhandled rejection with the bot bubble stuck 'running' (WB-001).
  try {
    const resp = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: opts.text,
        session_id: opts.sessionId,
        title: opts.title,
        space: opts.space,
        model: opts.model,
        plan: opts.plan,
        ask: opts.ask,
        project_id: opts.projectId,
        experts: opts.experts,
        skills: opts.skills,
        connectors: opts.connectors,
        refs: opts.refs,
      }),
      signal: opts.signal,
    })

    if (!resp.ok || !resp.body) {
      const detail = await resp.text().catch(() => '')
      opts.onEvent({ type: 'error', data: { message: `HTTP ${resp.status} ${detail}` } })
      opts.onEvent({ type: 'done', data: {} })
      return
    }

    reader = resp.body.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE frames are separated by a blank line.
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        dispatchFrame(frame, opts.onEvent)
      }
    }

    // Stream closed cleanly. Flush any trailing multibyte bytes, then dispatch a
    // final frame the server didn't terminate with a blank line (WB-020) — else a
    // last `done` frame is dropped and the bubble stays 'running'.
    buffer += decoder.decode()
    if (buffer.trim()) dispatchFrame(buffer, opts.onEvent)
  } catch (e) {
    // AbortError is an expected outcome of the stop button — the caller's stop()
    // already finalised the bubble, so stay silent (and keep one-shot refs).
    if ((e as Error).name !== 'AbortError') {
      opts.onEvent({ type: 'error', data: { message: String(e) } })
      opts.onEvent({ type: 'done', data: {} })
    }
  } finally {
    reader?.releaseLock?.()
  }
}

function dispatchFrame(frame: string, onEvent: (ev: SSEEvent) => void): void {
  let event = 'message'
  const dataLines: string[] = []
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return
  let data: unknown
  try {
    data = JSON.parse(dataLines.join('\n'))
  } catch {
    return
  }
  onEvent({ type: event, data } as SSEEvent)
}
