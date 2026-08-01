import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Empty, Form, Input, Modal, Popconfirm, Segmented, Select, Space, Table, Tag, Typography } from 'antd'
import { api } from '../../lib/api'
import type { GovernanceRecordType, ProjectGovernanceRecord, ProjectMember, RiskSeverity } from '../../lib/types'
import { useWorkItemStore } from '../../stores/workItemStore'
import { toast } from '../../stores/toastStore'

const STATUS = {
  risk: [
    { value: 'open', label: '待处理' }, { value: 'mitigating', label: '应对中' }, { value: 'closed', label: '已关闭' },
  ],
  decision: [
    { value: 'proposed', label: '待决策' }, { value: 'accepted', label: '已采纳' }, { value: 'superseded', label: '已替代' },
  ],
}
const STATUS_LABEL: Record<string, string> = Object.fromEntries([...STATUS.risk, ...STATUS.decision].map((item) => [item.value, item.label]))
const SEVERITY: Array<{ value: RiskSeverity; label: string; color: string }> = [
  { value: 'low', label: '低', color: 'default' }, { value: 'medium', label: '中', color: 'blue' },
  { value: 'high', label: '高', color: 'orange' }, { value: 'critical', label: '严重', color: 'red' },
]

type Draft = Partial<ProjectGovernanceRecord> & { record_type: GovernanceRecordType; title: string }

