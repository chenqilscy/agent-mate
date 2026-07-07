import { useEffect, useState } from 'react'
import { toast } from '../stores/toastStore'
import { useProjectStore } from '../stores/projectStore'
import { useUIStore } from '../stores/uiStore'
import { NewProjectModal } from '../components/project/NewProjectModal'
import { useCatalog } from '../stores/catalogStore'
import type { ProjectInfo } from '../lib/types'

// A shared project (M7 C2) carries the caller's role; owned projects show no badge.
const ROLE_LABEL: Record<string, string> = { Admin: '管理员', Member: '成员', Viewer: '只读' }

export function ProjectsView() {
  const projects = useProjectStore((s) => s.projects)
  const load = useProjectStore((s) => s.load)
  const setActive = useProjectStore((s) => s.setActive)
  const setView = useUIStore((s) => s.setView)
  const [modalOpen, setModalOpen] = useState(false)
  const { PROJ_TPL } = useCatalog()

  useEffect(() => { load() }, [load])

  // Open the project workbench (home), not straight into an execution (§11).
  const openProject = (p: ProjectInfo) => {
    setActive(p)
    setView('project')
  }

  return (
    <section className="view active" data-view="projects">
      <div className="page-scroll">
        <div className="ph">
          <div className="ph-l">
            <h1>项目</h1>
            <div className="sub">多人协同，打造超级团队</div>
            <button className="btn-line" onClick={() => setModalOpen(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>新建项目
            </button>
          </div>
          <svg className="ph-illus" viewBox="0 0 300 150" aria-hidden="true">
            <rect width="300" height="150" rx="12" fill="#F4FAF7" />
            <circle cx="70" cy="80" r="22" fill="#CFEADC" opacity=".6" />
            <circle cx="150" cy="70" r="26" fill="#16B37A" opacity=".18" />
            <circle cx="230" cy="82" r="20" fill="#BFE3F5" opacity=".6" />
            <rect x="120" y="30" width="60" height="30" rx="8" fill="#fff" stroke="#DDE7E1" />
            <path d="M132 45h36M132 52h24" stroke="#B7C6BD" strokeWidth="2" />
          </svg>
        </div>

        <div className="sec-row">
          <div className="sec-title">我的项目</div>
          <div className="search-box">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M21 21l-4-4" /></svg>
            <input placeholder="搜索项目" />
          </div>
        </div>
        <div id="myProjList">
          {projects.length === 0 && (
            <div className="my-proj" style={{ cursor: 'default', color: 'var(--text-3)' }}>
              <span className="t-ic" style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--brand-soft)', display: 'grid', placeItems: 'center', color: 'var(--brand-600)' }}>🧭</span>
              <div><div style={{ fontSize: 13.5, fontWeight: 700 }}>还没有项目</div><div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>点击「新建项目」开始</div></div>
            </div>
          )}
          {projects.map((p) => (
            <div className="my-proj" key={p.id} onClick={() => openProject(p)}>
              <span className="t-ic" style={{ width: 30, height: 30, borderRadius: 8, background: 'var(--brand-soft)', display: 'grid', placeItems: 'center', color: 'var(--brand-600)' }}>🤖</span>
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                  {p.name}
                  {p.role && p.role !== 'Owner' && <span className="pj-rolebadge sm">协作 · {ROLE_LABEL[p.role] || p.role}</span>}
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-3)' }}>添加于 {p.ago}</div>
              </div>
              <span className="mp-more" onClick={(e) => { e.stopPropagation(); toast('项目菜单') }}>⋮</span>
            </div>
          ))}
        </div>

        <div className="sec-title">从模版创建</div>
        <div className="card-grid g4">
          {PROJ_TPL.map(([ic, n, d]) => (
            <div className="tpl" key={n} onClick={() => setModalOpen(true)}>
              <span className="t-ic">{ic}</span>
              <div>
                <div className="t-n">{n}</div>
                <div className="t-d">{d}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <NewProjectModal open={modalOpen} onClose={() => setModalOpen(false)} onCreated={(p) => { setModalOpen(false); openProject(p) }} />
    </section>
  )
}
