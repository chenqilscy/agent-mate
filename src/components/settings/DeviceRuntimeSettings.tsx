import { useEffect, useMemo, useState } from 'react'
import { Alert, Card, InputNumber, List, Popconfirm, Switch, Tag } from 'antd'
import { api } from '../../lib/api'
import type { DeviceSettingItem, DeviceSettingsPayload } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { WbButton, WbInput, WbSelect } from '../ui/Primitives'

type Values = Record<string, string | number | boolean>

const sourceLabel: Record<string, string> = {
  database: '页面设置', environment: '环境变量', default: '系统默认',
}

function initialValues(data: DeviceSettingsPayload): Values {
  const values: Values = {}
  for (const item of data.items) {
    if (!item.secret && item.value !== null) values[item.key] = item.value
    if (item.secret) values[item.key] = ''
  }
  return values
}

export function DeviceRuntimeSettings() {
  const [data, setData] = useState<DeviceSettingsPayload | null>(null)
  const [values, setValues] = useState<Values>({})
  const [busy, setBusy] = useState(false)
  const [testing, setTesting] = useState('')

  const load = async () => {
    try {
      const next = await api.runtimeSettings()
      setData(next); setValues(initialValues(next))
    } catch { toast('加载运行设置失败') }
  }
  useEffect(() => { void load() }, [])

  const groups = useMemo(() => ({
    observability: data?.items.filter((item) => item.group === 'observability') || [],
    voice: data?.items.filter((item) => item.group === 'voice') || [],
    collaboration: data?.items.filter((item) => item.group === 'collaboration') || [],
  }), [data])

  const change = (key: string, value: string | number | boolean) => setValues((current) => ({ ...current, [key]: value }))
  const save = async () => {
    if (!data) return
    setBusy(true)
    try {
      const payload: Record<string, unknown> = {}
      for (const item of data.items) {
        const value = values[item.key]
        if (!item.secret || String(value || '').trim()) payload[item.key] = value
      }
      const next = await api.saveRuntimeSettings(payload)
      setData(next); setValues(initialValues(next)); toast('运行设置已保存并生效')
    } catch { toast('运行设置保存失败，请检查字段格式') }
    finally { setBusy(false) }
  }
  const clear = async (items: DeviceSettingItem[]) => {
    try {
      const next = await api.saveRuntimeSettings({}, items.map((item) => item.key))
      setData(next); setValues(initialValues(next)); toast('已恢复环境变量或系统默认值')
    } catch { toast('恢复设置失败') }
  }
  const test = async (group: string) => {
    setTesting(group)
    try {
      const result = await api.testRuntimeSettings(group)
      toast(result.ok ? `${group === 'voice' ? '语音依赖' : group === 'collaboration' ? 'Server' : 'Langfuse'}连接正常` : String(result.error || '测试失败'))
    } catch { toast('测试失败') }
    finally { setTesting('') }
  }

  const field = (item: DeviceSettingItem) => {
    const value = values[item.key]
    return (
      <div className="set-field" key={item.key}>
        <div className="set-fhd">
          <div className="set-fname">{item.label} <Tag>{sourceLabel[item.source] || item.source}</Tag>{item.secret && <Tag color={item.configured ? 'green' : 'default'}>{item.configured ? '已配置' : '未配置'}</Tag>}</div>
          <div className="set-fsub">{item.description}</div>
        </div>
        {item.value_type === 'boolean' ? <Switch checked={Boolean(value)} onChange={(checked) => change(item.key, checked)} />
          : item.value_type === 'choice' ? <WbSelect className="np-input set-select" value={String(value || '')} onChange={(event) => change(item.key, event.target.value)}>{item.choices.map((choice) => <option value={choice} key={choice}>{choice}</option>)}</WbSelect>
            : item.value_type === 'number' ? <InputNumber min={item.minimum ?? undefined} max={item.maximum ?? undefined} step={0.1} value={Number(value ?? 0)} onChange={(next) => change(item.key, Number(next ?? 0))} style={{ width: 180 }} />
              : <WbInput className="np-input set-select" type={item.secret ? 'password' : 'text'} autoComplete={item.secret ? 'new-password' : undefined} placeholder={item.secret ? '输入新密钥以替换' : item.placeholder} value={String(value || '')} onChange={(event) => change(item.key, event.target.value)} />}
      </div>
    )
  }

  const section = (title: string, group: keyof typeof groups, warning?: string) => (
    <Card className="set-card" title={title} extra={<><WbButton className="btn-ghost" disabled={testing === group} onClick={() => void test(group)}>{testing === group ? '测试中…' : '测试'}</WbButton> <Popconfirm title={`恢复${title}的环境变量或默认值？`} onConfirm={() => void clear(groups[group])}><WbButton className="btn-ghost">恢复</WbButton></Popconfirm></>}>
      {warning && <Alert type="warning" showIcon message={warning} />}
      {groups[group].map(field)}
    </Card>
  )

  if (!data) return <div className="set-body"><div className="set-ptitle">运行服务</div><div className="set-pdesc">加载中…</div></div>
  return (
    <div className="set-body">
      <div className="set-ptitle">运行服务</div>
      <div className="set-pdesc">这些设置对当前设备生效，保存后无需修改 .env 或重启。密钥只保存在本机后端且不会回显。</div>
      {section('可观测性 · Langfuse', 'observability', '启用“采集对话正文”会把提示词、回复及工具正文发送到配置的 Langfuse，请确认符合隐私要求。')}
      {section('本地语音识别', 'voice')}
      {section('Server 与协作隐私', 'collaboration')}
      <Card className="set-card" title="启动级配置边界">
        <div className="set-pdesc">以下参数必须由部署或安装过程管理：</div>
        <div>{data.deployment_only.map((key) => <Tag key={key}>{key}</Tag>)}</div>
      </Card>
      <Card className="set-card" title="最近设置审计">
        <List size="small" dataSource={data.audit.slice(0, 20)} renderItem={(item) => <List.Item><List.Item.Meta title={`${item.setting_key} · ${item.action === 'clear' ? '恢复' : '保存'}`} description={`${item.before_value || '-'} → ${item.after_value || '-'} · ${new Date(item.created_at * 1000).toLocaleString()}`} /></List.Item>} />
      </Card>
      <div className="set-actions"><WbButton className="btn-dark" disabled={busy} onClick={() => void save()}>{busy ? '保存中…' : '保存并生效'}</WbButton></div>
    </div>
  )
}
