import { useEffect, useState } from 'react'
import { Switch } from 'antd'
import { platform, type UpdateResult } from '../../platform'
import {
  checkDesktopUpdate, getLastUpdateResult, getUpdatePreferences,
  saveUpdatePreferences, type UpdatePreferences,
} from '../../platform/updates'
import { toast } from '../../stores/toastStore'
import { WbButton, WbInput, WbSelect } from '../ui/Primitives'

export function DesktopUpdateSettings() {
  const [prefs, setPrefs] = useState<UpdatePreferences>(() => getUpdatePreferences())
  const [result, setResult] = useState<UpdateResult | null>(() => getLastUpdateResult())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const handler = (event: Event) => setResult((event as CustomEvent<UpdateResult>).detail)
    window.addEventListener('agentmate:update-status', handler)
    return () => window.removeEventListener('agentmate:update-status', handler)
  }, [])

  const persist = (next: UpdatePreferences) => {
    setPrefs(saveUpdatePreferences(next))
    setError('')
  }
  const check = async (install = false) => {
    setBusy(true); setError('')
    try {
      const next = await checkDesktopUpdate(saveUpdatePreferences(prefs), install)
      setResult(next)
      if (next.status === 'latest') toast('当前已是最新版本')
      if (next.status === 'available') toast(`发现版本 ${next.version}`)
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message); toast(install ? '更新安装失败' : '检查更新失败')
    } finally { setBusy(false) }
  }

  const status = !platform.isDesktop
    ? '浏览器版不执行桌面更新'
    : error || (result?.status === 'available'
      ? `${result.rollback ? '回滚' : '可用'} ${result.version}${result.forced ? '（最低版本要求）' : ''}`
      : result?.status === 'latest' ? `已是最新版本${result.current_version ? ` ${result.current_version}` : ''}`
        : '尚未检查')

  return (
    <>
      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">桌面更新服务</div>
          <div className="set-fsub">生产环境只接受 HTTPS；地址由部署或当前设备显式配置。</div>
        </div>
        <WbInput className="np-input set-select" aria-label="桌面更新服务地址" placeholder="https://updates.example.com"
          value={prefs.endpoint} onChange={(e) => persist({ ...prefs, endpoint: e.target.value })} />
      </div>
      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">更新通道</div>
          <div className="set-fsub">stable 用于正式灰度，beta 用于提前验证；同一设备稳定分桶。</div>
        </div>
        <WbSelect className="np-input set-select" aria-label="更新通道" value={prefs.channel}
          onChange={(e) => persist({ ...prefs, channel: e.target.value === 'beta' ? 'beta' : 'stable' })}>
          <option value="stable">Stable</option>
          <option value="beta">Beta</option>
        </WbSelect>
      </div>
      <div className="set-field">
        <div className="set-fhd">
          <div className="set-fname">每日自动检查</div>
          <div className="set-fsub">只检查签名 manifest；下载和安装始终需要手工确认。</div>
        </div>
        <Switch checked={prefs.automatic} onChange={(automatic) => persist({ ...prefs, automatic })} />
      </div>
      <div className="set-actions">
        <WbButton className="btn-ghost" disabled={!platform.isDesktop || busy || !prefs.endpoint} onClick={() => void check(false)}>
          {busy ? '检查中…' : '检查更新'}
        </WbButton>
        {result?.status === 'available' && (
          <WbButton className="btn-dark" disabled={busy} onClick={() => void check(true)}>
            {result.rollback ? '下载并回滚' : '下载并安装'}
          </WbButton>
        )}
        <span className="set-pdesc">{status}</span>
      </div>
    </>
  )
}
