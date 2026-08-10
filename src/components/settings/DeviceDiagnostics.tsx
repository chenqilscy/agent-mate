import { useEffect, useState } from 'react'
import { Alert, Card, Empty, Popconfirm, Space, Statistic, Tag } from 'antd'
import { api } from '../../lib/api'
import type { DeviceDiagnosticIssue, DeviceDiagnostics } from '../../lib/types'
import { useChatStore } from '../../stores/chatStore'
import { toast } from '../../stores/toastStore'
import { useUIStore } from '../../stores/uiStore'
import { WbButton } from '../ui/Primitives'
import { CompatList as List } from '../ui/CompatList'

function bytes(value: number) {
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

export function DeviceDiagnosticsPanel() {
  const [data, setData] = useState<DeviceDiagnostics | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const setTab = useUIStore((state) => state.setSettingsTab)
  const setSettingsOpen = useUIStore((state) => state.setSettingsOpen)
  const setView = useUIStore((state) => state.setView)
  const openSession = useChatStore((state) => state.openSession)

  const load = async () => {
    try { setData(await api.deviceDiagnostics()); setError('') }
    catch (reason) { setError(reason instanceof Error ? reason.message : '诊断读取失败') }
  }
  useEffect(() => {
    void load()
    const timer = window.setInterval(() => { void load() }, 10_000)
    return () => window.clearInterval(timer)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const runAction = async (action: 'retry_transport' | 'register_device' | 'clear_completed') => {
    setBusy(action)
    try {
      const result = await api.deviceDiagnosticAction(action)
      setData(result.diagnostics)
      toast(action === 'retry_transport' ? '已重试 Server 心跳与 WAL 传输' : action === 'register_device' ? '设备注册已刷新' : `已清理 ${Number(result.result.deleted || 0)} 条已确认缓存`)
    } catch (reason) { toast(reason instanceof Error ? reason.message : '恢复操作失败') }
    finally { setBusy('') }
  }
  const issueAction = async (issue: DeviceDiagnosticIssue) => {
    if (issue.action === 'retry_transport') return runAction('retry_transport')
    if (issue.action === 'runtime_settings') { setTab('runtime'); return }
    if (issue.action === 'login') { setTab('account'); return }
    if (issue.action === 'connectors') { setSettingsOpen(false); setView('connectors'); return }
    if (issue.action === 'recheck') { await load(); return }
    if (issue.action === 'open_run' && issue.run_id) {
      try {
        const run = await api.getRun(issue.run_id)
        setSettingsOpen(false)
        setView(run.project_id ? 'projexec' : 'chat', { projectId: run.project_id || undefined, sessionId: run.session_id })
        await openSession(run.session_id)
      } catch { toast('无法打开对应 Run') }
    }
  }

  if (!data) return <div className="set-body"><div className="set-ptitle">执行诊断与恢复</div>{error ? <Alert type="error" showIcon title="诊断读取失败" description={error} action={<WbButton className="btn-line" onClick={() => void load()}>重试</WbButton>} /> : <div className="set-pdesc">正在检查 Local Agent…</div>}</div>

  const active = data.transport.leases.filter((item) => item.status === 'active').length
  const unhealthyConnectors = data.connectors.filter((item) => item.enabled && !item.healthy).length
  return <div className="set-body">
    <div className="set-ptitle">执行诊断与恢复</div>
    <div className="set-pdesc">数据直接来自这台 Local Agent；恢复动作只重试可恢复传输或清理已确认缓存，不会删除运行中任务、WAL 或工作文件。</div>
    <Alert type={data.healthy ? 'success' : 'warning'} showIcon title={data.healthy ? 'Local Agent 运行正常' : `发现 ${data.issues.length} 个需要关注的问题`} description={`检查时间 ${new Date(data.checked_at * 1000).toLocaleString()} · 协议 v${data.process.protocol_version} · PID ${data.process.pid}`} />
    <div className="home-metrics" style={{ marginTop: 14 }}>
      <Card className="home-metric"><Statistic title="活动 Run" value={active} /></Card>
      <Card className={`home-metric ${data.transport.wal.count ? 'danger' : ''}`}><Statistic title="等待 ACK" value={data.transport.wal.count} suffix={data.transport.wal.count ? `· ${bytes(data.transport.wal.bytes)}` : undefined} /></Card>
      <Card className={`home-metric ${unhealthyConnectors ? 'danger' : ''}`}><Statistic title="连接器异常" value={unhealthyConnectors} /></Card>
    </div>
    <Card className="set-card" title="需要处理" extra={<WbButton className="btn-ghost" onClick={() => void load()}>重新检测</WbButton>}>
      {data.issues.length ? <List dataSource={data.issues} renderItem={(issue) => <List.Item actions={[<WbButton key="action" className="btn-ghost" onClick={() => void issueAction(issue)}>{issue.action === 'open_run' ? '打开 Run' : issue.action === 'connectors' ? '管理连接器' : issue.action === 'login' ? '查看账号' : issue.action === 'runtime_settings' ? '运行设置' : issue.action === 'retry_transport' ? '立即重试' : '重新检测'}</WbButton>]}><List.Item.Meta title={<Space><Tag color={issue.severity === 'error' ? 'error' : 'warning'}>{issue.severity === 'error' ? '阻断' : '提醒'}</Tag>{issue.title}</Space>} description={issue.detail} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有需要处理的问题" />}
    </Card>
    <Card className="set-card" title="传输与执行">
      <List size="small" dataSource={data.transport.leases.slice(0, 20)} locale={{ emptyText: '暂无 Run lease' }} renderItem={(item) => <List.Item><List.Item.Meta title={<Space>{item.run_id}<Tag>{item.status}</Tag><Tag>epoch {item.lease_epoch}</Tag></Space>} description={item.last_error || `ACK ${item.ack_high_water} · ${new Date(item.updated_at * 1000).toLocaleString()}`} /></List.Item>} />
    </Card>
    <Card className="set-card" title="后台组件">
      <List size="small" dataSource={data.workers.components} locale={{ emptyText: '后台组件尚未产生健康记录' }} renderItem={(item) => <List.Item><List.Item.Meta title={<Space>{item.name}<Tag color={item.consecutive_failures ? 'error' : 'success'}>{item.consecutive_failures ? `连续失败 ${item.consecutive_failures}` : '正常'}</Tag></Space>} description={item.last_error || (item.last_success_at ? `最近成功 ${new Date(item.last_success_at * 1000).toLocaleString()}` : '等待首次执行')} /></List.Item>} />
    </Card>
    <Card className="set-card" title="安全恢复操作">
      <Space wrap>
        <WbButton className="btn-dark" disabled={busy === 'retry_transport'} onClick={() => void runAction('retry_transport')}>重试心跳与传输</WbButton>
        <WbButton className="btn-ghost" disabled={busy === 'register_device'} onClick={() => void runAction('register_device')}>刷新设备注册</WbButton>
        <Popconfirm title="只清理已获 Server ACK 且终态完成的本机 lease 缓存？" onConfirm={() => void runAction('clear_completed')}><WbButton className="btn-ghost">清理已确认缓存</WbButton></Popconfirm>
      </Space>
    </Card>
  </div>
}
