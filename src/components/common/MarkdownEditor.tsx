import { BoldOutlined, CheckSquareOutlined, ItalicOutlined, LinkOutlined, UnorderedListOutlined } from '@ant-design/icons'
import { Button, Empty, Input, Segmented, Space, Tooltip, Typography } from 'antd'
import type { TextAreaRef } from 'antd/es/input/TextArea'
import type { KeyboardEvent } from 'react'
import { useMemo, useRef, useState } from 'react'
import { renderMarkdown } from '../../lib/markdown'

type EditorMode = 'write' | 'split' | 'preview'

export function MarkdownEditor({
  value = '', onChange, disabled, placeholder = '使用 Markdown 编写…', ariaLabel = 'Markdown 编辑器',
}: {
  value?: string
  onChange?: (value: string) => void
  disabled?: boolean
  placeholder?: string
  ariaLabel?: string
}) {
  const [mode, setMode] = useState<EditorMode>('write')
  const inputRef = useRef<TextAreaRef>(null)
  const preview = useMemo(() => renderMarkdown(value), [value])
  const formattingDisabled = disabled || mode === 'preview'

  const replaceSelection = (prefix: string, suffix = '', fallback = '文本') => {
    if (disabled) return
    const textarea = inputRef.current?.resizableTextArea?.textArea
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const selected = value.slice(start, end) || fallback
    const replacement = `${prefix}${selected}${suffix}`
    onChange?.(`${value.slice(0, start)}${replacement}${value.slice(end)}`)
    requestAnimationFrame(() => {
      textarea.focus()
      textarea.setSelectionRange(start + prefix.length, start + prefix.length + selected.length)
    })
  }

  const prefixLines = (prefix: string) => {
    if (disabled) return
    const textarea = inputRef.current?.resizableTextArea?.textArea
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const lineStart = value.lastIndexOf('\n', Math.max(0, start - 1)) + 1
    const nextBreak = value.indexOf('\n', end)
    const lineEnd = nextBreak < 0 ? value.length : nextBreak
    const selected = value.slice(lineStart, lineEnd) || '内容'
    const replacement = selected.split(/\r?\n/).map((line) => `${prefix}${line}`).join('\n')
    onChange?.(`${value.slice(0, lineStart)}${replacement}${value.slice(lineEnd)}`)
    requestAnimationFrame(() => {
      textarea.focus()
      textarea.setSelectionRange(lineStart, lineStart + replacement.length)
    })
  }

  const handleShortcut = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (!(event.ctrlKey || event.metaKey)) return
    const key = event.key.toLowerCase()
    if (key === 'b') { event.preventDefault(); replaceSelection('**', '**') }
    else if (key === 'i') { event.preventDefault(); replaceSelection('_', '_') }
    else if (key === 'k') { event.preventDefault(); replaceSelection('[', '](https://)', '链接文字') }
  }

  const editor = <Input.TextArea
    ref={inputRef} className="wb-markdown-editor-input" value={value} disabled={disabled}
    placeholder={placeholder} autoSize={{ minRows: 10 }} onChange={(event) => onChange?.(event.target.value)}
    onKeyDown={handleShortcut} aria-label={ariaLabel}
  />
  const rendered = <div className="wb-markdown-editor-preview" aria-label={`${ariaLabel}预览`}>
    {value.trim() ? <div className="wb-markdown-editor-preview-content" dangerouslySetInnerHTML={{ __html: preview }} />
      : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="输入内容后可在此预览" />}
  </div>

  return <div className="wb-markdown-editor">
    <div className="wb-markdown-editor-toolbar">
      <Space size={2} wrap>
        <Tooltip title="二级标题"><Button type="text" size="small" disabled={formattingDisabled} onClick={() => prefixLines('## ')}>H2</Button></Tooltip>
        <Tooltip title="粗体（Ctrl/⌘ + B）"><Button type="text" size="small" icon={<BoldOutlined />} aria-label="粗体" disabled={formattingDisabled} onClick={() => replaceSelection('**', '**')} /></Tooltip>
        <Tooltip title="斜体（Ctrl/⌘ + I）"><Button type="text" size="small" icon={<ItalicOutlined />} aria-label="斜体" disabled={formattingDisabled} onClick={() => replaceSelection('_', '_')} /></Tooltip>
        <Tooltip title="无序列表"><Button type="text" size="small" icon={<UnorderedListOutlined />} aria-label="无序列表" disabled={formattingDisabled} onClick={() => prefixLines('- ')} /></Tooltip>
        <Tooltip title="任务清单"><Button type="text" size="small" icon={<CheckSquareOutlined />} aria-label="任务清单" disabled={formattingDisabled} onClick={() => prefixLines('- [ ] ')} /></Tooltip>
        <Tooltip title="链接（Ctrl/⌘ + K）"><Button type="text" size="small" icon={<LinkOutlined />} aria-label="链接" disabled={formattingDisabled} onClick={() => replaceSelection('[', '](https://)', '链接文字')} /></Tooltip>
      </Space>
      <Segmented<EditorMode> size="small" value={mode} onChange={setMode} options={[
        { value: 'write', label: '编辑' }, { value: 'split', label: '分栏' }, { value: 'preview', label: '预览' },
      ]} />
    </div>
    <div className={`wb-markdown-editor-body is-${mode}`}>
      {mode !== 'preview' && editor}
      {mode !== 'write' && rendered}
    </div>
    <div className="wb-markdown-editor-footer">
      <Typography.Text type="secondary">支持 Markdown · Ctrl/⌘ + B / I / K</Typography.Text>
      <Typography.Text type="secondary">{value.length} 字符 · {value ? value.split(/\r?\n/).length : 0} 行</Typography.Text>
    </div>
  </div>
}
