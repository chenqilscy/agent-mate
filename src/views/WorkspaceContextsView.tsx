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
            <h1>项目上下文</h1>
            <div className="sub">选择 Server 项目，把任务交给这台设备上的 Local Agent 执行</div>
            <WbButton className="btn-line" onClick={() => void openServerConsole('projects')}>在 Console 管理项目</WbButton>
          </div>
        </div>
        <Alert
          type="info"
          showIcon
          title="App 只使用项目上下文，不负责项目治理"
          description="新建项目、成员角色、计划、自动化和审计由 Server Console 统一管理；这里不保存第二份项目数据。"
        />
        <List
          className="projects-list"
          dataSource={projects}
          locale={{
            emptyText: (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Server 中还没有可用项目">
                <WbButton className="btn-line" onClick={() => void openServerConsole('projects')}>打开 Console</WbButton>
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
                disabled={project.role === 'Viewer'}
                onClick={() => execute(project)}
              >
                {project.role === 'Viewer' ? '只读上下文' : '开始本机任务'}
              </WbButton>
            </List.Item>
          )}
        />
      </div>
    </section>
  )
}
