import { useEffect, useState } from 'react'
import { Alert, Form, Input, Modal, Select, Space, Switch, Tag } from 'antd'
import { api } from '../../lib/api'
import type { ConnectorRuntimeStatus, LocalConnectorInstance, LocalConnectorPayload } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { WbButton } from '../ui/Primitives'
import { CompatList as List } from '../ui/CompatList'

type Draft = {
  name: string
  transport: 'stdio' | 'sse'
  command: string
  argsText: string
  url: string
  environmentText: string
  secretText: string
  enabled: boolean
}

const EMPTY: Draft = {
  name: '', transport: 'stdio', command: '', argsText: '', url: '',
  environmentText: '', secretText: '', enabled: true,
}

function pairs(text: string, label: string): Record<string, string> {
  const result: Record<string, string> = {}
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line) continue
    const index = line.indexOf('=')
    if (index < 1) throw new Error(`${label}必须使用 KEY=VALUE，每行一项`)
    result[line.slice(0, index).trim()] = line.slice(index + 1)
  }
  return result
}

function fromInstance(item: LocalConnectorInstance): Draft {
  return {
    name: item.name, transport: item.transport, command: item.command,
    argsText: item.args.join('\n'), url: item.url,
    environmentText: Object.entries(item.environment).map(([key, value]) => `${key}=${value}`).join('\n'),
    secretText: item.secret_keys.map((key) => `${key}=`).join('\n'), enabled: item.enabled,
  }
}

