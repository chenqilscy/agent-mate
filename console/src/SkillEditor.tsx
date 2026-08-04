import {
  App,
  Alert,
  Button,
  Checkbox,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Row,
  Segmented,
  Select,
  Space,
  Tag,
  Typography,
} from "antd";
import { CompatList as List } from "./components/CompatList";
import { IconPicker } from "../../src/components/ui/IconPicker";
import {
  DeleteOutlined,
  FileAddOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { consoleApi } from "./api";
import type { CatalogItem, SkillCategoryData, SkillData, SkillFile, SkillTool } from "./types";

interface SkillFormValues {
  slug: string;
  name: string;
  icon: string;
  category_slug: string;
  description: string;
  tools: string[];
  min_app_version: string;
  sort: number;
}

interface SkillEditorProps {
  open: boolean;
  item: CatalogItem<SkillData> | null;
  tools: SkillTool[];
  categories: CatalogItem<SkillCategoryData>[];
  initialTab: "info" | "files" | "tools";
  onClose: () => void;
  onSaved: () => void;
}

const RESERVED_FILES = new Set(["skill.md", "_skillhub_meta.json", "_meta.json", "_agentmate_release.json", ".disabled"]);
const MANAGED_FRONTMATTER_KEYS = new Set(["name", "slug", "description", "version", "source"]);

interface SkillMarkdownDocument {
  frontmatter: Record<string, string>;
  frontmatterRaw: string;
  body: string;
}

function normalizePath(value: string): string {
  return value.replace(/\\/g, "/").trim();
}

function buildSkillMarkdown(
  values: Partial<SkillFormValues>,
  version: number,
  existing?: SkillMarkdownDocument | null,
  fallbackBody = "",
): string {
  const preserved = existing ? preserveUnmanagedFrontmatter(existing.frontmatterRaw) : "";
  const body = existing?.body ?? fallbackBody;
  const extra = preserved ? `${preserved}\n` : "";
  const markdown = `---\nname: ${JSON.stringify(values.name || "")}\nslug: ${values.slug || ""}\ndescription: ${JSON.stringify(values.description || "")}\nversion: ${JSON.stringify(String(version || 1))}\nsource: agentmate\n${extra}---\n\n${body}`;
  return body && !body.endsWith("\n") ? `${markdown}\n` : markdown;
}

function parseFrontmatterValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    return typeof parsed === "string" ? parsed : String(parsed);
  } catch {
    return trimmed.replace(/^['"]|['"]$/g, "");
  }
}

function preserveUnmanagedFrontmatter(raw: string): string {
  const lines = raw.split(/\r?\n/);
  const kept: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^([A-Za-z0-9_-]+):[ \t]*(.*)$/);
    if (!match || !MANAGED_FRONTMATTER_KEYS.has(match[1])) {
      kept.push(lines[index]);
      continue;
    }
    const value = match[2].trim();
    if (!value || /^[|>][0-9+-]*$/.test(value)) {
      while (index + 1 < lines.length && (!lines[index + 1].trim() || /^[ \t]/.test(lines[index + 1]))) index += 1;
    }
  }
  return kept.join("\n").trim();
}

function parseSkillMarkdown(markdown: string): SkillMarkdownDocument | null {
  const match = markdown.replace(/^\uFEFF/, "").match(/^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)([\s\S]*)$/);
  if (!match) return null;
  const frontmatter: Record<string, string> = {};
  const lines = match[1].split(/\r?\n/);
  for (let index = 0; index < lines.length; index += 1) {
    const parsed = lines[index].match(/^([A-Za-z0-9_-]+):[ \t]*(.*)$/);
    if (!parsed) continue;
    const [, key, rawValue] = parsed;
    const value = rawValue.trim();
    if (/^[|>][0-9+-]*$/.test(value)) {
      const continuation: string[] = [];
      while (index + 1 < lines.length && (!lines[index + 1].trim() || /^[ \t]/.test(lines[index + 1]))) {
        index += 1;
        continuation.push(lines[index].replace(/^[ \t]+/, ""));
      }
      frontmatter[key] = value.startsWith(">") ? continuation.join(" ").trim() : continuation.join("\n").trim();
    } else {
      frontmatter[key] = parseFrontmatterValue(value);
    }
  }
  if (!frontmatter.name?.trim() || !frontmatter.slug?.trim() || !frontmatter.description?.trim()) return null;
  return { frontmatter, frontmatterRaw: match[1], body: match[2].replace(/^\r?\n/, "") };
}

