import { Button, Empty, Input, Popover, Tooltip } from 'antd'
import { DownOutlined, SearchOutlined } from '@ant-design/icons'
import { useMemo, useState } from 'react'

export type IconPickerOption = {
  value: string
  glyph: string
  label: string
  category: string
  keywords?: string
}

export const DEFAULT_ICON_OPTIONS: readonly IconPickerOption[] = [
  { value: '🤖', glyph: '🤖', label: '机器人', category: '角色', keywords: 'assistant bot ai 助理' },
  { value: '🧑', glyph: '🧑', label: '专家', category: '角色', keywords: 'person expert 人物' },
  { value: '👩‍💼', glyph: '👩‍💼', label: '商务顾问', category: '角色', keywords: 'business manager 商务 管理' },
  { value: '👨‍💻', glyph: '👨‍💻', label: '开发工程师', category: '角色', keywords: 'developer code 开发 编程' },
  { value: '🧠', glyph: '🧠', label: '智能分析', category: '角色', keywords: 'brain thinking ai 智能 推理' },
  { value: '🧭', glyph: '🧭', label: '策略导航', category: '角色', keywords: 'strategy compass 策略 导航' },
  { value: '🛡️', glyph: '🛡️', label: '安全专家', category: '角色', keywords: 'security shield 安全' },
  { value: '🎨', glyph: '🎨', label: '创意设计', category: '角色', keywords: 'design creative 设计 创意' },
  { value: '📚', glyph: '📚', label: '知识库', category: '办公', keywords: 'books knowledge 知识 文档' },
  { value: '📄', glyph: '📄', label: '文档', category: '办公', keywords: 'document file 文件' },
  { value: '📝', glyph: '📝', label: '写作', category: '办公', keywords: 'write note 编辑 笔记' },
  { value: '📊', glyph: '📊', label: '数据分析', category: '办公', keywords: 'chart analytics 数据 图表' },
  { value: '📈', glyph: '📈', label: '增长趋势', category: '办公', keywords: 'growth trend 增长 趋势' },
  { value: '💼', glyph: '💼', label: '商务', category: '办公', keywords: 'briefcase work 工作' },
  { value: '🗂️', glyph: '🗂️', label: '资料归档', category: '办公', keywords: 'archive folder 归档 资料' },
  { value: '🗓️', glyph: '🗓️', label: '计划日程', category: '办公', keywords: 'calendar schedule 日程 计划' },
  { value: '🧩', glyph: '🧩', label: '技能组件', category: '技术', keywords: 'skill plugin component 技能 插件' },
  { value: '🛠️', glyph: '🛠️', label: '工程工具', category: '技术', keywords: 'tools engineering 工程 工具' },
  { value: '🔧', glyph: '🔧', label: '配置工具', category: '技术', keywords: 'wrench config 配置 工具' },
  { value: '⚙️', glyph: '⚙️', label: '系统设置', category: '技术', keywords: 'settings system 系统 设置' },
  { value: '💻', glyph: '💻', label: '软件开发', category: '技术', keywords: 'computer software 代码 软件' },
  { value: '🖥️', glyph: '🖥️', label: '控制台', category: '技术', keywords: 'console desktop 控制台 桌面' },
  { value: '🔌', glyph: '🔌', label: '连接器', category: '技术', keywords: 'connector plug 连接器 接口' },
  { value: '🔬', glyph: '🔬', label: '研究实验', category: '技术', keywords: 'research science 研究 实验' },
  { value: '💬', glyph: '💬', label: '对话沟通', category: '协作', keywords: 'chat message 对话 消息' },
  { value: '📣', glyph: '📣', label: '公告推广', category: '协作', keywords: 'announce marketing 公告 推广' },
  { value: '✉️', glyph: '✉️', label: '邮件', category: '协作', keywords: 'email mail 邮件' },
  { value: '🔔', glyph: '🔔', label: '通知提醒', category: '协作', keywords: 'notification alert 通知 提醒' },
  { value: '🤝', glyph: '🤝', label: '团队协作', category: '协作', keywords: 'team collaborate 团队 协作' },
  { value: '🎯', glyph: '🎯', label: '目标', category: '协作', keywords: 'target goal 目标' },
  { value: '✨', glyph: '✨', label: '推荐精选', category: '协作', keywords: 'sparkle featured 推荐 精选' },
  { value: '🚀', glyph: '🚀', label: '发布启动', category: '协作', keywords: 'launch release 发布 启动' },
  { value: '🏠', glyph: '🏠', label: '家庭空间', category: '通用', keywords: 'home house 家庭 空间' },
  { value: '🏢', glyph: '🏢', label: '企业组织', category: '通用', keywords: 'company organization 企业 组织' },
  { value: '🏷️', glyph: '🏷️', label: '标签分类', category: '通用', keywords: 'tag category 标签 分类' },
  { value: '🔖', glyph: '🔖', label: '书签资料', category: '通用', keywords: 'bookmark 书签 资料' },
  { value: '❓', glyph: '❓', label: '问答帮助', category: '通用', keywords: 'question help 问答 帮助' },
  { value: '💡', glyph: '💡', label: '灵感创意', category: '通用', keywords: 'idea insight 灵感 创意' },
  { value: '⚖️', glyph: '⚖️', label: '法律合规', category: '通用', keywords: 'legal compliance 法律 合规' },
  { value: '🔐', glyph: '🔐', label: '权限隐私', category: '通用', keywords: 'lock privacy 权限 隐私' },
]

