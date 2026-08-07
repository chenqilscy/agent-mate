import { useCallback, useEffect, useMemo, useState } from 'react'
import { Alert, Button, Empty, Form, Input, Modal, Popconfirm, Segmented, Select, Space, Table, Tag, Typography } from 'antd'
import { api } from '../../lib/api'
import { RISK_DESCRIPTION_TEMPLATE } from '../../lib/governance'
import type { GovernanceRecordType, ProjectGovernanceRecord, ProjectMember, RiskSeverity } from '../../lib/types'
import { useWorkItemStore } from '../../stores/workItemStore'
import { toast } from '../../stores/toastStore'
import { MarkdownEditor } from '../common/MarkdownEditor'

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
const PRIORITY_LABEL: Record<RiskSeverity, string> = { low: '低', medium: '中', high: '高', critical: '紧急' }

const ACTION_TASK_ACCEPTANCE_TEMPLATE = `- [ ] 已完成风险应对措施中的全部实施项
- [ ] 相关正常路径和异常路径无回归
- [ ] 已通过真实 Run 交付，且交付物完整性校验通过
- [ ] 已记录验证结果、残余风险和必要的后续监控`

function markdownSummary(value: string): string {
  return value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*+]\s+(?:\[[ xX]\]\s*)?/gm, '')
    .replace(/^\s*\d+[.)]\s+/gm, '')
    .replace(/[>*_~`|]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

type Draft = Partial<ProjectGovernanceRecord> & { record_type: GovernanceRecordType; title: string }
type ActionTaskDraft = { title: string; due_date: string; acceptance_criteria: string }

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function ProjectGovernance({ projectId, canWrite }: { projectId: string; canWrite: boolean }) {
  const [records, setRecords] = useState<ProjectGovernanceRecord[]>([])
  const [members, setMembers] = useState<ProjectMember[]>([])
  const [kind, setKind] = useState<GovernanceRecordType>('risk')
  const [editing, setEditing] = useState<ProjectGovernanceRecord | null>(null)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [actionRisk, setActionRisk] = useState<ProjectGovernanceRecord | null>(null)
  const [actionOpen, setActionOpen] = useState(false)
  const [actionSaving, setActionSaving] = useState(false)
  const [form] = Form.useForm<Draft>()
  const [actionForm] = Form.useForm<ActionTaskDraft>()
  const watchedType = Form.useWatch('record_type', form) || kind
  const watchedStatus = Form.useWatch('status', form)
  const items = useWorkItemStore((state) => state.items)
  const milestones = useWorkItemStore((state) => state.milestones)
  const reloadWorkItems = useWorkItemStore((state) => state.load)

  const load = useCallback(async () => {
    try {
      const [result, memberResult] = await Promise.all([api.listProjectGovernance(projectId), api.listMembers(projectId)])
      setRecords(result.records); setMembers(memberResult.members)
    } catch { toast('治理台账加载失败') }
  }, [projectId])
  useEffect(() => {
    void load()
    void reloadWorkItems(projectId)
  }, [load, projectId, reloadWorkItems])

  const visible = useMemo(() => records.filter((record) => record.record_type === kind), [records, kind])
  const initialDraft = (recordType: GovernanceRecordType): Draft => ({
    record_type: recordType,
    title: '',
    description: recordType === 'risk' ? RISK_DESCRIPTION_TEMPLATE : '',
    status: recordType === 'risk' ? 'open' : 'proposed',
    severity: recordType === 'risk' ? 'medium' : '',
  })
  const showCreate = () => {
    setEditing(null)
    form.setFieldsValue(initialDraft(kind))
    setOpen(true)
  }
  const showEdit = (record: ProjectGovernanceRecord) => { setEditing(record); form.setFieldsValue(record); setOpen(true) }
  const showClose = (record: ProjectGovernanceRecord) => {
    setEditing(record)
    form.setFieldsValue({ ...record, status: 'closed' })
    setOpen(true)
  }
  const showActionTask = (record: ProjectGovernanceRecord) => {
    const milestone = milestones.find((item) => item.id === record.milestone_id)
    setActionRisk(record)
    actionForm.setFieldsValue({
      title: `[风险处置] ${record.title}`.slice(0, 300),
      due_date: milestone?.due_date || '',
      acceptance_criteria: ACTION_TASK_ACCEPTANCE_TEMPLATE,
    })
    setActionOpen(true)
  }
  const save = async () => {
    let values: Draft
    try { values = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      if (editing) await api.updateProjectGovernance(projectId, editing.id, values)
      else await api.createProjectGovernance({ ...values, project_id: projectId })
      setOpen(false); form.resetFields(); await load(); toast(editing ? '治理记录已更新' : '治理记录已创建')
    } catch (error) { toast(errorMessage(error, '保存失败，请检查字段或网络连接')) } finally { setSaving(false) }
  }
  const createActionTask = async () => {
    if (!actionRisk) return
    let values: ActionTaskDraft
    try { values = await actionForm.validateFields() } catch { return }
    setActionSaving(true)
    try {
      const result = await api.createRiskActionTask(projectId, actionRisk.id, values)
      setActionOpen(false); actionForm.resetFields(); setActionRisk(null)
      await Promise.all([load(), reloadWorkItems(projectId)])
      toast(result.created ? '处置任务已创建并关联风险' : '风险已关联现有处置任务')
    } catch (error) { toast(errorMessage(error, '处置任务创建失败')) } finally { setActionSaving(false) }
  }
  const remove = async (id: string) => {
    try { await api.deleteProjectGovernance(projectId, id); await load(); toast('治理记录已删除') }
    catch { toast('删除失败，请重试') }
  }

  return <div style={{ minWidth: 0 }}>
    <Space wrap style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
      <Segmented value={kind} onChange={(value) => setKind(value as GovernanceRecordType)} options={[{ value: 'risk', label: `风险 ${records.filter((r) => r.record_type === 'risk').length}` }, { value: 'decision', label: `决策 ${records.filter((r) => r.record_type === 'decision').length}` }]} />
      {canWrite && <Button type="primary" onClick={showCreate}>新建{kind === 'risk' ? '风险' : '决策'}</Button>}
    </Space>
    {visible.length ? <Table<ProjectGovernanceRecord>
      rowKey="id" size="small" pagination={false} dataSource={visible} scroll={{ x: 980 }}
      columns={[
        { title: '标题', dataIndex: 'title', width: 240, render: (value, record) => <Space orientation="vertical" size={0}><Typography.Text strong>{value}</Typography.Text>{record.description && <Typography.Text type="secondary" ellipsis style={{ maxWidth: 280 }}>{markdownSummary(record.description)}</Typography.Text>}</Space> },
        { title: '状态', dataIndex: 'status', width: 95, render: (value) => <Tag>{STATUS_LABEL[value] || value}</Tag> },
        ...(kind === 'risk' ? [{ title: '等级', dataIndex: 'severity', width: 75, render: (value: string) => { const level = SEVERITY.find((item) => item.value === value); return <Tag color={level?.color}>{level?.label || value}</Tag> } }] : []),
        { title: '负责人', dataIndex: 'owner_name', width: 110, render: (value, record) => value || members.find((m) => m.user_id === record.owner_id)?.name || '未指定' },
        { title: '关联与证据', key: 'refs', width: 245, render: (_, record) => {
          const task = items.find((item) => item.id === record.work_item_id)
          return <Space wrap size={[4, 4]}>
            {record.work_item_id && <Tag>任务 · {record.work_item_title || task?.title || record.work_item_id.slice(0, 8)}</Tag>}
            {task?.delivery_accepted && record.status !== 'closed' && <Tag color="success">处置已验收，可关闭</Tag>}
            {record.milestone_id && <Tag>里程碑 · {record.milestone_name || milestones.find((m) => m.id === record.milestone_id)?.name || record.milestone_id.slice(0, 8)}</Tag>}
            {(record.run_id || record.artifact_id) && <Tag color="blue">执行证据</Tag>}
          </Space>
        } },
        { title: '操作', key: 'actions', fixed: 'right', width: 270, render: (_, record) => {
          const task = items.find((item) => item.id === record.work_item_id)
          return canWrite ? <Space wrap size={2}>
            {record.record_type === 'risk' && record.status !== 'closed' && !record.work_item_id && <Button type="link" size="small" onClick={() => showActionTask(record)}>创建处置任务</Button>}
            {record.record_type === 'risk' && record.status !== 'closed' && task?.delivery_accepted && <Button type="link" size="small" onClick={() => showClose(record)}>确认关闭</Button>}
            <Button type="link" size="small" onClick={() => showEdit(record)}>编辑</Button>
            <Popconfirm title="确认删除这条治理记录？" onConfirm={() => void remove(record.id)}><Button type="link" danger size="small">删除</Button></Popconfirm>
          </Space> : null
        } },
      ]}
    /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={kind === 'risk' ? '暂无风险记录' : '暂无决策记录'} />}

    <Modal width={watchedType === 'risk' ? 920 : 620} open={open} title={editing ? `编辑${kind === 'risk' ? '风险' : '决策'}` : `新建${kind === 'risk' ? '风险' : '决策'}`} onCancel={() => setOpen(false)} onOk={() => void save()} confirmLoading={saving} destroyOnHidden forceRender afterOpenChange={(visible) => {
      if (visible) form.setFieldsValue(editing || initialDraft(kind))
    }}>
      <Form form={form} layout="vertical" preserve={false} onValuesChange={(changed) => {
        if (changed.record_type) {
          const nextType = changed.record_type as GovernanceRecordType
          form.setFieldsValue({
            status: nextType === 'risk' ? 'open' : 'proposed', severity: nextType === 'risk' ? 'medium' : '',
            description: nextType === 'risk' && !form.getFieldValue('description') ? RISK_DESCRIPTION_TEMPLATE : form.getFieldValue('description'),
          })
        }
      }}>
        <Form.Item name="record_type" label="类型" rules={[{ required: true }]}><Select disabled={!!editing} options={[{ value: 'risk', label: '风险' }, { value: 'decision', label: '决策' }]} /></Form.Item>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true, max: 300 }]}><Input /></Form.Item>
        {watchedType === 'risk'
          ? <Form.Item name="description" label="说明" rules={[{ max: 20000 }]}><MarkdownEditor ariaLabel="风险说明 Markdown 编辑器" placeholder="按触发条件、潜在影响、影响范围和关闭条件描述风险…" /></Form.Item>
          : <Form.Item name="description" label="说明" rules={[{ max: 20000 }]}><Input.TextArea rows={4} maxLength={20000} /></Form.Item>}
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}><Select style={{ width: 150 }} options={STATUS[watchedType]} /></Form.Item>
          {watchedType === 'risk' && <Form.Item name="severity" label="风险等级" rules={[{ required: true }]}><Select style={{ width: 130 }} options={SEVERITY} /></Form.Item>}
          <Form.Item name="owner_id" label="负责人"><Select allowClear style={{ width: 160 }} options={members.map((m) => ({ value: m.user_id, label: m.name }))} /></Form.Item>
        </Space>
        {watchedType === 'risk'
          ? <Form.Item name="response" label="应对措施" rules={watchedStatus === 'closed' ? [{ required: true, whitespace: true, message: '关闭风险前必须填写应对措施' }] : []}><Input.TextArea rows={3} /></Form.Item>
          : <Form.Item name="rationale" label="决策依据"><Input.TextArea rows={3} /></Form.Item>}
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="work_item_id" label="关联任务"><Select allowClear showSearch optionFilterProp="label" style={{ width: 260 }} options={items.map((item) => ({ value: item.id, label: item.title }))} /></Form.Item>
          <Form.Item name="milestone_id" label="关联里程碑"><Select allowClear style={{ width: 220 }} options={milestones.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
        </Space>
        {watchedType === 'risk' && watchedStatus === 'closed' && <Alert type="info" showIcon style={{ marginBottom: 16 }} title="关闭门禁" description="关联处置任务必须已通过真实交付验收；请补充残余风险结论。验收 Run 会由 Server 自动绑定。" />}
        <Form.Item name="evidence_label" label={watchedType === 'risk' && watchedStatus === 'closed' ? '残余风险结论与证据说明' : '执行证据说明'} rules={watchedType === 'risk' && watchedStatus === 'closed' ? [{ required: true, whitespace: true, message: '请填写残余风险结论与证据说明' }] : []}>
          <Input.TextArea rows={2} placeholder={watchedType === 'risk' && watchedStatus === 'closed' ? '例如：处置验证通过；残余风险为低，继续由现有监控覆盖。' : '例如：回归验证通过，详见本次运行'} maxLength={500} />
        </Form.Item>
        <Space align="start" wrap style={{ width: '100%' }}>
          <Form.Item name="run_id" label="运行 ID"><Input style={{ width: 260 }} /></Form.Item>
          <Form.Item name="artifact_id" label="产物 ID"><Input style={{ width: 260 }} /></Form.Item>
        </Space>
      </Form>
    </Modal>

    <Modal width={640} open={actionOpen} title="创建风险处置任务" okText="创建并关联" onCancel={() => { setActionOpen(false); setActionRisk(null) }} onOk={() => void createActionTask()} confirmLoading={actionSaving} destroyOnHidden forceRender>
      {actionRisk && <Alert type="info" showIcon style={{ marginBottom: 16 }} title={`来源风险：${actionRisk.title}`} description={<Space wrap><Tag color={SEVERITY.find((item) => item.value === actionRisk.severity)?.color}>{SEVERITY.find((item) => item.value === actionRisk.severity)?.label}</Tag><span>任务优先级将映射为“{PRIORITY_LABEL[actionRisk.severity as RiskSeverity]}”</span><span>负责人和里程碑自动继承，可在任务中继续调整。</span></Space>} />}
      <Form form={actionForm} layout="vertical" preserve={false}>
        <Form.Item name="title" label="任务标题" rules={[{ required: true, whitespace: true, max: 300 }]}><Input /></Form.Item>
        <Form.Item name="due_date" label="截止日期" rules={[{ pattern: /^$|^\d{4}-\d{2}-\d{2}$/, message: '请输入 YYYY-MM-DD' }]}><Input type="date" /></Form.Item>
        <Form.Item name="acceptance_criteria" label="验收标准" rules={[{ required: true, whitespace: true, max: 10000 }]}><Input.TextArea rows={7} /></Form.Item>
      </Form>
    </Modal>
  </div>
}
