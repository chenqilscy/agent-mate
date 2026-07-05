import { useState } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { toast } from '../../stores/toastStore'

// Login / register for real accounts (M7 C1). On success the store persists the
// token and reloads the app under the new identity. Not logging in keeps you as
// the local owner.
export function LoginModal({ onClose }: { onClose: () => void }) {
  const login = useAuthStore((s) => s.login)
  const register = useAuthStore((s) => s.register)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    if (!name.trim() || !password || busy) return
    setBusy(true)
    try {
      if (mode === 'login') await login(name.trim(), password)
      else await register(name.trim(), password)
      // success → the store reloads the app; nothing else to do here
    } catch {
      toast(mode === 'login' ? '登录失败：用户名或密码错误' : '注册失败：用户名可能已被占用，或密码太短（≥4 位）')
      setBusy(false)
    }
  }

  const onKey = (e: { key: string }) => { if (e.key === 'Enter') void submit() }

  return (
    <div className="np-overlay open" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="np-modal auth-modal" role="dialog" aria-modal="true" aria-label={mode === 'login' ? '登录' : '注册'}>
        <div className="np-h">{mode === 'login' ? '登录' : '注册账号'}<button className="np-x" onClick={onClose}>×</button></div>
        <div className="np-body">
          <div className="np-lbl">用户名</div>
          <input className="np-input" value={name} autoFocus placeholder="你的用户名" onChange={(e) => setName(e.target.value)} onKeyDown={onKey} />
          <div className="np-lbl">密码</div>
          <input className="np-input" type="password" value={password} placeholder={mode === 'register' ? '至少 4 位' : '密码'} onChange={(e) => setPassword(e.target.value)} onKeyDown={onKey} />
          <div className="auth-switch">
            {mode === 'login' ? '还没有账号？' : '已有账号？'}
            <span onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? '去注册' : '去登录'}</span>
          </div>
        </div>
        <div className="np-foot">
          <span className="np-hint">不登录也可用（本地所有者）</span>
          <button className="btn-ghost" onClick={onClose}>取消</button>
          <button className="btn-dark" disabled={!name.trim() || !password || busy} onClick={submit}>{mode === 'login' ? '登录' : '注册'}</button>
        </div>
      </div>
    </div>
  )
}
