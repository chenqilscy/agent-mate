// catalogStore — 橱窗目录（WB-060）。
//
// 普通橱窗以 catalog.ts 为静态兜底；技能推荐由 catalog_skills 真定义表生成。
// 第三方 SkillHub 由本地 App 直接读取真实 rankings，不接受 Server 镜像（WB-215）。
import { create } from 'zustand'
import { api, TOKEN_KEY } from '../lib/api'
import type { SkillCard } from '../lib/types'
import * as C from '../data/catalog'
import { useSkillStore } from './skillStore'

export interface SkillCat { key: string; name: string; nameEn?: string; sortOrder?: number; count: number }

// 由 API 供给的橱窗键（与后端 storage/db.showcase_all 对齐；不含 SKILLHUB_*）。
type Catalog = Pick<
  typeof C,
  | 'QUICK' | 'PROJ_TPL' | 'EXP_SCENES' | 'EXP_CATS' | 'EXP_GRID' | 'EXP_TEAMS'
  | 'SK_CATS' | 'SK_GRID' | 'CONNS' | 'CONN_META' | 'AUTO' | 'INSTALLED'
  | 'NP_TPLS' | 'NP_CONNS' | 'NP_EXPERTS' | 'READY_CONNECTORS' | 'NEEDS_TOKEN_CONNECTORS'
  | 'INSP_CATS' | 'INSP' | 'KB_TPLS'
>

const FALLBACK: Catalog = {
  QUICK: C.QUICK, PROJ_TPL: C.PROJ_TPL, EXP_SCENES: C.EXP_SCENES, EXP_CATS: C.EXP_CATS,
  EXP_GRID: C.EXP_GRID, EXP_TEAMS: C.EXP_TEAMS, SK_CATS: C.SK_CATS,
  SK_GRID: C.SK_GRID, CONNS: C.CONNS, CONN_META: C.CONN_META, AUTO: C.AUTO,
  INSTALLED: C.INSTALLED, NP_TPLS: C.NP_TPLS, NP_CONNS: C.NP_CONNS, NP_EXPERTS: C.NP_EXPERTS,
  READY_CONNECTORS: C.READY_CONNECTORS, NEEDS_TOKEN_CONNECTORS: C.NEEDS_TOKEN_CONNECTORS,
  INSP_CATS: C.INSP_CATS, INSP: C.INSP, KB_TPLS: C.KB_TPLS,
}

// 后端把 Set 序列化成数组；这两项消费方用 .has()，回填时还原为 Set。
const SET_KEYS = new Set(['READY_CONNECTORS', 'NEEDS_TOKEN_CONNECTORS'])

interface CatalogState extends Catalog {
  loaded: boolean
  // WB-215：本地 App 直接读取的第三方 SkillHub 商店元数据。
  skillMarketplace: SkillCard[]
  skillCats: SkillCat[]
  load: () => Promise<void>
}

export const useCatalogStore = create<CatalogState>((set) => ({
  ...FALLBACK,
  loaded: false,
  skillMarketplace: [],
  skillCats: [],
  load: async () => {
    try {
      const raw = (await api.getCatalog()) as Record<string, unknown>
      const next: Record<string, unknown> = {}
      for (const k of Object.keys(FALLBACK)) {
        if (raw[k] === undefined) continue // 后端未提供某项 → 保留兜底
        next[k] = SET_KEYS.has(k) ? new Set(raw[k] as string[]) : raw[k]
      }
      set({ ...(next as Partial<CatalogState>), loaded: true })
    } catch {
      set({ loaded: true }) // 后端未连：保留静态兜底，不白屏
    }
  },
}))

// 登录态下触发一次本地 backend → Server 下行 pull（仅 AgentMate 自有目录与协作配置）。
let serverPulled = false
async function syncFromServer(): Promise<void> {
  if (serverPulled) return
  serverPulled = true
  if (!localStorage.getItem(TOKEN_KEY)) return // 未登录 → 无 Server token，跳过
  try {
    const r = await api.serverPull()
    if (r.server) {
      await useCatalogStore.getState().load()
      await useSkillStore.getState().load(true)
    }
  } catch { /* 未接 Server / 不可达：保留本地兜底 */ }
}

// 第三方市场始终从本地 App 后端直读真实 SkillHub 排行，与 Server 登录/同步状态无关（WB-215）。
async function loadSkillMarketplace(): Promise<void> {
  try {
    const r = await api.skillRankings('hot') // hot=较广的真实排行；离线/无 CLI → 抛错，回退静态
    const cards: SkillCard[] = (r.skills || []).map((c) => ({
      ...c,
      skillhub_category: c.category,
      skillhub_category_name: c.category || '其他',
    }))
    if (!cards.length) return
    const counts: Record<string, number> = {}
    for (const c of cards) { const k = c.skillhub_category ?? ''; counts[k] = (counts[k] ?? 0) + 1 }
    const cats: SkillCat[] = Object.entries(counts)
      .map(([key, count]) => ({ key, name: key, count }))
      .sort((a, b) => b.count - a.count)
    useCatalogStore.setState({ skillMarketplace: cards, skillCats: cats })
  } catch { /* 离线 / 无 CLI：保持空，页面展示诚实空态 */ }
}

// 便捷 hook：取整份目录（组件里按需解构，如 const { EXP_GRID } = useCatalog()）。
export function useCatalog(): Catalog {
  return useCatalogStore((s) => s)
}

// 启动即拉取一次（兜底已就绪，拉到后 set() 触发消费组件重渲染；失败保留兜底、不白屏）。
// Server 下行与第三方市场并行、互不覆盖；市场只走本地 App（WB-215）。
void (async () => {
  await useCatalogStore.getState().load()
  await Promise.all([syncFromServer(), loadSkillMarketplace()])
})()