export function IconPicker({
  value,
  onChange,
  options = DEFAULT_ICON_OPTIONS,
  compact = false,
  disabled = false,
  ariaLabel = '选择图标',
}: {
  value?: string
  onChange?: (value: string) => void
  options?: readonly IconPickerOption[]
  compact?: boolean
  disabled?: boolean
  ariaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const selected = options.find((option) => option.value === value)
  const currentGlyph = selected?.glyph || value || '✨'
  const currentLabel = selected?.label || (value ? '当前图标' : '选择图标')
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase()
    if (!needle) return options
    return options.filter((option) => `${option.label} ${option.category} ${option.keywords || ''} ${option.value}`.toLocaleLowerCase().includes(needle))
  }, [options, query])
  const groups = useMemo(() => {
    const result = new Map<string, IconPickerOption[]>()
    filtered.forEach((option) => result.set(option.category, [...(result.get(option.category) || []), option]))
    return [...result.entries()]
  }, [filtered])
  const choose = (next: string) => {
    onChange?.(next)
    setOpen(false)
    setQuery('')
  }
  const content = (
    <div className="icon-picker-panel" aria-label="图标选项">
      <Input
        allowClear
        autoFocus
        prefix={<SearchOutlined />}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onPressEnter={() => { if (filtered.length === 1) choose(filtered[0].value) }}
        placeholder="搜索图标名称"
        aria-label="搜索图标"
      />
      <div className="icon-picker-scroll">
        {groups.map(([category, items]) => (
          <section className="icon-picker-group" key={category} aria-label={category}>
            <div className="icon-picker-group-title">{category}</div>
            <div className="icon-picker-grid">
              {items.map((option) => (
                <Tooltip title={option.label} key={option.value} mouseEnterDelay={0.35}>
                  <Button
                    type="text"
                    htmlType="button"
                    className={`icon-picker-option ${value === option.value ? 'selected' : ''}`.trim()}
                    aria-label={option.label}
                    aria-pressed={value === option.value}
                    onClick={() => choose(option.value)}
                  >
                    {option.glyph}
                  </Button>
                </Tooltip>
              ))}
            </div>
          </section>
        ))}
        {filtered.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配的图标" />}
      </div>
    </div>
  )

  return (
    <Popover
      content={content}
      title="选择图标"
      trigger="click"
      placement="bottomLeft"
      open={open}
      onOpenChange={(next) => { setOpen(next); if (!next) setQuery('') }}
      destroyOnHidden
      classNames={{ root: 'icon-picker-popover' }}
    >
      <Button
        htmlType="button"
        disabled={disabled}
        className={`icon-picker-trigger ${compact ? 'compact' : ''}`.trim()}
        aria-label={`${ariaLabel}，当前：${currentLabel}`}
      >
        <span className="icon-picker-current" aria-hidden>{currentGlyph}</span>
        {!compact && <span className="icon-picker-label">{currentLabel}</span>}
        <DownOutlined className="icon-picker-chevron" />
      </Button>
    </Popover>
  )
}