export function ProjectGovernance({ projectId, canWrite }: { projectId: string; canWrite: boolean }) {
  const [records, setRecords] = useState<ProjectGovernanceRecord[]>([])
  const [members, setMembers] = useState<ProjectMember[]>([])
  const [kind, setKind] = useState<GovernanceRecordType>('risk')
  const [editing, setEditing] = useState<ProjectGovernanceRecord | null>(null)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<Draft>()
  const watchedType = Form.useWatch('record_type', form) || kind
  const items = useWorkItemStore((state) => state.items)
  const milestones = useWorkItemStore((state) => state.milestones)

  const load = useCallback(async () => {
    try {
      const [result, memberResult] = await Promise.all([api.listProjectGovernance(projectId), api.listMembers(projectId)])
      setRecords(result.records); setMembers(memberResult.members)
    } catch { toast('治理台账加载失败') }
  }, [projectId])
  useEffect(() => { void load() }, [load])

  const visible = useMemo(() => records.filter((record) => record.record_type === kind), [records, kind])
  const showCreate = () => {
    setEditing(null)
    form.setFieldsValue({ record_type: kind, title: '', status: kind === 'risk' ? 'open' : 'proposed', severity: kind === 'risk' ? 'medium' : '' })
    setOpen(true)
  }
  const showEdit = (record: ProjectGovernanceRecord) => { setEditing(record); form.setFieldsValue(record); setOpen(true) }
  const save = async () => {
    let values: Draft
    try { values = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      if (editing) await api.updateProjectGovernance(editing.id, values)
      else await api.createProjectGovernance({ ...values, project_id: projectId })
      setOpen(false); form.resetFields(); await load(); toast(editing ? '治理记录已更新' : '治理记录已创建')
    } catch { toast('保存失败，请检查字段或网络连接') } finally { setSaving(false) }
  }
  const remove = async (id: string) => {
    try { await api.deleteProjectGovernance(id); await load(); toast('治理记录已删除') }
    catch { toast('删除失败，请重试') }
  }

  return <div style={{ minWidth: 0 }}>
    <Space wrap style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
      <Segmented value={kind} onChange={(value) => setKind(value as GovernanceRecordType)} options={[{ value: 'risk', label: `风险 ${records.filter((r) => r.record_type === 'risk').length}` }, { value: 'decision', label: `决策 ${records.filter((r) => r.record_type === 'decision').length}` }]} />
      {canWrite && <Button type="primary" onClick={showCreate}>新建{kind === 'risk' ? '风险' : '决策'}</Button>}
    </Space>
    {visible.length ? <Table<ProjectGovernanceRecord>
      rowKey="id" size="small" pagination={false} dataSource={visible} scroll={{ x: 780 }}
      columns={[
        { title: '标题', dataIndex: 'title', width: 220, render: (value, record) => <Space orientation="vertical" size={0}><Typography.Text strong>{value}</Typography.Text>{record.description && <Typography.Text type="secondary" ellipsis style={{ maxWidth: 260 }}>{record.description}</Typography.Text>}</Space> },
        { title: '状态', dataIndex: 'status', width: 95, render: (value) => <Tag>{STATUS_LABEL[value] || value}</Tag> },
        ...(kind === 'risk' ? [{ title: '等级', dataIndex: 'severity', width: 75, render: (value: string) => { const level = SEVERITY.find((item) => item.value === value); return <Tag color={level?.color}>{level?.label || value}</Tag> } }] : []),
        { title: '负责人', dataIndex: 'owner_name', width: 110, render: (value, record) => value || members.find((m) => m.user_id === record.owner_id)?.name || '未指定' },
        { title: '关联', key: 'refs', width: 200, render: (_, record) => <Space wrap size={[4, 4]}>{record.work_item_id && <Tag>任务 · {record.work_item_title || items.find((i) => i.id === record.work_item_id)?.title || record.work_item_id.slice(0, 8)}</Tag>}{record.milestone_id && <Tag>里程碑 · {record.milestone_name || milestones.find((m) => m.id === record.milestone_id)?.name || record.milestone_id.slice(0, 8)}</Tag>}{(record.run_id || record.artifact_id) && <Tag color="blue">执行证据</Tag>}</Space> },
        { title: '操作', key: 'actions', fixed: 'right', width: 120, render: (_, record) => canWrite ? <Space><Button type="link" size="small" onClick={() => showEdit(record)}>编辑</Button><Popconfirm title="确认删除这条治理记录？" onConfirm={() => void remove(record.id)}><Button type="link" danger size="small">删除</Button></Popconfirm></Space> : null },
      ]}
    /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={kind === 'risk' ? '暂无风险记录' : '暂无决策记录'} />}

    <Modal open={open} title={editing ? `编辑${kind === 'risk' ? '风险' : '决策'}` : `新建${kind === 'risk' ? '风险' : '决策'}`} onCancel={() => setOpen(false)} onOk={() => void save()} confirmLoading={saving} destroyOnHidden forceRender afterOpenChange={(visible) => {
      if (visible) form.setFieldsValue(editing || {
        record_type: kind, title: '', status: kind === 'risk' ? 'open' : 'proposed',
        severity: kind === 'risk' ? 'medium' : '',
      })
    }}>
      <Form form={form} layout="vertical" preserve={false} onValuesChange={(changed) => {
        if (changed.record_type) form.setFieldsValue({ status: changed.record_type === 'risk' ? 'open' : 'proposed', severity: changed.record_type === 'risk' ? 'medium' : '' })
      }}>
        <Form.Item name="record_type" label="类型" rules={[{ required: true }]}><Select disabled={!!editing} options={[{ value: 'risk', label: '风险' }, { value: 'decision', label: '决策' }]} /></Form.Item>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true, max: 300 }]}><Input /></Form.Item>
        <Form.Item name="description" label="说明"><Input.TextArea rows={3} maxLength={20000} /></Form.Item>
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}><Select style={{ width: 150 }} options={STATUS[watchedType]} /></Form.Item>
          {watchedType === 'risk' && <Form.Item name="severity" label="风险等级" rules={[{ required: true }]}><Select style={{ width: 130 }} options={SEVERITY} /></Form.Item>}
          <Form.Item name="owner_id" label="负责人"><Select allowClear style={{ width: 160 }} options={members.map((m) => ({ value: m.user_id, label: m.name }))} /></Form.Item>
        </Space>
        {watchedType === 'risk' ? <Form.Item name="response" label="应对措施"><Input.TextArea rows={2} /></Form.Item> : <Form.Item name="rationale" label="决策依据"><Input.TextArea rows={2} /></Form.Item>}
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="work_item_id" label="关联任务"><Select allowClear showSearch optionFilterProp="label" style={{ width: 220 }} options={items.map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Form.Item name="milestone_id" label="关联里程碑"><Select allowClear style={{ width: 190 }} options={milestones.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
        </Space>
        <Form.Item name="evidence_label" label="执行证据说明"><Input placeholder="例如：回归验证通过，详见本次运行" maxLength={500} /></Form.Item>
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="run_id" label="运行 ID"><Input style={{ width: 220 }} /></Form.Item>
          <Form.Item name="artifact_id" label="产物 ID"><Input style={{ width: 220 }} /></Form.Item>
        </Space>
      </Form>
    </Modal>
  </div>
}
