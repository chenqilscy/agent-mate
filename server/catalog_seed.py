"""AgentMate Server 首次启动的自有技能目录种子。

运行时只读 catalog_items；本文件只负责把产品随附的默认技能写入 Server 权威目录。
第三方 SkillHub 数据、Key 与技能包不得进入这里。
"""
from __future__ import annotations

from typing import Any


DEFAULT_APP_SKILLS: list[dict[str, Any]] = [
    {"slug": "web-access", "name": "Web Access（浏览器自动化）", "icon": "🌐", "category": "开发编程", "description": "联网取材：按 URL 抓取网页正文再作答，并注明来源链接。", "instructions": "需要联网信息时，用 web_fetch 抓取网页内容再作答；引用来源 URL。", "tools": ["web_fetch"], "source": "Server"},
    {"slug": "markitdown", "name": "MarkItDown", "icon": "📝", "category": "内容创作", "description": "把网页 / 文档整理成干净、结构化的 Markdown。", "instructions": "把网页 / 文档整理成干净、结构化的 Markdown：用 html_to_markdown 抓取并转换网页，再按需精修标题层级、列表与表格。", "tools": ["html_to_markdown"], "source": "Server"},
    {"slug": "skill-creator-guide", "name": "技能创建指南", "icon": "🧩", "category": "开发编程", "description": "通过对话梳理技能用途、触发场景与执行指令，并安装为本机技能。", "instructions": "帮助用户创建自定义技能：先澄清用途、触发场景、输入输出与约束，整理出稳定英文 slug、名称、描述和完整 Markdown 指令；信息足够后必须调用 create_local_skill 真正创建并安装，不要只给模板或假装已创建。", "tools": ["create_local_skill"], "source": "Server"},
    {"slug": "word-doc", "name": "Word 文档生成", "icon": "📄", "category": "办公效率", "description": "以规范的长文档结构组织输出：标题层级、要点、表格与结论。", "instructions": "以规范的长文档结构组织输出：清晰的标题层级、要点、必要的表格与结论。", "tools": [], "source": "Server"},
    {"slug": "excel-csv", "name": "Excel 文件处理", "icon": "📊", "category": "数据分析", "description": "对工作区里的 CSV 做行列/数值列统计，基于真实数据作答。", "instructions": "处理表格数据时：对工作区里的 CSV 用 analyze_csv 获取行列/数值列统计，再基于真实数据作答；输出用清晰的表格结构。", "tools": ["analyze_csv"], "source": "Server"},
    {"slug": "stock-analyzer", "name": "股票综合分析器", "icon": "📈", "category": "商业运营", "description": "分基本面 / 消息面 / 资金面三维展开，结论先行并提示风险。", "instructions": "做股票分析时分三维展开：基本面、消息面、资金面，结论先行并提示风险。", "tools": [], "source": "Server"},
]
