import {
  BoldOutlined,
  CheckSquareOutlined,
  CodeOutlined,
  DownOutlined,
  ItalicOutlined,
  LinkOutlined,
  OrderedListOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import {
  Button,
  Dropdown,
  Empty,
  Input,
  Segmented,
  Space,
  Tooltip,
  Typography,
} from "antd";
import type { TextAreaRef } from "antd/es/input/TextArea";
import DOMPurify from "dompurify";
import { marked } from "marked";
import type { KeyboardEvent } from "react";
import { useMemo, useRef, useState } from "react";

type EditorMode = "write" | "split" | "preview";

const STRUCTURES = {
  general: `## 背景

说明为什么需要处理这项任务。

## 目标

说明完成后应达到的结果。

## 实施要点

- 补充实施要点

## 验收标准

- [ ] 补充验收标准
`,
  defect: `## 问题现象

描述实际发生的行为。

## 复现步骤

1. 补充复现步骤

## 期望结果

描述正确行为。

## 验收标准

- [ ] 问题无法再复现
- [ ] 相关路径无回归
`,
  research: `## 研究问题

需要回答的核心问题。

## 已知信息

- 补充已知信息

## 调研过程

1. 补充调研过程

## 结论与建议

`,
} as const;

function renderTaskMarkdown(value: string): string {
  return DOMPurify.sanitize(
    marked.parse(value, { async: false, gfm: true, breaks: false }) as string,
  );
}

export function MarkdownEditor({
  value = "",
  onChange,
  disabled,
  placeholder = "使用 Markdown 编写任务背景、目标、实施步骤和验收标准…",
}: {
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}) {
  const [mode, setMode] = useState<EditorMode>("write");
  const inputRef = useRef<TextAreaRef>(null);
  const preview = useMemo(() => renderTaskMarkdown(value), [value]);
  const lineCount = value ? value.split(/\r?\n/).length : 0;
  const formattingDisabled = disabled || mode === "preview";

  function replaceSelection(
    prefix: string,
    suffix = "",
    fallback = "文本",
  ) {
    if (disabled) return;
    const textarea = inputRef.current?.resizableTextArea?.textArea;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = value.slice(start, end) || fallback;
    const replacement = `${prefix}${selected}${suffix}`;
    onChange?.(`${value.slice(0, start)}${replacement}${value.slice(end)}`);
    requestAnimationFrame(() => {
      textarea.focus();
      const selectionStart = start + prefix.length;
      textarea.setSelectionRange(
        selectionStart,
        selectionStart + selected.length,
      );
    });
  }

  function prefixLines(prefix: string) {
    if (disabled) return;
    const textarea = inputRef.current?.resizableTextArea?.textArea;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    const nextBreak = value.indexOf("\n", end);
    const lineEnd = nextBreak < 0 ? value.length : nextBreak;
    const selected = value.slice(lineStart, lineEnd) || "内容";
    const replacement = selected
      .split(/\r?\n/)
      .map((line) => `${prefix}${line}`)
      .join("\n");
    onChange?.(
      `${value.slice(0, lineStart)}${replacement}${value.slice(lineEnd)}`,
    );
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(lineStart, lineStart + replacement.length);
    });
  }

  function insertStructure(content: string) {
    if (disabled) return;
    const textarea = inputRef.current?.resizableTextArea?.textArea;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const separator = value && !value.endsWith("\n\n") ? "\n\n" : "";
    const insertion = `${separator}${content}`;
    onChange?.(`${value.slice(0, start)}${insertion}${value.slice(end)}`);
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(
        start + insertion.length,
        start + insertion.length,
      );
    });
  }

  function handleShortcut(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!(event.ctrlKey || event.metaKey)) return;
    const key = event.key.toLowerCase();
    if (key === "b") {
      event.preventDefault();
      replaceSelection("**", "**");
    } else if (key === "i") {
      event.preventDefault();
      replaceSelection("_", "_");
    } else if (key === "k") {
      event.preventDefault();
      replaceSelection("[", "](https://)", "链接文字");
    }
  }

  const editor = (
    <Input.TextArea
      ref={inputRef}
      className="markdown-editor-input"
      value={value}
      disabled={disabled}
      placeholder={placeholder}
      autoSize={{ minRows: 14 }}
      onChange={(event) => onChange?.(event.target.value)}
      onKeyDown={handleShortcut}
      aria-label="任务描述 Markdown 编辑器"
    />
  );
  const rendered = (
    <div className="markdown-editor-preview" aria-label="任务描述预览">
      {value.trim() ? (
        <div
          className="markdown-editor-preview-content"
          // Markdown 预览必须经过 DOMPurify 安全清洗。
          dangerouslySetInnerHTML={{ __html: preview }}
        />
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="输入内容后可在此预览"
        />
      )}
    </div>
  );

  return (
    <div className="markdown-editor">
      <div className="markdown-editor-toolbar">
        <Space size={2} wrap>
          <Tooltip title="二级标题">
            <Button
              type="text"
              size="small"
              disabled={formattingDisabled}
              onClick={() => prefixLines("## ")}
            >
              H2
            </Button>
          </Tooltip>
          <Tooltip title="粗体（Ctrl/⌘ + B）">
            <Button
              type="text"
              size="small"
              icon={<BoldOutlined />}
              aria-label="粗体"
              disabled={formattingDisabled}
              onClick={() => replaceSelection("**", "**")}
            />
          </Tooltip>
          <Tooltip title="斜体（Ctrl/⌘ + I）">
            <Button
              type="text"
              size="small"
              icon={<ItalicOutlined />}
              aria-label="斜体"
              disabled={formattingDisabled}
              onClick={() => replaceSelection("_", "_")}
            />
          </Tooltip>
          <Tooltip title="无序列表">
            <Button
              type="text"
              size="small"
              icon={<UnorderedListOutlined />}
              aria-label="无序列表"
              disabled={formattingDisabled}
              onClick={() => prefixLines("- ")}
            />
          </Tooltip>
          <Tooltip title="有序列表">
            <Button
              type="text"
              size="small"
              icon={<OrderedListOutlined />}
              aria-label="有序列表"
              disabled={formattingDisabled}
              onClick={() => prefixLines("1. ")}
            />
          </Tooltip>
          <Tooltip title="任务清单">
            <Button
              type="text"
              size="small"
              icon={<CheckSquareOutlined />}
              aria-label="任务清单"
              disabled={formattingDisabled}
              onClick={() => prefixLines("- [ ] ")}
            />
          </Tooltip>
          <Tooltip title="引用">
            <Button
              type="text"
              size="small"
              aria-label="引用"
              disabled={formattingDisabled}
              onClick={() => prefixLines("> ")}
            >
              ❝
            </Button>
          </Tooltip>
          <Tooltip title="行内代码">
            <Button
              type="text"
              size="small"
              icon={<CodeOutlined />}
              aria-label="行内代码"
              disabled={formattingDisabled}
              onClick={() => replaceSelection("`", "`", "code")}
            />
          </Tooltip>
          <Tooltip title="链接（Ctrl/⌘ + K）">
            <Button
              type="text"
              size="small"
              icon={<LinkOutlined />}
              aria-label="链接"
              disabled={formattingDisabled}
              onClick={() =>
                replaceSelection("[", "](https://)", "链接文字")
              }
            />
          </Tooltip>
          <Dropdown
            disabled={formattingDisabled}
            menu={{
              items: [
                { key: "general", label: "通用任务结构" },
                { key: "defect", label: "缺陷修复结构" },
                { key: "research", label: "调研任务结构" },
              ],
              onClick: ({ key }) =>
                insertStructure(STRUCTURES[key as keyof typeof STRUCTURES]),
            }}
          >
            <Button type="text" size="small" icon={<DownOutlined />}>
              插入结构
            </Button>
          </Dropdown>
        </Space>
        <Segmented<EditorMode>
          size="small"
          value={mode}
          onChange={setMode}
          options={[
            { value: "write", label: "编辑" },
            { value: "split", label: "分栏" },
            { value: "preview", label: "预览" },
          ]}
        />
      </div>
      <div className={`markdown-editor-body is-${mode}`}>
        {mode !== "preview" && editor}
        {mode !== "write" && rendered}
      </div>
      <div className="markdown-editor-footer">
        <Typography.Text type="secondary">
          支持 Markdown · Ctrl/⌘ + B / I / K
        </Typography.Text>
        <Typography.Text type="secondary">
          {value.length} 字符 · {lineCount} 行
        </Typography.Text>
      </div>
    </div>
  );
}
