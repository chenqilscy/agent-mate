import {
  Alert,
  App,
  Button,
  Card,
  Empty,
  List,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  DownloadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { consoleApi } from "../../api";
import type {
  Project,
  WorkItem,
  WorkItemDelivery,
  WorkItemRun,
  WorkItemRunEvent,
  WorkItemRunPlanItem,
  WorkItemRunStatus,
} from "../../types";

const ACTIVE_STATUSES = new Set<WorkItemRunStatus>([
  "queued",
  "leased",
  "planning",
  "running",
  "waiting_user",
  "paused",
  "recoverable",
]);

const STATUS_META: Record<WorkItemRunStatus, { label: string; color: string }> =
  {
    queued: { label: "排队中", color: "default" },
    leased: { label: "已领取", color: "processing" },
    planning: { label: "规划中", color: "processing" },
    running: { label: "执行中", color: "processing" },
    waiting_user: { label: "等待用户操作", color: "warning" },
    paused: { label: "已暂停", color: "warning" },
    recoverable: { label: "等待恢复", color: "warning" },
    completed: { label: "待验收", color: "success" },
    succeeded: { label: "待验收", color: "success" },
    failed: { label: "失败", color: "error" },
    cancelled: { label: "已取消", color: "default" },
  };

const PLAN_STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: "待执行", color: "default" },
  in_progress: { label: "进行中", color: "processing" },
  completed: { label: "已完成", color: "success" },
  blocked: { label: "已阻塞", color: "error" },
};

function timestamp(value?: number | null): string {
  return value ? new Date(value * 1000).toLocaleString() : "—";
}

function duration(run: WorkItemRun): string {
  if (!run.started_at) return "尚未开始";
  const end = run.ended_at || Date.now() / 1000;
  const seconds = Math.max(0, Math.round(end - run.started_at));
  if (seconds < 60) return `${seconds} 秒`;
  if (seconds < 3600)
    return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
  return `${Math.floor(seconds / 3600)} 小时 ${Math.floor((seconds % 3600) / 60)} 分`;
}

function payloadText(payload: Record<string, unknown>, key: string): string {
  return typeof payload[key] === "string" ? String(payload[key]) : "";
}

function eventLabel(event: WorkItemRunEvent): string {
  const payload = event.payload || {};
  if (event.type === "run.started") return "Local Agent 开始执行";
  if (event.type === "run.waiting_user") return "执行等待用户回答或授权";
  if (event.type === "run.paused" || event.type === "run.pause_ack")
    return "执行已暂停";
  if (event.type === "run.completed") return "执行完成，等待交付验收";
  if (event.type === "run.failed")
    return payloadText(payload, "message") || "执行失败";
  if (event.type === "run.cancelled" || event.type === "run.cancel_ack")
    return "执行已取消";
  if (event.type === "ui.step")
    return (
      payloadText(payload, "label") ||
      payloadText(payload, "tool") ||
      "执行步骤"
    );
  if (event.type === "ui.todo")
    return payloadText(payload, "text") || "更新执行事项";
  if (event.type === "ui.plan_snapshot") return "生成执行计划";
  if (event.type === "ui.plan_patch") return "更新执行计划";
  if (event.type === "ui.artifact")
    return `生成产物：${payloadText(payload, "name") || "未命名产物"}`;
  if (event.type === "ui.error")
    return payloadText(payload, "message") || "执行发生错误";
  if (event.type === "ui.usage") return "更新模型用量";
  return event.type;
}

function projectedPlan(run: WorkItemRun): WorkItemRunPlanItem[] {
  if (run.plan.length) return run.plan;
  const planEvent = [...run.events]
    .reverse()
    .find((event) =>
      ["ui.plan_snapshot", "ui.plan_patch"].includes(event.type),
    );
  const items = planEvent?.payload.items;
  return Array.isArray(items) ? (items as WorkItemRunPlanItem[]) : [];
}

