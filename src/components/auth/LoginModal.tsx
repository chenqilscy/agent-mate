import { WbButton, WbInput } from '../ui/Primitives'
import { useEffect, useState } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { api, type SsoProvider } from '../../lib/api'
import { toast } from '../../stores/toastStore'
import { AntModalBridge } from '../ui/AntModalBridge'
import { clickable } from '../../lib/a11y'

// Login / register against AgentMate Server, the only account authority. On
// success the store persists the Server token and reloads under that identity.
// Closing the dialog keeps an anonymous local guest scope, not a local account.
export function LoginModal({ onClose }: { onClose: () => void }) {
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const ssoLogin = useAuthStore((s) => s.ssoLogin)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [providers, setProviders] = useState<SsoProvider[]>([])
  const [inviteCode, setInviteCode] = useState('')

  useEffect(() => {
    void api.ssoProviders().then((result) => setProviders(result.providers)).catch(() => setProviders([]))
  }, [])

  const submit = async () => {
    if (!name.trim() || !password || busy) return
    setBusy(true)
    try {
      if (mode === 'login') await login(name.trim(), password)
      else await register(name.trim(), password)
      // success → the store reloads the app; nothing else to do here
    } catch {
      toast(mode === 'login' ? '登录失败：请检查 Server 连接、用户名和密码' : '注册失败：请检查 Server 连接、用户名和密码')
      setBusy(false)
    }
  }

  const submitSso = async (provider: string) => {
    if (busy) return
    setBusy(true)
    try {
      await ssoLogin(provider, inviteCode.trim())
    } catch {
      toast('联合登录未完成：请检查弹窗、Server 配置或首次注册邀请码')
      setBusy(false)
    }
  }

  const onKey = (e: { key: string }) => { if (e.key === 'Enter') void submit() }

  return (
    <AntModalBridge onClose={onClose} closeOnMask={!busy}>
      <div className="np-modal auth-modal" role="dialog" aria-modal="true" aria-label={mode === 'login' ? '登录' : '注册'}>
        <div className="np-h">{mode === 'login' ? '登录' : '注册账号'}<WbButton className="np-x" onClick={onClose}>×</WbButton></div>
        <div className="np-body">
          <div className="np-lbl">AgentMate Server 用户名</div>
          <WbInput className="np-input" value={name} autoFocus placeholder="你的 Server 用户名" onChange={(e) => setName(e.target.value)} onKeyDown={onKey} />
          <div className="np-lbl">密码</div>
          <WbInput className="np-input" type="password" value={password} placeholder={mode === 'register' ? '至少 4 位' : '密码'} onChange={(e) => setPassword(e.target.value)} onKeyDown={onKey} />
          {mode === 'login' && providers.length > 0 ? (
            <div className="auth-sso">
              <div className="auth-sso-divider"><span>或使用联合登录</span></div>
              <WbInput className="np-input" value={inviteCode} placeholder="首次注册邀请码（已有绑定可留空）" onChange={(e) => setInviteCode(e.target.value)} />
              <div className="auth-sso-buttons">
                {providers.map((provider) => (
                  <WbButton key={provider.id} className="btn-ghost" disabled={busy} onClick={() => void submitSso(provider.id)}>
                    {provider.label}
                  </WbButton>
                ))}
              </div>
            </div>
          ) : null}
          <div className="auth-switch">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <span {...clickable} onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? '去注册' : '去登录'}</span>
          </div>
        </div>
        <div className="np-foot">
          <span className="np-hint">账号由 Server 统一提供；关闭后保持匿名访客模式</span>
          <WbButton className="btn-ghost" onClick={onClose}>取消</WbButton>
          <WbButton className="btn-dark" disabled={!name.trim() || !password || busy} onClick={submit}>{mode === 'login' ? '登录' : '注册'}</WbButton>
        </div>
      </div>
    </AntModalBridge>
  )
}
