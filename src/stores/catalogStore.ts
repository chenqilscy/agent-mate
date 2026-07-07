// catalogStore — 橱窗目录（WB-060）。
//
// 原 src/data/catalog.ts 的静态商品卡改由后端 /api/catalog 供给；此处以 catalog.ts 为「静态兜底」
// 初始值，启动时用接口数据覆盖（后端未连则保持兜底，绝不白屏）。zustand 响应式：接口数据到达后
// 消费组件自动重渲染（数据与迁移前逐字一致，无可见变化）。
// 注意：SKILLHUB_*（技能商店浏览列表）不在此——WB-064 负责其实时数据源，其消费仍从 data/catalog.ts 直取。
import { create } from 'zustand'
import { api, TOKEN_KEY } from '../lib/api'
import type { SkillCard } from '../lib/types'
import * as C from '../data/catalog'

// Hub 镜像的 SkillHub 场景分类（WB-070）：来自 Hub /api/v1/categories 快照 + 每类计数。
export interface SkillCat { key: string; name: string; nameEn?: string; sortOrder?: number; count: number }

// 由 API 供给的橱窗键（与后端 storage/db.showcase_all 对齐；不含 SKILLHUB_*）。
type Catalog = Pick<
  typeof C,
  | 'QUICK' | 'PROJ_TPL' | 'EXP_SCENES' | 'EXP_CATS' | 'EXP_GRID' | 'EXP_TEAMS'
  | 'SK_RECO' | 'SK_CATS' | 'SK_GRID' | 'CONNS' | 'CONN_META' | 'AUTO' | 'INSTALLED'
  | 'NP_TPLS' | 'NP_CONNS' | 'NP_EXPERTS' | 'READY_CONNECTORS' | 'NEEDS_TOKEN_CONNECTORS'
  | 'INSP_CATS' | 'INSP'
>

const FALLBACK: Catalog = {
  QUICK: C.QUICK, PROJ_TPL: C.PROJ_TPL, EXP_SCENES: C.EXP_SCENES, EXP_CATS: C.EXP_CATS,
  EXP_GRID: C.EXP_GRID, EXP_TEAMS: C.EXP_TEAMS, SK_RECO: C.SK_RECO, SK_CATS: C.SK_CATS,
  SK_GRID: C.SK_GRID, CONNS: C.CONNS, CONN_META: C.CONN_META, AUTO: C.AUTO,
  INSTALLED: C.INSTALLED, NP_TPLS: C.NP_TPLS, NP_CONNS: C.NP_CONNS, NP_EXPERTS: C.NP_EXPERTS,
  READY_CONNECTORS: C.READY_CONNECTORS, NEEDS_TOKEN_CONNECTORS: C.NEEDS_TOKEN_CONNECTORS,
  INSP_CATS: C.INSP_CATS, INSP: C.INSP,
}

// 后端把 Set 序列化成数组；这两项消费方用 .has()，回填时还原为 Set。
const SET_KEYS = new Set(['READY_CONNECTORS', 'NEEDS_TOKEN_CONNECTORS'])

interface CatalogState extends Catalog {
  loaded: boolean
  // WB-070：Hub 镜像的 SkillHub 商店（已连 Hub 并下行 pull 后有值）。空 = 未接 Hub → 前端回退静态 SKILLHUB_*。
  skillMirror: SkillCard[]
  skillCats: SkillCat[]
  load: () => Promise<void>
}

export const useCatalogStore = create<CatalogState>((set) => ({
  ...FALLBACK,
  loaded: false,
  skillMirror: [],
  skillCats: [],
  load: async () => {
    try {
      const raw = (await api.getCatalog()) as Record<string, unknown>
      const next: Record<string, unknown> = {}
      for (const k of Object.keys(FALLBACK)) {
        if (raw[k] === undefined) continue // 后端未提供某项 → 保留兜底
        next[k] = SET_KEYS.has(k) ? new Set(raw[k] as string[]) : raw[k]
      }
      // WB-070：Hub SkillHub 镜像——category='skill' 是商店卡数组；'skill-category' 是 [{items:[12 类]}] 骨架。
      // 这两类不在静态 catalog.ts 里（带连字符、非导出键），故独立承载；后端未下发则保持空、前端回退静态。
      const mirror = Array.isArray(raw['skill']) ? (raw['skill'] as SkillCard[]) : []
      const taxRow = Array.isArray(raw['skill-category']) ? (raw['skill-category'] as Array<{ items?: SkillCat[] }>)[0] : undefined
      const cats = taxRow && Array.isArray(taxRow.items) ? taxRow.items : []
      set({ ...(next as Partial<CatalogState>), skillMirror: mirror, skillCats: cats, loaded: true })
    } catch {
      set({ loaded: true }) // 后端未连：保留静态兜底，不白屏
    }
  },
}))

// 登录态下触发一次本地 backend → Hub 下行 pull（把 Hub SkillHub 镜像等拉进本地 /api/catalog），
// 拉到后重载目录并进（WB-070）。未接 Hub / 未登录 → 静默，保留本地兜底。只跑一次，避免循环。
let hubPulled = false
async function syncFromHub(): Promise<void> {
  if (hubPulled) return
  hubPulled = true
  if (!localStorage.getItem(TOKEN_KEY)) return // 未登录 → 无 Hub token，跳过
  try {
    const r = await api.hubPull()
    if (r.hub && (r.catalog ?? 0) > 0) await useCatalogStore.getState().load()
  } catch { /* 未接 Hub / 不可达：保留本地兜底 */ }
}

// 便捷 hook：取整份目录（组件里按需解构，如 const { EXP_GRID } = useCatalog()）。
export function useCatalog(): Catalog {
  return useCatalogStore((s) => s)
}

// 启动即拉取一次（兜底已就绪，拉到后 set() 触发消费组件重渲染；失败保留兜底、不白屏）。
// 随后触发一次 Hub 下行 pull，把 Hub 镜像目录（含 SkillHub 369 技能）并进来（WB-070）。
void useCatalogStore.getState().load().then(syncFromHub)
