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
  List,
  Row,
  Segmented,
  Space,
  Tag,
  Typography,
} from "antd";
import {
  DeleteOutlined,
  FileAddOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  SaveOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { consoleApi } from "./api";
import type { CatalogItem, SkillData, SkillFile, SkillTool } from "./types";

interface SkillFormValues {
  slug: string;
  name: string;
  icon: string;
  category: string;
  description: string;
  instructions: string;
  tools: string[];
  sort: number;
}

interface SkillEditorProps {
  open: boolean;
  item: CatalogItem<SkillData> | null;
  tools: SkillTool[];
  initialTab: "info" | "files";
  onClose: () => void;
  onSaved: () => void;
}

const RESERVED_FILES = new Set(["skill.md", "_skillhub_meta.json", "_meta.json", ".disabled"]);

function normalizePath(value: string): string {
  return value.replace(/\\/g, "/").trim();
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

export default function SkillEditor({ open, item, tools, initialTab, onClose, onSaved }: SkillEditorProps) {
  const { message, modal } = App.useApp();
  const [form] = Form.useForm<SkillFormValues>();
  const [tab, setTab] = useState<"info" | "files">(initialTab);
  const [files, setFiles] = useState<SkillFile[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | "skill">("skill");
  const [fileQuery, setFileQuery] = useState("");
  const [draftPath, setDraftPath] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [fileDirty, setFileDirty] = useState(false);
  const [formDirty, setFormDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const initialFilesSnapshot = useRef("");

  useEffect(() => {
    if (!open) return;
    const data = item?.data;
    const nextFiles = Array.isArray(data?.files) ? data.files.map((file) => ({ ...file })) : [];
    const values: SkillFormValues = {
      slug: data?.slug || "",
      name: data?.name || "",
      icon: data?.icon || "🧩",
      category: data?.category || "",
      description: data?.description || "",
      instructions: data?.instructions || "",
      tools: Array.isArray(data?.tools) ? data.tools : [],
      sort: item?.sort || 0,
    };
    form.setFieldsValue(values);
    setFiles(nextFiles);
    setSelectedIndex("skill");
    setDraftPath("");
    setDraftContent("");
    setFileDirty(false);
    setFormDirty(false);
    setFileQuery("");
    setTab(initialTab);
    initialFilesSnapshot.current = JSON.stringify(nextFiles);
  }, [form, initialTab, item, open]);

  const generatedSkillMarkdown = useMemo(() => {
    const values = form.getFieldsValue();
    return `---\nname: ${JSON.stringify(values.name || "")}\nslug: ${values.slug || ""}\ndescription: ${JSON.stringify(values.description || "")}\nversion: ${JSON.stringify(String(item?.version || 1))}\nsource: agentmate\n---\n\n${values.instructions || ""}\n`;
    // Watching the form below causes this memo to update through the component render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Form.useWatch([], form), item?.version]);

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
      setDraftContent(generatedSkillMarkdown);
    } else {
      setDraftPath(files[index]?.path || "");
      setDraftContent(files[index]?.content || "");
    }
    setFileDirty(false);
  }

  useEffect(() => {
    if (!open || fileDirty) return;
    if (selectedIndex === "skill") setDraftContent(generatedSkillMarkdown);
  }, [fileDirty, generatedSkillMarkdown, open, selectedIndex]);

  function applyFileDraft(): SkillFile[] | null {
    if (selectedIndex === "skill") return files;
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
    if (selectedIndex === "skill") return;
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
      content: "文件将在保存技能后从 Server 目录定义中移除。",
      okText: "删除",
      okButtonProps: { danger: true },
      cancelText: "取消",
      onOk: () => {
        setFiles((current) => current.filter((_file, index) => index !== selectedIndex));
        setSelectedIndex("skill");
        setDraftPath("");
        setDraftContent(generatedSkillMarkdown);
        setFileDirty(false);
      },
    });
  }

  function isDirty(): boolean {
    return formDirty || fileDirty || JSON.stringify(files) !== initialFilesSnapshot.current;
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
      category: values.category.trim(),
      description: values.description.trim(),
      instructions: values.instructions.trim(),
      tools: values.tools || [],
      files: effectiveFiles,
      source: "Server",
    };
    setSaving(true);
    try {
      if (item) await consoleApi.updateSkill(item.id, { data, sort: values.sort || 0 });
      else await consoleApi.createSkill(data, values.sort || 0);
      message.success(item ? "技能已更新" : "技能已创建");
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
      title={item ? `编辑技能 · ${item.data.name}` : "新增技能"}
      onClose={requestClose}
      destroyOnHidden
      maskClosable={false}
      extra={(
        <Space>
          <Button onClick={requestClose}>取消</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={() => void save()}>
            保存技能
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
        ]}
        onChange={(value) => setTab(value as "info" | "files")}
      />

      <Form<SkillFormValues> form={form} layout="vertical" requiredMark="optional" onValuesChange={() => setFormDirty(true)} className={tab === "info" ? "" : "hidden-panel"}>
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
          <Col xs={24} md={8}><Form.Item name="icon" label="图标"><Input maxLength={16} placeholder="🧩" /></Form.Item></Col>
          <Col xs={24} md={10}><Form.Item name="category" label="分类"><Input maxLength={80} placeholder="办公效率" /></Form.Item></Col>
          <Col xs={24} md={6}><Form.Item name="sort" label="排序"><InputNumber min={0} precision={0} className="full-width" /></Form.Item></Col>
        </Row>
        <Form.Item name="description" label="简介" rules={[{ required: true, whitespace: true, message: "请输入技能简介" }]}>
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
        <Form.Item name="instructions" label="技能指令" extra="保存后生成 SKILL.md 正文，并在使用技能时注入模型。" rules={[{ required: true, whitespace: true, message: "请输入技能指令" }]}>
          <Input.TextArea rows={9} maxLength={50000} showCount className="code-input" />
        </Form.Item>
        <Form.Item name="tools" label="可用工具">
          <Checkbox.Group className="tool-grid">
            {tools.map((tool) => (
              <Checkbox value={tool.name} key={tool.name} className="tool-choice">
                <span><strong>{tool.label || tool.name}</strong><code>{tool.name}</code></span>
                <Typography.Text type="secondary">{tool.description || "AgentMate 内置工具"}</Typography.Text>
              </Checkbox>
            ))}
          </Checkbox.Group>
        </Form.Item>
      </Form>

      <section className={tab === "files" ? "file-workspace" : "hidden-panel"}>
        <Alert
          type="info"
          showIcon
          message="SKILL.md 由基本信息和技能指令自动生成；这里只维护随技能安装的 UTF-8 文本附件。"
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
              dataSource={[{ file: { path: "SKILL.md", content: generatedSkillMarkdown }, index: "skill" as const }, ...visibleFiles]}
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
                {selectedIndex === "skill" ? <Tag color="blue">自动生成</Tag> : fileDirty ? <Tag color="gold">未应用</Tag> : <Tag>附件</Tag>}
              </Space>
              {selectedIndex !== "skill" ? <Button size="small" danger icon={<DeleteOutlined />} onClick={deleteFile}>删除</Button> : null}
            </div>
            {selectedIndex !== "skill" ? (
              <Input value={draftPath} status={validateFilePath(normalizePath(draftPath), files, selectedIndex) ? "error" : undefined} onChange={(event) => { setDraftPath(event.target.value); setFileDirty(true); }} placeholder="references/guide.md" />
            ) : null}
            <Input.TextArea
              className="file-content-editor"
              value={selectedIndex === "skill" ? generatedSkillMarkdown : draftContent}
              readOnly={selectedIndex === "skill"}
              onChange={(event) => { setDraftContent(event.target.value); setFileDirty(true); }}
              spellCheck={false}
            />
            <div className="file-editor-footer">
              <Typography.Text type="secondary">最多 128 个附件，总计 1MB</Typography.Text>
              {selectedIndex !== "skill" ? (
                <Space>
                  <Button disabled={!fileDirty} onClick={revertFileDraft}>撤销</Button>
                  <Button type="primary" disabled={!fileDirty} onClick={applyFileDraft}>应用更改</Button>
                </Space>
              ) : null}
            </div>
          </article>
        </div>
      </section>
    </Drawer>
  );
}