export function LocalConnectorManager({ open, onClose, onChanged }: {
  open: boolean
  onClose: () => void
  onChanged: (payload: LocalConnectorPayload) => void
}) {
  const [payload, setPayload] = useState<LocalConnectorPayload>({ instances: [], statuses: [] })
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState<LocalConnectorInstance | null | undefined>(undefined)
  const [draft, setDraft] = useState<Draft>(EMPTY)
  const [busy, setBusy] = useState('')
  const [credential, setCredential] = useState<ConnectorRuntimeStatus | null>(null)
  const [credentialValues, setCredentialValues] = useState<Record<string, string>>({})

  const refresh = async () => {
    setLoading(true)
    try {
      const next = await api.localConnectors()
      setPayload(next); onChanged(next)
    } catch (error) {
      toast(error instanceof Error ? error.message : '本机连接器读取失败')
    } finally { setLoading(false) }
  }
  useEffect(() => { if (open) void refresh() }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => {
    setBusy('save')
    try {
      const environment = pairs(draft.environmentText, '环境变量')
      const secrets = pairs(draft.secretText, '凭据')
      const secretKeys = [...new Set([
        ...(editing?.secret_keys ?? []),
        ...Object.keys(secrets),
      ])]
      const body = {
        name: draft.name.trim(), transport: draft.transport, command: draft.command.trim(),
        args: draft.argsText.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
        url: draft.url.trim(), environment, secrets, secret_keys: secretKeys, enabled: draft.enabled,
      }
      const next = editing
        ? await api.updateLocalConnector(editing.id, body)
        : await api.createLocalConnector(body)
      setPayload(next); onChanged(next); setEditing(undefined)
      toast('连接器已保存，请执行连通测试')
    } catch (error) {
      toast(error instanceof Error ? error.message : '连接器保存失败')
    } finally { setBusy('') }
  }
  const test = async (item: LocalConnectorInstance) => {
    setBusy(`test:${item.id}`)
    try {
      const result = await api.testLocalConnector(item.id)
      toast(result.ok ? `连接成功 · 发现 ${result.tools.length} 个工具` : result.error || '连接失败')
      await refresh()
    } finally { setBusy('') }
  }
  const toggle = async (item: LocalConnectorInstance, enabled: boolean) => {
    setBusy(`toggle:${item.id}`)
    try {
      const next = await api.setLocalConnectorEnabled(item.id, enabled)
      setPayload(next); onChanged(next)
    } finally { setBusy('') }
  }
  const remove = (item: LocalConnectorInstance) => Modal.confirm({
    title: `删除“${item.name}”？`, content: '本机启动定义与加密凭据将一并删除。', okText: '删除', okType: 'danger', cancelText: '取消',
    onOk: async () => {
      const next = await api.deleteLocalConnector(item.id)
      setPayload(next); onChanged(next); toast('连接器已删除')
    },
  })
  const saveCredentials = async () => {
    if (!credential) return
    setBusy('credential')
    try {
      const values = Object.fromEntries(Object.entries(credentialValues).filter(([, value]) => value))
      const next = await api.setBuiltinConnectorCredentials(credential.name, values)
      setPayload(next); onChanged(next); setCredential(null); setCredentialValues({})
      toast('凭据已加密保存到这台设备')
    } finally { setBusy('') }
  }

  return (
    <>
      <Modal title="本机 MCP 与连接器" open={open} onCancel={onClose} footer={null} width={760} destroyOnHidden>
        <Alert type="info" showIcon title="启动定义与凭据只保存在 Local Agent；凭据不会返回前端，也不会同步到 Server。" />
        <div className="ph" style={{ marginTop: 14, alignItems: 'center' }}>
          <b>运行状态</b><span style={{ flex: 1 }} />
          <WbButton className="btn-dark" onClick={() => { setDraft(EMPTY); setEditing(null) }}>＋ 添加 MCP</WbButton>
        </div>
        <List loading={loading} dataSource={payload.statuses} locale={{ emptyText: '还没有本机连接器' }} renderItem={(status) => {
          const instance = payload.instances.find((item) => item.id === status.id)
          return <List.Item actions={instance ? [
            <WbButton key="test" className="btn-ghost" disabled={busy === `test:${instance.id}`} onClick={() => void test(instance)}>测试</WbButton>,
            <WbButton key="edit" className="btn-ghost" onClick={() => { setDraft(fromInstance(instance)); setEditing(instance) }}>编辑</WbButton>,
            <WbButton key="delete" className="btn-ghost" onClick={() => remove(instance)}>删除</WbButton>,
          ] : status.credential_keys.length ? [
            <WbButton key="credential" className="btn-ghost" onClick={() => { setCredential(status); setCredentialValues({}) }}>配置凭据</WbButton>,
            <WbButton key="test" className="btn-ghost" onClick={() => void api.testConnectorByName(status.name).then((result) => toast(result.ok ? `连接成功 · ${result.tools.length} 个工具` : result.error))}>测试</WbButton>,
          ] : undefined}>
            <List.Item.Meta
              title={<Space>{status.name}<Tag>{status.transport}</Tag>{status.healthy ? <Tag color="success">可用</Tag> : <Tag color="warning">{status.health_status}</Tag>}</Space>}
              description={status.last_error || (status.tool_count ? `${status.tool_count} 个工具` : status.source === 'builtin' ? '内置连接器' : '等待连通测试')}
            />
            {instance && <Switch checked={instance.enabled} loading={busy === `toggle:${instance.id}`} onChange={(value) => void toggle(instance, value)} />}
          </List.Item>
        }} />
      </Modal>

      <Modal title={editing ? `编辑 · ${editing.name}` : '添加本机 MCP'} open={editing !== undefined} onCancel={() => setEditing(undefined)} onOk={() => void save()} confirmLoading={busy === 'save'} okText="保存" cancelText="取消" width={640} destroyOnHidden>
        <Form layout="vertical">
          <Form.Item label="名称" required><Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Form.Item>
          <Form.Item label="传输方式" required><Select value={draft.transport} options={[{ value: 'stdio', label: 'stdio 本机进程' }, { value: 'sse', label: 'HTTP/SSE 服务' }]} onChange={(transport) => setDraft({ ...draft, transport })} /></Form.Item>
          {draft.transport === 'stdio' ? <>
            <Form.Item label="启动命令" required><Input value={draft.command} placeholder="例如 npx 或可执行文件绝对路径" onChange={(event) => setDraft({ ...draft, command: event.target.value })} /></Form.Item>
            <Form.Item label="参数（每行一项）"><Input.TextArea rows={4} value={draft.argsText} onChange={(event) => setDraft({ ...draft, argsText: event.target.value })} /></Form.Item>
            <Form.Item label="非敏感环境变量（KEY=VALUE，每行一项）"><Input.TextArea rows={3} value={draft.environmentText} onChange={(event) => setDraft({ ...draft, environmentText: event.target.value })} /></Form.Item>
          </> : <Form.Item label="SSE 地址" required><Input value={draft.url} placeholder="https://example.com/sse" onChange={(event) => setDraft({ ...draft, url: event.target.value })} /></Form.Item>}
          <Form.Item label={draft.transport === 'stdio' ? '凭据环境变量（KEY=VALUE，每行一项）' : '凭据 Header（KEY=VALUE，每行一项）'} extra="已保存的值不会回显；留空会保留原值。">
            <Input.TextArea rows={3} value={draft.secretText} onChange={(event) => setDraft({ ...draft, secretText: event.target.value })} />
          </Form.Item>
          <Form.Item label="启用"><Switch checked={draft.enabled} onChange={(enabled) => setDraft({ ...draft, enabled })} /></Form.Item>
        </Form>
      </Modal>

      <Modal title={credential ? `配置凭据 · ${credential.name}` : '配置凭据'} open={Boolean(credential)} onCancel={() => setCredential(null)} onOk={() => void saveCredentials()} confirmLoading={busy === 'credential'} okText="加密保存" cancelText="取消" destroyOnHidden>
        <Form layout="vertical">
          {credential?.credential_keys.map((key) => <Form.Item key={key} label={key}><Input.Password value={credentialValues[key] || ''} onChange={(event) => setCredentialValues({ ...credentialValues, [key]: event.target.value })} /></Form.Item>)}
        </Form>
      </Modal>
    </>
  )
}
