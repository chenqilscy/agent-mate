import { useCallback, useEffect, useState } from 'react'
import { Alert, Empty, Form, Input, Modal, Select, Space, Tag } from 'antd'
import { api } from '../../lib/api'
import {
  decisionDescriptionForWorkItem,
  riskDescriptionForWorkItem,
  riskSeverityForWorkItem,
} from '../../lib/governance'
import type { GovernanceRecordType, ProjectGovernanceRecord, RiskSeverity, WorkItem } from '../../lib/types'
import { toast } from '../../stores/toastStore'
import { MarkdownEditor } from '../common/MarkdownEditor'
import { WbButton } from '../ui/Primitives'

const SEVERITY_OPTIONS: Array<{ value: RiskSeverity; label: string }> = [
  { value: 'low', label: '低' },
  { value: 'medium', label: '中' },
  { value: 'high', label: '高' },
  { value: 'critical', label: '严重' },
]

const STATUS_LABEL: Record<string, string> = {
  open: '待处理', mitigating: '应对中', closed: '已关闭',
  proposed: '待决策', accepted: '已采纳', superseded: '已替代',
}

type GovernanceDraft = {
  title: string
  description: string
  severity: RiskSeverity
  response: string
  rationale: string
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message ? error.message : '治理记录创建失败'
}

export function TaskGovernanceSection({
  projectId, item, canWrite,
}: {
  projectId: string
  item: WorkItem
  canWrite: boolean
}) {
  const [records, setRecords] = useState<ProjectGovernanceRecord[]>([])
  const [kind, setKind] = useState<GovernanceRecordType>('risk')
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<GovernanceDraft>()

  const load = useCallback(async () => {
    try {
      const result = await api.listProjectGovernance(projectId)
      setRecords(result.records.filter((record) => record.work_item_id === item.id))
    } catch {
      setRecords([])
    }
  }, [item.id, projectId])

  useEffect(() => { void load() }, [load])

  const showCreate = (recordType: GovernanceRecordType) => {
    setKind(recordType)
    form.setFieldsValue({
      title: `${recordType === 'risk' ? '任务风险' : '任务决策'}：${item.title}`.slice(0, 300),
      description: recordType === 'risk' ? riskDescriptionForWorkItem(item) : decisionDescriptionForWorkItem(item),
      severity: riskSeverityForWorkItem(item.priority),
      response: '',
      rationale: '',
    })
    setOpen(true)
  }

  const create = async () => {
    let values: GovernanceDraft
    try { values = await form.validateFields() } catch { return }
    setSaving(true)
    try {
      await api.createProjectGovernance({
        project_id: projectId,
        record_type: kind,
        title: values.title.trim(),
        description: values.description || '',
        status: kind === 'risk' ? 'open' : 'proposed',
        severity: kind === 'risk' ? values.severity : '',
        owner_id: item.assignee || '',
        response: kind === 'risk' ? values.response || '' : '',
        rationale: kind === 'decision' ? values.rationale || '' : '',
        work_item_id: item.id,
        milestone_id: item.milestone_id || '',
      })
      setOpen(false)
      form.resetFields()
      await load()
      toast(kind === 'risk' ? '风险已创建并关联当前任务' : '决策已创建并关联当前任务')
    } catch (error) {
      toast(errorMessage(error))
    } finally {
      setSaving(false)
    }
  }

  return <>
    <div className="wb-td-sec-h wb-td-governance-head">
      <span>治理关联{records.length ? ` ${records.length}` : ''}</span>
      {canWrite && <Space size={2} wrap>
        <WbButton className="wb-td-editlink" onClick={() => showCreate('risk')}>＋ 创建风险</WbButton>
        <WbButton className="wb-td-editlink" onClick={() => showCreate('decision')}>＋ 创建决策</WbButton>
      </Space>}
    </div>
    {records.length ? <div className="wb-td-governance-list">
      {records.map((record) => <div className="wb-td-governance-row" key={record.id}>
        <Tag color={record.record_type === 'risk' ? 'orange' : 'blue'}>{record.record_type === 'risk' ? '风险' : '决策'}</Tag>
        <span className="wb-td-governance-title" title={record.title}>{record.title}</span>
        <Tag>{STATUS_LABEL[record.status] || record.status}</Tag>
      </div>)}
    </div> : <Empty className="pj-empty wb-td-governance-empty" image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前任务尚未关联风险或决策" />}

    <Modal
      width={kind === 'risk' ? 840 : 620}
      open={open}
      title={kind === 'risk' ? '从任务创建风险' : '从任务创建决策'}
      okText="创建并关联"
      onCancel={() => setOpen(false)}
      onOk={() => void create()}
      confirmLoading={saving}
      destroyOnHidden
      forceRender
    >
      <Alert
        type="info"
        showIcon
        title={`关联任务：${item.title}`}
        description={<Space wrap>
          {item.assignee_name && <Tag>负责人 · {item.assignee_name}</Tag>}
          {item.milestone_id && <Tag>继承任务里程碑</Tag>}
          {kind === 'risk' && <Tag>等级由任务优先级预填，可调整</Tag>}
        </Space>}
        style={{ marginBottom: 16 }}
      />
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item name="title" label="标题" rules={[{ required: true, whitespace: true, max: 300 }]}><Input /></Form.Item>
        {kind === 'risk' ? <>
          <Form.Item name="description" label="说明" rules={[{ max: 20000 }]}>
            <MarkdownEditor ariaLabel="任务关联风险说明 Markdown 编辑器" />
          </Form.Item>
          <Form.Item name="severity" label="风险等级" rules={[{ required: true }]}><Select options={SEVERITY_OPTIONS} /></Form.Item>
          <Form.Item name="response" label="应对措施" rules={[{ max: 20000 }]}><Input.TextArea rows={3} /></Form.Item>
        </> : <>
          <Form.Item name="description" label="说明" rules={[{ max: 20000 }]}><Input.TextArea rows={7} /></Form.Item>
          <Form.Item name="rationale" label="决策依据" rules={[{ max: 20000 }]}><Input.TextArea rows={4} /></Form.Item>
        </>}
      </Form>
    </Modal>
  </>
}
