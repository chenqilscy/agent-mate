import { WbButton } from '../ui/Primitives'
import { useEffect, useRef, useState } from 'react'
import { type ConnMeta } from '../../data/catalog'
import { useCatalog } from '../../stores/catalogStore'
import { api } from '../../lib/api'
import { useLoadoutStore } from '../../stores/loadoutStore'
import { useChatStore } from '../../stores/chatStore'
import { useUIStore } from '../../stores/uiStore'
import { toast } from '../../stores/toastStore'
import { WeKnoraConfigForm } from './WeKnoraConfigForm'
import { AntModalBridge } from '../ui/AntModalBridge'
import { Tag } from 'antd'

// 连接器详情弹窗（套现有 .np-overlay/.np-modal 骨架，天然继承暗色覆盖）。
// OAuth 连接器（如金山文档）走真实授权流：点「连接」→ 后端 spawn `kdocs-cli auth login`
// → 跳转 WPS 授权页 → 成功后 Token 存本机密钥链；前端轮询状态直到已连接，再展示去试试/添加。
// 表单型连接器（meta.configKind，如 WeKnora · WB-188）：「启用方式」渲染成真配置表单，
// 填完存后端 DB（不用改 .env），徽标按真实连接态实时切换。
// 其余非 OAuth 连接器沿用「添加到本会话 / 去试试」展示型交互。

// 把连接器作为新会话的唯一能力班底，可选携一个试用 prompt 直接发起。
function engage(name: string, prompt?: string) {
  useLoadoutStore.getState().summonConnectors([name])
  const chat = useChatStore.getState()
  if (prompt) {
    chat.startDraft(prompt.length > 26 ? prompt.slice(0, 26) + '…' : prompt)
    useUIStore.getState().setView('chat')
    void chat.send(prompt)
    toast('已接入 · ' + name)
  } else {
    chat.startDraft('对话')
    useUIStore.getState().setView('home')
    toast('已接入 ' + name + ' · 可直接对它下达指令')
  }
}

type ConnState = 'unknown' | 'not_installed' | 'disconnected' | 'connecting' | 'connected'

