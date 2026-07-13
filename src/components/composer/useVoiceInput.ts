// 语音输入「按住说话、松开转写」（WB-139）。浏览器 MediaRecorder 录一段音频，松开后
// POST 给本机后端 faster-whisper 转文字，回填输入框。音频不出本机（local-first）。
//
// 交互要点：
// - pointerDown 起录、pointerUp/Leave/Cancel 停录 —— 统一 pointer 事件同时覆盖鼠标与触屏。
// - getUserMedia 是异步的：若用户在拿到麦克风流之前就松手，置 stopRequested，流一就绪立刻停。
// - 依赖没装/模型没就绪 → 后端诚实 503，这里把原因 toast 出来，绝不假装转写成功（铁律#1）。
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../lib/api'
import { toast } from '../../stores/toastStore'

export type VoiceState = 'idle' | 'recording' | 'transcribing'

function pickMime(): string {
  const cands = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus']
  for (const m of cands) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(m)) return m
  }
  return ''
}

export function useVoiceInput(onText: (text: string) => void) {
  const [state, setState] = useState<VoiceState>('idle')
  // null = 还没探测；true/false = 后端 ASR 是否可用（依赖装齐）。
  const [available, setAvailable] = useState<boolean | null>(null)
  const unavailableMsg = useRef<string | null>(null)

  const recRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const stopRequested = useRef(false)
  const startingRef = useRef(false)

  // 挂载时轻探测一次能不能用——GET 不触发模型下载，只看依赖是否装齐。
  useEffect(() => {
    let alive = true
    api.asrStatus()
      .then((s) => { if (alive) { setAvailable(s.available); unavailableMsg.current = s.error } })
      .catch(() => { if (alive) { setAvailable(false); unavailableMsg.current = '后端语音服务不可达' } })
    return () => { alive = false }
  }, [])

  const cleanupStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    recRef.current = null
    chunksRef.current = []
  }, [])

  const finish = useCallback(async (blob: Blob) => {
    setState('transcribing')
    try {
      const { text } = await api.transcribeAudio(blob)
      const t = text.trim()
      if (t) onText(t)
      else toast('没听清，请再试一次')
    } catch (e) {
      toast(e instanceof Error ? e.message : '转写失败')
    } finally {
      setState('idle')
    }
  }, [onText])

  const start = useCallback(async () => {
    if (state !== 'idle' || startingRef.current) return
    if (available === false) {
      toast(unavailableMsg.current || '语音输入不可用（后端未安装 faster-whisper）')
      return
    }
    if (!navigator.mediaDevices?.getUserMedia) { toast('当前环境不支持录音'); return }

    startingRef.current = true
    stopRequested.current = false
    setState('recording')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const mime = pickMime()
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined)
      recRef.current = rec
      chunksRef.current = []
      rec.ondataavailable = (ev) => { if (ev.data.size) chunksRef.current.push(ev.data) }
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
        cleanupStream()
        if (blob.size > 0) void finish(blob)
        else setState('idle')
      }
      rec.start()
      // 用户在拿到流之前就松手了：立刻停。
      if (stopRequested.current) rec.stop()
    } catch (e) {
      cleanupStream()
      setState('idle')
      const name = (e as DOMException)?.name
      toast(name === 'NotAllowedError' ? '麦克风权限被拒绝' : '无法访问麦克风')
    } finally {
      startingRef.current = false
    }
  }, [state, available, cleanupStream, finish])

  const stop = useCallback(() => {
    // 流还没就绪（getUserMedia 未 resolve）：标记，待就绪即停。
    if (startingRef.current && !recRef.current) { stopRequested.current = true; return }
    const rec = recRef.current
    if (rec && rec.state !== 'inactive') rec.stop()
  }, [])

  // 卸载时兜底释放麦克风。
  useEffect(() => cleanupStream, [cleanupStream])

  return { state, available, start, stop }
}