function RunCard({
  run,
  delivery,
  accepting,
  onAccept,
}: {
  run: WorkItemRun;
  delivery: WorkItemDelivery;
  accepting: boolean;
  onAccept: (run: WorkItemRun) => void;
}) {
  const { message } = App.useApp();
  const plan = projectedPlan(run);
  const status = STATUS_META[run.status] || {
    label: run.status,
    color: "default",
  };
  const verifiedArtifacts = run.artifacts.filter(
    (artifact) =>
      artifact.verification?.exists && artifact.verification?.hash_matches,
  );
  const accepted = delivery.acceptance?.run_id === run.id;
  const canAccept =
    delivery.can_write &&
    delivery.work_item.status === "review" &&
    ["completed", "succeeded"].includes(run.status) &&
    run.artifacts.length > 0 &&
    verifiedArtifacts.length === run.artifacts.length &&
    !accepted;
  const visibleEvents = run.events.filter(
    (event) =>
      !["ui.usage", "ui.plan_snapshot", "ui.plan_patch"].includes(event.type),
  );

  return (
    <Card
      size="small"
      className="work-item-run-card"
      title={
        <Space size={[6, 6]} wrap>
          <Tag color={status.color}>{accepted ? "已验收" : status.label}</Tag>
          <Typography.Text>Run {run.id.slice(0, 8)}</Typography.Text>
          {run.retry_of && <Tag color="orange">重试</Tag>}
          {run.recovery_count > 0 && <Tag>恢复 {run.recovery_count} 次</Tag>}
        </Space>
      }
      extra={
        <Typography.Text type="secondary">
          {timestamp(run.created_at)}
        </Typography.Text>
      }
    >
      <div className="work-item-run-summary">
        <div>
          <Typography.Text type="secondary">执行设备</Typography.Text>
          <Typography.Text>
            {run.device?.name ||
              (run.target_device_id
                ? "等待指定 Local Agent"
                : "等待兼容 Local Agent")}
          </Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">执行耗时</Typography.Text>
          <Typography.Text>{duration(run)}</Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">模型与工具</Typography.Text>
          <Typography.Text>
            {run.model_id || run.model_ref || "默认模型"} · {run.tool_calls}{" "}
            次工具调用
          </Typography.Text>
        </div>
        <div>
          <Typography.Text type="secondary">Token</Typography.Text>
          <Typography.Text>
            {run.prompt_tokens + run.completion_tokens}
            {run.cached_prompt_tokens
              ? `（缓存 ${run.cached_prompt_tokens}）`
              : ""}
          </Typography.Text>
        </div>
      </div>

      {run.queue_context && (
        <Alert
          type="info"
          showIcon
          className="work-item-run-alert"
          message="当前排队原因"
          description={run.queue_context.message}
        />
      )}
      {run.status === "waiting_user" && (
        <Alert
          type="warning"
          showIcon
          className="work-item-run-alert"
          message="需要在 App 端处理"
          description="此 Run 正在等待回答或授权。Console 仅展示状态，请由执行负责人在 App 中继续。"
        />
      )}
      {run.error_message && (
        <Alert
          type="error"
          showIcon
          className="work-item-run-alert"
          message={run.error_code || "执行失败"}
          description={run.error_message}
        />
      )}

      <div className="work-item-run-columns">
        <section>
          <Typography.Title level={5}>执行计划</Typography.Title>
          {plan.length ? (
            <List
              size="small"
              dataSource={[...plan].sort(
                (left, right) => left.order - right.order,
              )}
              renderItem={(item) => {
                const meta = PLAN_STATUS_META[item.status] || {
                  label: item.status,
                  color: "default",
                };
                return (
                  <List.Item>
                    <Space align="start">
                      <Tag color={meta.color}>{meta.label}</Tag>
                      <Typography.Text>{item.title}</Typography.Text>
                    </Space>
                  </List.Item>
                );
              }}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="该 Run 未提交结构化计划"
            />
          )}
        </section>
        <section>
          <Typography.Title level={5}>执行过程</Typography.Title>
          {visibleEvents.length ? (
            <Timeline
              items={visibleEvents.slice(-20).map((event) => ({
                color:
                  event.type.includes("failed") || event.type === "ui.error"
                    ? "red"
                    : "blue",
                children: (
                  <div>
                    <Typography.Text>{eventLabel(event)}</Typography.Text>
                    <br />
                    <Typography.Text type="secondary">
                      {timestamp(event.occurred_at)}
                    </Typography.Text>
                  </div>
                ),
              }))}
            />
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无可共享的执行事件"
            />
          )}
        </section>
      </div>

      <Typography.Title level={5}>交付产物</Typography.Title>
      <List
        size="small"
        dataSource={run.artifacts}
        locale={{ emptyText: "尚未提交可验收产物" }}
        renderItem={(artifact) => (
          <List.Item
            actions={[
              <Button
                key="download"
                type="link"
                icon={<DownloadOutlined />}
                disabled={artifact.storage_state !== "committed"}
                onClick={() =>
                  void consoleApi
                    .downloadAsset(artifact)
                    .catch(() => message.error("产物下载失败"))
                }
              >
                下载
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={artifact.name}
              description={
                <Space size={[6, 6]} wrap>
                  <Tag
                    color={
                      artifact.verification?.hash_matches
                        ? "success"
                        : "warning"
                    }
                  >
                    {artifact.verification?.hash_matches
                      ? "完整性已验证"
                      : "待验证"}
                  </Tag>
                  <Tag
                    color={
                      artifact.acceptance_status === "accepted"
                        ? "success"
                        : "default"
                    }
                  >
                    {artifact.acceptance_status === "accepted"
                      ? "已验收"
                      : "待验收"}
                  </Tag>
                  <Typography.Text type="secondary">
                    {artifact.size.toLocaleString()} bytes
                  </Typography.Text>
                </Space>
              }
            />
          </List.Item>
        )}
      />
      {accepted && delivery.acceptance && (
        <Alert
          type="success"
          showIcon
          className="work-item-run-alert"
          message="交付已验收"
          description={`验收时间：${timestamp(delivery.acceptance.accepted_at)}；产物 ${delivery.acceptance.artifact_count} 个。`}
        />
      )}
      {canAccept && (
        <Button
          type="primary"
          icon={<CheckCircleOutlined />}
          loading={accepting}
          onClick={() => onAccept(run)}
        >
          验收全部产物并完成任务
        </Button>
      )}
    </Card>
  );
}

export function WorkItemExecution({
  project,
  workItem,
  onWorkItemUpdated,
}: {
  project: Project;
  workItem: WorkItem;
  onWorkItemUpdated: (item: WorkItem) => void;
}) {
  const { message } = App.useApp();
  const [delivery, setDelivery] = useState<WorkItemDelivery | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [acceptingRunId, setAcceptingRunId] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(
    async (quiet = false) => {
      if (!quiet) setLoading(true);
      try {
        const value = await consoleApi.workItemDelivery(
          project.id,
          workItem.id,
        );
        setDelivery(value);
        setError("");
        if (value.work_item.status !== workItem.status)
          onWorkItemUpdated(value.work_item);
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "执行信息加载失败");
      } finally {
        if (!quiet) setLoading(false);
      }
    },
    [onWorkItemUpdated, project.id, workItem.id, workItem.status],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const active = useMemo(
    () =>
      delivery?.runs.some((run) => ACTIVE_STATUSES.has(run.status)) || false,
    [delivery],
  );

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => void load(true), 2500);
    return () => window.clearInterval(timer);
  }, [active, load]);

  async function loadMore() {
    if (!delivery?.next_cursor) return;
    setLoadingMore(true);
    try {
      const page = await consoleApi.workItemDelivery(
        project.id,
        workItem.id,
        delivery.next_cursor,
      );
      setDelivery({
        ...page,
        runs: [...delivery.runs, ...page.runs],
        launches: [...delivery.launches, ...page.launches],
      });
    } catch {
      message.error("更多执行记录加载失败");
    } finally {
      setLoadingMore(false);
    }
  }

  async function accept(run: WorkItemRun) {
    setAcceptingRunId(run.id);
    try {
      const updated = await consoleApi.acceptWorkItemDelivery(
        project.id,
        workItem.id,
        run.id,
        run.artifacts.length,
      );
      onWorkItemUpdated(updated);
      message.success("交付已验收，任务已完成");
      await load(true);
    } catch (reason) {
      message.error(reason instanceof Error ? reason.message : "验收失败");
    } finally {
      setAcceptingRunId("");
    }
  }

  return (
    <Card
      size="small"
      title="Local Agent 执行与交付"
      className="section-card work-item-execution"
      extra={
        <Button
          type="text"
          icon={<ReloadOutlined />}
          loading={loading}
          onClick={() => void load()}
        >
          刷新
        </Button>
      }
    >
      {error && (
        <Alert
          type="error"
          showIcon
          message="执行信息暂不可用"
          description={error}
          action={<Button onClick={() => void load()}>重试</Button>}
        />
      )}
      {loading && !delivery ? (
        <div className="work-item-execution-loading">
          <Spin />
        </div>
      ) : !delivery || delivery.runs.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="尚未产生关联 Run；任务交给 Local Agent 后会在这里显示真实进度。"
        />
      ) : (
        <Space direction="vertical" size={12} className="full-width">
          {delivery.runs.map((run) => (
            <RunCard
              key={run.id}
              run={run}
              delivery={delivery}
              accepting={acceptingRunId === run.id}
              onAccept={(value) => void accept(value)}
            />
          ))}
          {delivery.next_cursor && (
            <Button block loading={loadingMore} onClick={() => void loadMore()}>
              加载更早的执行记录
            </Button>
          )}
        </Space>
      )}
    </Card>
  );
}