export function ConnectorDetailModal(
  { icon, name, desc, onClose }: { icon: string; name: string; desc: string; onClose: () => void },
) {
  const [showTools, setShowTools] = useState(false)
  const added = useLoadoutStore((s) => s.connectors.includes(name))
  const { CONN_META } = useCatalog()
  const meta: ConnMeta | undefined = CONN_META[name]
  const intro = meta?.fullDesc || desc
  const isOAuth = !!meta?.oauth
  // 表单型连接器（WB-188）：配置表单自己上报真实连接态，驱动徽标与「试试这样问我」。
  const isForm = !!meta?.configKind
  const [formOk, setFormOk] = useState(false)

  // OAuth 连接状态（仅 oauth 连接器用）。
  const [conn, setConn] = useState<ConnState>(isOAuth ? 'unknown' : 'connected')
  const [authUrl, setAuthUrl] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)
  const aliveRef = useRef(true)

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }

  const refreshStatus = async () => {
    try {
      const s = await api.kdocsStatus()
      if (!aliveRef.current) return
      if (!s.installed) setConn('not_installed')
      else setConn(s.authenticated ? 'connected' : 'disconnected')
      return s
    } catch {
      if (aliveRef.current) setConn('disconnected')
    }
  }

  useEffect(() => {
    aliveRef.current = true
    if (isOAuth) void refreshStatus()
    return () => { aliveRef.current = false; stopPoll() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name])

  const doConnect = async () => {
    setConn('connecting')
    try {
      const r = await api.kdocsConnect()
      if (!aliveRef.current) return
      if (r.status === 'connected') { setConn('connected'); toast('已连接 · ' + name); return }
      if (r.authUrl) {
        setAuthUrl(r.authUrl)
        window.open(r.authUrl, '_blank', 'noopener,noreferrer')
      }
      toast('已打开授权页，请在浏览器完成 WPS 授权…')
      // 轮询直到授权完成（最多约 5 分钟）。
      let tries = 0
      stopPoll()
      pollRef.current = window.setInterval(async () => {
        tries += 1
        const s = await api.kdocsStatus().catch(() => null)
        if (!aliveRef.current) { stopPoll(); return }
        if (s?.authenticated) { stopPoll(); setConn('connected'); toast('已连接 · ' + name) }
        else if (tries >= 150) { stopPoll(); setConn('disconnected'); toast('授权超时，请重试') }
      }, 2000)
    } catch {
      if (aliveRef.current) { setConn('disconnected'); toast('连接失败，请重试') }
    }
  }

  const doDisconnect = async () => {
    try { await api.kdocsDisconnect() } catch { /* 忽略，下面刷新真实状态 */ }
    stopPoll()
    await refreshStatus()
    toast('已断开 · ' + name)
  }

  const doTry = () => { engage(name); onClose() }
  const doPrompt = (p: string) => { engage(name, p); onClose() }
  const toggleAdd = () => {
    if (added) {
      useLoadoutStore.getState().toggle('conn', name)
      toast('已移除 · ' + name)
      return
    }
    engage(name)
    onClose()
  }

  // 头部状态标签：oauth 连接器显示实时连接态；其它连接器显示静态 statusLabel。
  const statusTag = isOAuth
    ? conn === 'connected'
      ? <Tag className="conn-tag rdy">● 已连接</Tag>
      : conn === 'not_installed'
        ? <Tag className="conn-tag tok">未安装 CLI</Tag>
        : <Tag className="conn-tag tok">{conn === 'connecting' ? '连接中…' : '需连接'}</Tag>
    : isForm
      ? (formOk
          ? <Tag className="conn-tag rdy">● 已连接</Tag>
          : <Tag className="conn-tag tok">{meta?.statusLabel ?? '需连接'}</Tag>)
      : meta
        ? <span className={`conn-tag ${meta.status}`}>{meta.statusLabel}</span>
        : null

  return (
    <AntModalBridge onClose={onClose}>
      <div className="np-modal" style={{ width: 480 }} role="dialog" aria-modal="true" aria-label={name}>
        <div className="np-h">
          <div className="ec-av" style={{ width: 50, height: 50, fontSize: 26 }}>{icon}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 18, fontWeight: 800, display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
              {name}{statusTag}
            </div>
            <div className="ec-tags" style={{ marginTop: 6 }}>
              <span className="ec-tag">连接器</span>
              {added && <span className="ec-tag">本会话已接入</span>}
            </div>
          </div>
          <WbButton type="button" className="np-x" onClick={onClose}>×</WbButton>
        </div>

        <div className="np-body">
          <div className="sec-title" style={{ margin: '10px 0 8px' }}>能力介绍</div>
          <div className="ec-d" style={{ fontSize: 13.5, lineHeight: 1.7 }}>{intro}</div>

          {meta?.setup && (
            <>
              <div className="sec-title" style={{ margin: '18px 0 8px' }}>启用方式</div>
              <div className="ec-d" style={{ fontSize: 12.5, lineHeight: 1.65, color: 'var(--text-3)' }}>{meta.setup}</div>
            </>
          )}
          {/* 表单型连接器：配置项就地填、就地存（WB-188），不用改配置文件 */}
          {meta?.configKind === 'weknora' && (
            <WeKnoraConfigForm onChange={(c) => setFormOk(c.configured)} />
          )}

          {/* OAuth 连接过程中的提示 + 手动打开授权页兜底 */}
          {isOAuth && conn === 'connecting' && (
            <div className="ec-d" style={{ fontSize: 12.5, lineHeight: 1.7, color: 'var(--brand-600)', marginTop: 10 }}>
              正在等待 WPS 授权完成…
              {authUrl && <> 没有自动跳转？<a href={authUrl} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--brand-600)', textDecoration: 'underline' }}>点此打开授权页</a></>}
            </div>
          )}
          {isOAuth && conn === 'not_installed' && (
            <div className="ec-d" style={{ fontSize: 12.5, lineHeight: 1.7, color: '#C77700', marginTop: 10 }}>
              未检测到 kdocs-cli（金山文档命令行工具）。请先在本机安装后再连接。
            </div>
          )}

          {meta?.tools && meta.tools.length > 0 && (
            <>
              <WbButton
                type="button"
                className="btn-ghost"
                style={{ margin: '18px 0 4px', padding: '4px 0', fontWeight: 700, color: 'var(--text-2)' }}
                onClick={() => setShowTools((v) => !v)}
              >
                {showTools ? '▾' : '▸'} 能力清单 · {meta.tools.length} 项工具
              </WbButton>
              {showTools && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {meta.tools.map((t) => (
                    <div className="pkc-row" key={t.name} style={{ cursor: 'default', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="pn" style={{ fontFamily: 'var(--mono, monospace)', fontSize: 12.5 }}>{t.name}</div>
                        <div className="pd" style={{ fontSize: 12 }}>{t.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* 试用问法：未接入时不给（点了必然失败），故 oauth 看授权态、表单型看配置态 */}
          {meta?.prompts && meta.prompts.length > 0 && (isOAuth ? conn === 'connected' : (!isForm || formOk)) && (
            <>
              <div className="sec-title" style={{ margin: '18px 0 8px' }}>试试这样问我</div>
              {meta.prompts.map((p) => (
                <div className="pkc-row" key={p} onClick={() => doPrompt(p)}>
                  <div style={{ flex: 1, minWidth: 0, fontSize: 13, color: 'var(--text-2)' }}>“{p}”</div>
                  <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>›</span>
                </div>
              ))}
            </>
          )}
        </div>

        <div className="np-foot" style={{ gap: 8 }}>
          {isOAuth && conn !== 'connected' ? (
            <WbButton
              type="button"
              className="btn-dark"
              style={{ flex: 1, justifyContent: 'center' }}
              disabled={conn === 'connecting' || conn === 'not_installed'}
              onClick={doConnect}
            >
              {conn === 'connecting' ? '连接中…' : '连接'}
            </WbButton>
          ) : (
            <>
              {isOAuth && <WbButton type="button" className="btn-ghost" onClick={doDisconnect}>断开</WbButton>}
              <WbButton type="button" className="btn-ghost" onClick={toggleAdd}>{added ? '移除' : '添加到本会话'}</WbButton>
              <WbButton type="button" className="btn-dark" style={{ flex: 1, justifyContent: 'center' }} onClick={doTry}>去试试</WbButton>
            </>
          )}
        </div>
      </div>
    </AntModalBridge>
  )
}
