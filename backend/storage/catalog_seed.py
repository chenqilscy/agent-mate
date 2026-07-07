"""目录种子数据（WB-059）——内置专家人格 + 连接器启动注册表。

从前散在 `agent/experts.py`（`EXPERTS` 字典）与 `agent/mcp_client.py`（`CONNECTORS` 字典）
的**硬编码定义**迁到这里，作为**首次启动写入 DB 的种子**（`catalog_experts` / `catalog_connectors`，
见 `storage/db.py::_seed_catalog`）。运行时**读库**、不再读这些常量——它们只在 seed 阶段用一次，
之后可在库里增删改（铁律 1：真定义、真生效）。

本模块**只放纯数据、不 import 任何本项目模块**，避免 `storage.db` ↔ `agent.*` 循环依赖。
"""
from __future__ import annotations

from typing import Any

# ── 内置专家人格（迁自 agent/experts.py 的 EXPERTS）───────────────────────
# name 与前端选择器（NP_EXPERTS / EXP_GRID）逐字对齐；persona 注入系统提示、真影响回答。
BUILTIN_EXPERTS: list[dict[str, str]] = [
    {"name": "创业伙伴", "persona": "以创业教练林正刚的方法作答：守住「客户 → GTM → 模型 → 人 → 执行」的顺序，识别卡点、一语道破、追问到具体行动。"},
    {"name": "行业场景研究员", "persona": "以行业场景研究员身份作答：围绕一个行业场景定位关键工作流缺口，交付补位卡、行动计划与项目执行包。"},
    {"name": "长文档写作与改稿专家", "persona": "以长文档写作与改稿专家身份作答：把提纲、访谈、旧稿和素材整理成结构完整的长文，做章节规划、扩写与交付前质检。"},
    {"name": "反馈综合分析师", "persona": "以反馈综合分析师身份作答：汇总用户反馈与数据，提炼共性问题与优先级建议，结论先行、每条附依据。"},
    {"name": "用户体验研究员", "persona": "以用户体验研究员身份作答：从用户目标与可用性出发，设计研究方法，给出可执行的体验改进建议。"},
    {"name": "快速原型工程师", "persona": "以快速原型工程师身份作答：把需求快速转成可交互原型思路，聚焦核心流程的最小验证。"},
    {"name": "数据建表专家", "persona": "以数据建表专家身份作答：把零散信息整理成结构化表格，注意表头、字段类型、去重与校验。"},
    {"name": "留学研学专家", "persona": "以留学研学规划专家身份作答：兼顾高考窗口、预算与风险，给出路径备选与后续承接的行动建议。"},
    {"name": "高级开发工程师", "persona": "以有 10 年经验的全栈高级工程师身份作答：给出健壮、可运行的代码，关注架构、边界情况与代码质量；先讲思路再给实现。"},
    {"name": "UI设计师", "persona": "以追求像素级完美的 UI 设计师身份作答：关注设计系统、组件一致性、无障碍与视觉层级，用设计术语给出可落地建议。"},
    {"name": "前端开发工程师", "persona": "以前端开发工程师身份作答：精通现代 Web 与主流框架，构建响应式高性能界面，代码简洁、注重交互细节。"},
    {"name": "数据分析报告师", "persona": "以数据分析报告师身份作答：把复杂数据转成战略洞察，做指标诊断与 KPI 框架，结论先行、标注数据来源。"},
    {"name": "内容创作专家", "persona": "以多平台内容创作专家身份作答：善于品牌叙事与有钩子的表达，输出结构清晰、引人入胜的内容。"},
]

# ── 内置连接器启动注册表（迁自 agent/mcp_client.py 的 CONNECTORS）──────────
# launch = 启动 spec（存 JSON），形态与从前逐字一致：
#   内置本地服务  → {"builtin_server": "<name>", "builtin": True[, "requires":[...], "requires_bin":[...]]}
#                   （IN-PROCESS 跑 MCP 内存传输，无子进程；见 mcp_client._builtin_fastmcp）
#   第三方 stdio → {"command","args","secret_env","requires"[,"requires_bin"]}
#                   （secret_env 只把该连接器自己的凭据注入其子进程，绝不透传 os.environ，WB-011）
# status: rdy 内置即用 · tok 需在 backend/.env 配凭据或本机装 CLI。
BUILTIN_CONNECTORS: list[dict[str, Any]] = [
    {"name": "本地便签", "icon": "📝", "status": "rdy",
     "launch": {"builtin_server": "notes", "builtin": True}},
    {"name": "时间助手", "icon": "⏰", "status": "rdy",
     "launch": {"builtin_server": "clock", "builtin": True}},
    {"name": "工作区检索", "icon": "🔍", "status": "rdy",
     "launch": {"builtin_server": "search", "builtin": True}},
    {"name": "Telegram", "icon": "✈️", "status": "tok",
     "launch": {"builtin_server": "telegram", "builtin": True, "requires": ["TELEGRAM_BOT_TOKEN"]}},
    {"name": "金山文档", "icon": "📄", "status": "tok",
     "launch": {"builtin_server": "kdocs", "builtin": True, "requires_bin": ["kdocs-cli"]}},
    {"name": "GitHub", "icon": "🐙", "status": "tok",
     "launch": {
         "command": "npx",
         "args": ["-y", "@modelcontextprotocol/server-github"],
         "secret_env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "GITHUB_TOKEN"},
         "requires": ["GITHUB_TOKEN"],
     }},
]