function validateFilePath(path: string, files: SkillFile[], currentIndex: number): string | null {
  if (!path || path.startsWith("/") || /^[A-Za-z]:/.test(path)) return "请输入安全的相对路径";
  const parts = path.split("/");
  if (parts.some((part) => !part || part === "." || part === "..")) return "路径不能包含空目录、. 或 ..";
  if (RESERVED_FILES.has(path.toLowerCase())) return "该文件名由 AgentMate 保留";
  if (files.some((file, index) => index !== currentIndex && file.path.toLowerCase() === path.toLowerCase())) {
    return "同一路径已经存在";
  }
  return null;
}

export default function SkillEditor({ open, item, tools, categories, initialTab, onClose, onSaved }: SkillEditorProps) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm<SkillFormValues>();
  const [tab, setTab] = useState<"info" | "files" | "tools">(initialTab);
  const [files, setFiles] = useState<SkillFile[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | "skill">("skill");
  const [fileQuery, setFileQuery] = useState("");
  const [draftPath, setDraftPath] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [skillMarkdown, setSkillMarkdown] = useState("");
  const [fileDirty, setFileDirty] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const initialFilesSnapshot = useRef("");
  const initialSkillMarkdownSnapshot = useRef("");
  const selectedTools = Form.useWatch("tools", form) || [];
  const hiddenBoundTools = selectedTools.filter((name) => !tools.some((tool) => tool.name === name));

  useEffect(() => {
    if (!open) return;
    const data = item?.data;
    const nextFiles = Array.isArray(data?.files) ? data.files.map((file) => ({ ...file })) : [];
    const values: SkillFormValues = {
      slug: data?.slug || "",
      name: data?.name || "",
      icon: data?.icon || "🧩",
      category_slug: data?.category_slug || categories.find((category) => category.data.name === data?.category)?.data.slug || "",
      description: data?.description || "",
      tools: Array.isArray(data?.tools) ? data.tools : [],
      min_app_version: data?.min_app_version || "0.0.0",
      sort: item?.sort || 0,
    };
    const sourceMarkdown = typeof data?.skill_markdown === "string" ? data.skill_markdown : "";
    const parsedSource = sourceMarkdown ? parseSkillMarkdown(sourceMarkdown) : null;
    const nextSkillMarkdown = parsedSource
      ? sourceMarkdown
      : buildSkillMarkdown(values, item?.version || 1, null, data?.instructions || "");
    form.setFieldsValue(values);
    setFiles(nextFiles);
    setSelectedIndex("skill");
    setDraftPath("");
    setSkillMarkdown(nextSkillMarkdown);
    setDraftContent(nextSkillMarkdown);
    setFileDirty(false);
    setFormDirty(false);
    setFileQuery("");
    setTab(initialTab);
    initialFilesSnapshot.current = JSON.stringify(nextFiles);
    initialSkillMarkdownSnapshot.current = nextSkillMarkdown;
  }, [categories, form, initialTab, item, open]);

  const visibleFiles = useMemo(() => {
    const query = fileQuery.trim().toLowerCase();
    return files.map((file, index) => ({ file, index })).filter(({ file }) => !query || file.path.toLowerCase().includes(query));
  }, [fileQuery, files]);

  function loadFile(index: number | "skill") {
    if (fileDirty) {
      message.warning("请先应用或撤销当前文件修改");
      return;
    }
    setSelectedIndex(index);
    if (index === "skill") {
      setDraftPath("");
      setDraftContent(skillMarkdown);
    } else {
      setDraftPath(files[index]?.path || "");
      setDraftContent(files[index]?.content || "");
    }
    setFileDirty(false);
  }

  useEffect(() => {
    if (!open || fileDirty || selectedIndex !== "skill") return;
    setDraftContent(skillMarkdown);
  }, [fileDirty, open, selectedIndex, skillMarkdown]);

  function syncSkillMarkdown(values: SkillFormValues) {
    if (fileDirty) return;
    const parsed = parseSkillMarkdown(skillMarkdown);
    const next = buildSkillMarkdown(values, item?.version || 1, parsed, parsed?.body || "");
    setSkillMarkdown(next);
    if (selectedIndex === "skill") setDraftContent(next);
  }

  function changeTab(next: "info" | "files" | "tools") {
    if (fileDirty) {
      message.warning("请先应用或撤销当前文件修改");
      return;
    }
    setTab(next);
  }

  function applySkillDraft(): boolean {
    const parsed = parseSkillMarkdown(draftContent);
    if (!parsed) {
      message.error("SKILL.md 必须包含有效的 front-matter：name、slug、description");
      return false;
    }
    const currentSlug = String(form.getFieldValue("slug") || "").trim();
    if (item && parsed.frontmatter.slug !== currentSlug) {
      message.error("已有技能的 slug 不可修改，请保持 front-matter 中的 slug 不变");
      return false;
    }
    form.setFieldsValue({
      name: parsed.frontmatter.name,
      slug: parsed.frontmatter.slug,
      description: parsed.frontmatter.description,
    });
    setSkillMarkdown(draftContent);
    setFileDirty(false);
    message.success("SKILL.md 修改已应用，将在保存技能时提交");
    return true;
  }

  function applyFileDraft(): SkillFile[] | null {
    if (selectedIndex === "skill") return applySkillDraft() ? files : null;
    const path = normalizePath(draftPath);
    const validation = validateFilePath(path, files, selectedIndex);
    if (validation) {
      message.error(validation);
      return null;
    }
    const next = files.map((file, index) => index === selectedIndex ? { path, content: draftContent } : file);
    const bytes = new Blob(next.map((file) => file.content)).size;
    if (next.length > 128 || bytes > 1024 * 1024) {
      message.error("附加文件最多 128 个，总内容不能超过 1MB");
      return null;
    }
    setFiles(next);
    setFileDirty(false);
    message.success("文件修改已应用，将在保存技能时提交");
    return next;
  }

  function revertFileDraft() {
    if (selectedIndex === "skill") {
      setDraftContent(skillMarkdown);
      setFileDirty(false);
      return;
    }
    const current = files[selectedIndex];
    setDraftPath(current?.path || "");
    setDraftContent(current?.content || "");
    setFileDirty(false);
  }

  function addFile() {
    if (fileDirty) {
      message.warning("请先应用或撤销当前文件修改");
      return;
    }
    let suffix = files.length + 1;
    let path = `references/new-file-${suffix}.md`;
    while (files.some((file) => file.path === path)) path = `references/new-file-${++suffix}.md`;
    const next = [...files, { path, content: "" }];
    setFiles(next);
    setSelectedIndex(next.length - 1);
    setDraftPath(path);
    setDraftContent("");
    setFileDirty(true);
  }

  function deleteFile() {
    if (selectedIndex === "skill") return;
    const target = files[selectedIndex];
    modal.confirm({
      title: `删除 ${target.path}？`,
      content: "文件将在保存技能后从 Server 技能定义中移除。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () => {
        setFiles((current) => current.filter((_file, index) => index !== selectedIndex));
        setSelectedIndex("skill");
        setDraftPath("");
        setDraftContent(skillMarkdown);
        setFileDirty(false);
      },
    });
  }

  function isDirty(): boolean {
    return formDirty || fileDirty || skillMarkdown !== initialSkillMarkdownSnapshot.current || JSON.stringify(files) !== initialFilesSnapshot.current;
  }

  function requestClose() {
    if (!isDirty()) {
      onClose();
      return;
    }
    modal.confirm({
      title: "放弃尚未保存的修改？",
      content: "基本信息或文件内容已发生变化。",
      okText: "放弃修改",
      okButtonProps: { danger: true },
      cancelText: "继续编辑",
      onOk: onClose,
    });
  }

  async function save() {
    let values: SkillFormValues;
    try {
      if (fileDirty && selectedIndex === "skill" && !applySkillDraft()) {
        setTab("files");
        return;
      }
      values = await form.validateFields();
    } catch {
      setTab("info");
      return;
    }
    const effectiveFiles = fileDirty ? applyFileDraft() : files;
    if (!effectiveFiles) {
      setTab("files");
      return;
    }
    const data: SkillData = {
      slug: values.slug.trim(),
      name: values.name.trim(),
      icon: values.icon.trim() || "🧩",
      category_slug: values.category_slug.trim(),
      category: categories.find((category) => category.data.slug === values.category_slug)?.data.name || "",
      description: values.description.trim(),
      instructions: parseSkillMarkdown(skillMarkdown)?.body.trim() || "",
      skill_markdown: skillMarkdown,
      tools: values.tools || [],
      files: effectiveFiles,
      source: "Server",
      min_app_version: values.min_app_version.trim() || "0.0.0",
    };
    if (!data.instructions) {
      message.error("请在“文件”Tab中填写 SKILL.md 正文");
      setTab("files");
      return;
    }
    setSaving(true);
    try {
      await consoleApi.createSkillRelease(data, values.sort || 0, item?.id || "", data.min_app_version);
      message.success(item ? "新版本草稿已保存，测试和审核后方可发布" : "技能草稿已创建，尚未进入客户端下行");
      onSaved();
      onClose();
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Drawer
      open={open}
      width={960}
      title={item ? `编辑技能 · ${item.data.name}` : "新建技能草稿"}
      onClose={requestClose}
      destroyOnHidden
      maskClosable={false}
      extra={(
        <Space>
          <Button onClick={requestClose}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void save()}>
            {item ? "保存新版本草稿" : "创建技能草稿"}
          </Button>
        </Space>
      )}
    >
      <Segmented
        className="editor-tabs"
        value={tab}
        options={[
          { label: "基本信息", value: "info" },
          { label: `文件 ${files.length + 1}`, value: "files" },
          { label: "可用工具", value: "tools" },
        ]}
        onChange={(value) => changeTab(value as "info" | "files" | "tools")}
      />

      <Form<SkillFormValues>
        form={form}
        layout="vertical"
        requiredMark="optional"
        onValuesChange={(_changed, values) => { setFormDirty(true); syncSkillMarkdown(values); }}
      >
        <section className={tab === "info" ? "" : "hidden-panel"}>
        <Alert
          type={item ? "info" : "success"}
          showIcon
          className="skill-editor-mode-note"
          title={item ? "编辑已有技能：保存后会创建新的版本草稿，不会立即发布。" : "新建技能：保存后会创建一个待测试、待审核的技能草稿。"}
        />
        <Row gutter={16}>
          <Col xs={24} md={12}>
            <Form.Item name="slug" label="slug（稳定身份）" rules={[
              { required: true, message: "请输入 slug" },
              { pattern: /^[A-Za-z0-9][A-Za-z0-9._-]*$/, message: "仅允许字母、数字与 . _ -" },
            ]}>
              <Input disabled={Boolean(item)} maxLength={120} placeholder="my-skill" />
            </Form.Item>
          </Col>
          <Col xs={24} md={12}>
            <Form.Item name="name" label="名称" rules={[{ required: true, whitespace: true, message: "请输入名称" }]}>
              <Input maxLength={120} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col xs={24} md={8}><Form.Item name="icon" label="图标"><IconPicker ariaLabel="选择技能图标" /></Form.Item></Col>
          <Col xs={24} md={10}>
            <Form.Item name="category_slug" label="分类" rules={[{ required: true, message: "请选择分类" }]}>
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="选择已管理的分类"
                options={categories.map((category) => ({
                  value: category.data.slug,
                  label: `${category.data.icon || "🧩"} ${category.data.name}`,
                  disabled: !category.enabled,
                }))}
              />
            </Form.Item>
          </Col>
          <Col xs={24} md={6}><Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item></Col>
        </Row>
        <Form.Item name="description" label="简介" rules={[{ required: true, whitespace: true, message: "请输入技能简介" }]}>
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Form.Item name="min_app_version" label="最低 App 版本" extra="低于该版本的客户端只能看到兼容提示，不能安装或运行。" rules={[{ required: true, pattern: /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/, message: "请输入语义版本，如 1.2.0" }]}>
          <Input placeholder="0.0.0" />
        </Form.Item>
        </section>
        <section className={`skill-tools-panel ${tab === "tools" ? "" : "hidden-panel"}`}>
          <Alert type="info" showIcon title="可用工具会作为技能的工具绑定保存；工具实现、权限和可绑定状态由“内置工具”页统一管理。" />
          {hiddenBoundTools.length ? (
            <Alert
              type="warning"
              showIcon
              className="skill-tools-legacy"
              title="已有不可绑定工具将被保留"
              description={(
                <Space size={[4, 4]} wrap>
                  {hiddenBoundTools.map((name) => <Tag key={name}>{name}</Tag>)}
                </Space>
              )}
            />
          ) : null}
          <Form.Item
            name="tools"
            label="可用工具"
            getValueFromEvent={(next: string[]) => Array.from(new Set([...hiddenBoundTools, ...next]))}
          >
          <Checkbox.Group className="tool-grid">
            {tools.map((tool) => (
              <Checkbox value={tool.name} key={tool.name} className="tool-choice">
                <span><strong>{tool.label || tool.name}</strong><code>{tool.name}</code></span>
                <Typography.Text type="secondary">{tool.description || "AgentMate 内置工具"}</Typography.Text>
                <Space size={4} wrap>
                  {(tool.permissions || []).map((permission) => <Tag key={permission}>{permission}</Tag>)}
                </Space>
              </Checkbox>
            ))}
          </Checkbox.Group>
          </Form.Item>
        </section>
      </Form>

      <section className={tab === "files" ? "file-workspace" : "hidden-panel"}>
        <Alert
          type="info"
          showIcon
          title="SKILL.md 是技能的指令文件，可直接编辑；保存时会读取 front-matter 和正文。下面的附件会随技能一起安装。"
        />
        <div className="file-browser">
          <aside className="file-list-panel">
            <div className="file-list-header">
              <Space><FolderOpenOutlined /><strong>文件</strong></Space>
              <Button size="small" type="text" icon={<FileAddOutlined />} onClick={addFile}>新增</Button>
            </div>
            <Input.Search allowClear placeholder="搜索文件" value={fileQuery} onChange={(event) => setFileQuery(event.target.value)} />
            <List
              size="small"
              dataSource={[{ file: { path: "SKILL.md", content: skillMarkdown }, index: "skill" as const }, ...visibleFiles]}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有匹配文件" /> }}
              renderItem={({ file, index }) => (
                <List.Item
                  className={`file-list-item ${selectedIndex === index ? "active" : ""}`}
                  onClick={() => loadFile(index)}
                >
                  <FileTextOutlined />
                  <Typography.Text ellipsis title={file.path}>{file.path}</Typography.Text>
                </List.Item>
              )}
            />
          </aside>
          <article className="file-editor-panel">
            <div className="file-editor-toolbar">
              <Space>
                <Typography.Text strong>{selectedIndex === "skill" ? "SKILL.md" : files[selectedIndex]?.path}</Typography.Text>
                {selectedIndex === "skill" ? <Tag color={fileDirty ? "gold" : "blue"}>{fileDirty ? "未应用" : "技能指令文件"}</Tag> : fileDirty ? <Tag color="gold">未应用</Tag> : <Tag>附件</Tag>}
              </Space>
              {selectedIndex !== "skill" ? <Button size="small" danger icon={<DeleteOutlined />} onClick={deleteFile}>删除</Button> : null}
            </div>
            {selectedIndex !== "skill" ? (
              <Input value={draftPath} status={validateFilePath(normalizePath(draftPath), files, selectedIndex) ? "error" : undefined} onChange={(event) => { setDraftPath(event.target.value); setFileDirty(true); }} placeholder="references/guide.md" />
            ) : null}
            <Input.TextArea
              className="file-content-editor"
              value={draftContent}
              maxLength={selectedIndex === "skill" ? 50000 : undefined}
              onChange={(event) => { setDraftContent(event.target.value); setFileDirty(true); }}
              spellCheck={false}
            />
            <div className="file-editor-footer">
              <Typography.Text type="secondary">最多 128 个附件，总计 1MB</Typography.Text>
              {selectedIndex === "skill" ? (
                <Space>
                  <Button disabled={!fileDirty} onClick={revertFileDraft}>撤销</Button>
                  <Button type="primary" disabled={!fileDirty} onClick={() => { applySkillDraft(); }}>应用 SKILL.md 更改</Button>
                </Space>
              ) : (
                <Space>
                  <Button disabled={!fileDirty} onClick={revertFileDraft}>撤销</Button>
                  <Button type="primary" disabled={!fileDirty} onClick={applyFileDraft}>应用更改</Button>
                </Space>
              )}
            </div>
          </article>
        </div>
      </section>
    </Drawer>
  );
}
