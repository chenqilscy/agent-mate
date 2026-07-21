import { App, Badge, Button, Card, Empty, Space, Tag, Typography } from "antd";
import { CompatList as List } from "../components/CompatList";
import { BellOutlined, CheckOutlined } from "@ant-design/icons";
import { PageContainer } from "@ant-design/pro-components";
import { useEffect, useState } from "react";
import { consoleApi } from "../api";
import type { NotificationRecord } from "../types";

export default function NotificationsPage({ onUnreadChange }: { onUnreadChange?: (count: number) => void }) {
  const { message } = App.useApp();
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  async function load() { setLoading(true); try { const result = await consoleApi.notifications(); setItems(result.notifications || []); setUnread(result.unread || 0); onUnreadChange?.(result.unread || 0); } catch (reason) { message.error(reason instanceof Error ? reason.message : "通知加载失败"); } finally { setLoading(false); } }
  useEffect(() => { void load(); }, []);
  async function readAll() { try { await consoleApi.markNotificationsRead(); message.success("已全部标记为已读"); await load(); } catch (reason) { message.error(reason instanceof Error ? reason.message : "操作失败"); } }
  return (
    <PageContainer title={<Space>通知中心<Badge count={unread} /></Space>} subTitle="项目协作与系统事件" extra={<Button icon={<CheckOutlined />} disabled={!unread} onClick={() => void readAll()}>全部已读</Button>} header={{ breadcrumb: { items: [{ title: "通知" }] } }}>
      <Card loading={loading}>
        {items.length ? <List dataSource={items} renderItem={(item) => <List.Item className={item.read ? "" : "unread-item"}><List.Item.Meta avatar={<BellOutlined />} title={<Space><Typography.Text strong={!item.read}>{item.title || item.kind || "系统通知"}</Typography.Text>{!item.read && <Tag color="blue">未读</Tag>}</Space>} description={<><div>{item.body || item.message || ""}</div><Typography.Text type="secondary">{item.created_at ? new Date(item.created_at * 1000).toLocaleString() : ""}</Typography.Text></>} /></List.Item>} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无通知" />}
      </Card>
    </PageContainer>
  );
}
