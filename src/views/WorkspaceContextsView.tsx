import { useEffect } from 'react'
import { Alert, Empty, Tag } from 'antd'
import { CompatList as List } from '../components/ui/CompatList'
import { WbButton } from '../components/ui/Primitives'
import { useChatStore } from '../stores/chatStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { openServerConsole } from '../lib/console'

const ROLE_LABEL: Record<string, string> = {
  Owner: '所有者', Admin: '管理员', Member: '成员', Viewer: '只读',
}

export function WorkspaceContextsView() {
  const projects = useProjectStore((state) => state.projects)
  const loading = useProjectStore((state) => state.loading)
  const error = useProjectStore((state) => state.error)
  const updatedAt = useProjectStore((state) => state.updatedAt)
  const load = useProjectStore((state) => state.load)
  const setActive = useProjectStore((state) => state.setActive)
  const startProject = useChatStore((state) => state.startProject)
  const setView = useUIStore((state) => state.setView)

  useEffect(() => { void load() }, [load])

  const execute = (project: (typeof projects)[number]) => {
    setActive(project)
    startProject(project.id, project.name)
    setView('projexec', { projectId: project.id })
  }

  return (
    <section className="view active" data-view="projects">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>我的项目工作</h1>
            <div className="sub">从 Server 项目进入任务，在 App 中推进、监督并验收 Agent 工作</div>
            <WbButton className="btn-line" onClick={() => void openServerConsole('projects')}>在 Console 管理项目</WbButton>
          </div>
        </div>
        <Alert
          type="info"
          showIcon
          title="App 负责推进工作，Console 负责项目治理"
          description="这里可以查看任务、发起执行和验收交付；新建项目、成员角色、计划结构、自动化和审计由 Server Console 统一管理。"
        />
        {error && (
          <Alert
            className="project-sync-alert"
            type="warning"
            showIcon
            title={updatedAt ? 'Server 暂不可达，当前显示上次同步的项目' : 'Server 项目读取失败'}
            description={updatedAt ? `上次成功同步：${new Date(updatedAt).toLocaleString()}` : '请检查 Server 登录与连接状态后重试。'}
            action={<WbButton className="btn-line" onClick={() => void load()}>重新同步</WbButton>}
          />
        )}
        <List
          className="projects-list"
          loading={loading && projects.length === 0}
          dataSource={projects}
          locale={{
            emptyText: (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={error ? '无法读取 Server 项目' : 'Server 中还没有可用项目'}>
                <WbButton className="btn-line" onClick={() => error ? void load() : void openServerConsole('projects')}>{error ? '重新同步' : '打开 Console'}</WbButton>
              </Empty>
            ),
          }}
          renderItem={(project) => (
            <List.Item className="my-proj" key={project.id}>
              <span className="my-proj-icon">☁️</span>
              <div className="my-proj-main">
                <div className="my-proj-title">
                  {project.name}
                  <Tag className="project-source is-server">Server 上下文</Tag>
                  {project.role && <Tag className="pj-rolebadge sm">{ROLE_LABEL[project.role] || project.role}</Tag>}
                </div>
                <div className={`my-proj-desc ${project.instruction ? '' : 'is-empty'}`.trim()}>
                  {project.instruction || '该项目没有额外执行指令'}
                </div>
                <div className="my-proj-meta">
                  <span>{project.skills.length} 个技能</span>
                  <span>{project.connectors.length} 个连接器</span>
                  <span>{project.knowledge_ids.length} 个知识库</span>
                </div>
              </div>
              <WbButton
                className="btn-dark"
                onClick={() => execute(project)}
              >
                {project.role === 'Viewer' ? '查看任务' : '查看任务与执行'}
              </WbButton>
            </List.Item>
          )}
        />
      </div>
    </section>
  )
}
