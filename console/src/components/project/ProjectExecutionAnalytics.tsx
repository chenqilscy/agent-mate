import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { consoleApi } from "../../api";
import type {
  Project,
  ProjectExecutionAnalytics,
  ProjectExecutionRunMetric,
  WorkItem,
} from "../../types";

function duration(value: number | null): string {
  if (value === null) return "—";
  if (value < 60) return `${value.toFixed(1)} 秒`;
  if (value < 3600) return `${(value / 60).toFixed(1)} 分钟`;
  return `${(value / 3600).toFixed(1)} 小时`;
}

function percent(value: number | null): number {
  return value === null ? 0 : Math.round(value * 1000) / 10;
}

function cost(values: Record<string, number>): string {
  const entries = Object.entries(values);
  return entries.length
    ? entries.map(([currency, value]) => `${currency} ${value.toFixed(4)}`).join(" · ")
    : "—";
}

export function ProjectExecutionAnalyticsPanel({
  project,
  items,
  onOpenTask,
}: {
  project: Project;
  items: WorkItem[];
  onOpenTask: (item: WorkItem) => void;
}) {
  const [days, setDays] = useState<7 | 30 | 90>(7);
  const [data, setData] = useState<ProjectExecutionAnalytics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    [],
  );
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await consoleApi.projectExecutionAnalytics(project.id, days, timezone));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "执行分析加载失败");
    } finally {
      setLoading(false);
    }
  }, [days, project.id, timezone]);
  useEffect(() => { void load(); }, [load]);

  const drilldown = (metric: ProjectExecutionRunMetric) => {
    const item = items.find((candidate) => candidate.id === metric.work_item_id);
    if (item) onOpenTask(item);
  };
  const runColumns = [
    {
      title: "任务 / Run",
      key: "run",
      render: (_: unknown, item: ProjectExecutionRunMetric) => (
        <Space orientation="vertical" size={0}>
          <Button type="link" size="small" disabled={!item.work_item_id} onClick={() => drilldown(item)}>{item.work_item_title}</Button>
          <Typography.Text code>{item.run_id.slice(0, 8)}</Typography.Text>
        </Space>
      ),
    },
    { title: "状态", dataIndex: "status", render: (value: string) => <Tag>{value}</Tag> },
    { title: "排队", key: "queue", render: (_: unknown, item: ProjectExecutionRunMetric) => `${duration(item.queue_seconds)}${item.queue_live ? "（当前）" : ""}` },
    { title: "执行", dataIndex: "execution_seconds", render: duration },
    { title: "Token", dataIndex: "tokens" },
    { title: "预估成本", key: "cost", render: (_: unknown, item: ProjectExecutionRunMetric) => item.estimated_cost === null ? "未定价" : `${item.cost_currency || "?"} ${item.estimated_cost.toFixed(4)}` },
  ];

  return (
    <Card
      title="Agent 执行分析"
      loading={loading && !data}
      extra={<Space><Tag>{data?.metric_version || "project-execution-v2"}</Tag><Select value={days} onChange={setDays} options={[{ value: 7, label: "近 7 天" }, { value: 30, label: "近 30 天" }, { value: 90, label: "近 90 天" }]} /><Button aria-label="刷新执行分析" icon={<ReloadOutlined />} onClick={() => void load()} loading={loading} /></Space>}
    >
      {error && <Alert type="error" showIcon title={error} />}
      {!data ? (!loading && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无执行分析" />) : (
        <Space orientation="vertical" size={16} className="full-width">
          <Alert
            type="info"
            showIcon
            title={`统计窗口：${new Date(data.window.start * 1000).toLocaleString()} 至 ${new Date(data.window.end * 1000).toLocaleString()}（${data.window.timezone}）`}
            description="只统计当前项目的 Server Run、交付和用量；取消不计入成功率，未定价模型不按零成本处理，未验收交付仍计入首次验收分母。"
          />
          <Row gutter={[12, 12]}>
            <Col xs={12} xl={6}><Card size="small"><Statistic title="Run 总数" value={data.summary.runs} suffix={`失败 ${data.summary.failed}`} /></Card></Col>
            <Col xs={12} xl={6}><Card size="small"><Statistic title="成功率" value={percent(data.summary.success_rate)} suffix="%" /></Card></Col>
            <Col xs={12} xl={6}><Card size="small"><Statistic title="排队 P95" value={duration(data.summary.queue_p95_seconds)} /></Card></Col>
            <Col xs={12} xl={6}><Card size="small"><Statistic title="总 Token" value={data.summary.prompt_tokens + data.summary.completion_tokens} suffix={`未定价 ${data.summary.unpriced_runs}`} /></Card></Col>
          </Row>
          <Row gutter={[12, 12]}>
            <Col xs={24} xl={12}>
              <Card size="small" title="交付质量">
                <Space orientation="vertical" className="full-width">
                  <Typography.Text>首次验收 {data.delivery.first_pass_accepted}/{data.delivery.first_pass_total} · 返工 Run {data.delivery.rework_runs}</Typography.Text>
                  <Progress percent={percent(data.delivery.first_pass_acceptance_rate)} status="active" />
                  <Typography.Text>产物校验 {data.delivery.verified_artifacts}/{data.delivery.artifacts}</Typography.Text>
                  <Progress percent={percent(data.delivery.artifact_verification_rate)} />
                </Space>
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card size="small" title="成本与失败">
                <Space orientation="vertical">
                  <Typography.Text>已记录预估成本：{cost(data.summary.estimated_cost)}</Typography.Text>
                  <Typography.Text>重试 Run：{data.summary.retry_runs}；取消：{data.summary.cancelled}；活跃：{data.summary.active}</Typography.Text>
                  <Space wrap>{data.failures.length ? data.failures.map((item) => <Tag color="error" key={item.error_code}>{item.error_code} · {item.runs}</Tag>) : <Tag color="success">无失败</Tag>}</Space>
                </Space>
              </Card>
            </Col>
          </Row>
          <Card size="small" title="每日趋势">
            <Table size="small" pagination={false} rowKey="date" dataSource={data.trend} columns={[
              { title: "日期", dataIndex: "date" },
              { title: "Run", dataIndex: "runs" },
              { title: "成功", dataIndex: "completed" },
              { title: "失败", dataIndex: "failed" },
              { title: "Token", dataIndex: "tokens" },
              { title: "预估成本", dataIndex: "estimated_cost", render: cost },
            ]} />
          </Card>
          <Row gutter={[12, 12]}>
            <Col xs={24} xl={12}>
              <Card size="small" title="当前排队瓶颈">
                {data.queue_blockers.length ? <Space wrap>{data.queue_blockers.map((item) => <Tag color="warning" key={item.reason}>{item.message} · {item.runs}</Tag>)}</Space> : <Typography.Text type="secondary">当前没有排队阻塞</Typography.Text>}
              </Card>
            </Col>
            <Col xs={24} xl={12}>
              <Card size="small" title="Local Agent 设备负载">
                <Table size="small" pagination={false} rowKey="device_id" dataSource={data.devices} columns={[
                  { title: "设备", dataIndex: "device_name" },
                  { title: "就绪", dataIndex: "readiness", render: (value: string) => <Tag>{value}</Tag> },
                  { title: "Run", dataIndex: "runs" },
                  { title: "成功 / 失败", key: "result", render: (_: unknown, item) => `${item.completed} / ${item.failed}` },
                  { title: "并行容量", key: "capacity", render: (_: unknown, item) => `${item.capacity.active}/${item.capacity.parallel}` },
                ]} />
              </Card>
            </Col>
          </Row>
          <Card size="small" title="最慢 Run（点击任务下钻到真实交付）">
            <Table size="small" rowKey="run_id" pagination={false} dataSource={data.slow_runs} columns={runColumns} />
          </Card>
          {!!data.costly_runs.length && <Card size="small" title="最高预估成本 Run"><Table size="small" rowKey="run_id" pagination={false} dataSource={data.costly_runs} columns={runColumns} /></Card>}
          <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
            口径说明：{data.definitions.success_rate}；{data.definitions.first_pass_acceptance}；{data.definitions.cost}。队列原因是当前设备/租约快照，不回推历史阻塞时长。
          </Typography.Paragraph>
        </Space>
      )}
    </Card>
  );
}
