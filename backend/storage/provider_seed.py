"""内置大模型厂商渠道注册表（WB-128）。

替掉原型抄来的「假内置模型列表」（Auto/Hy3/GLM-5.2… + 假倍率，见 WB-124 说明）。这里是**真实厂商**：
每个自带确认过的 `base_url` + 对外提供的模型名；用户只需在设置里填该厂商的 **API Key** 即可真正调用
（凭据只存后端、按 owner 隔离、绝不回前端——铁律#4）。

- 本模块只放纯数据，不 import 本项目任何模块（避免循环依赖，仿 catalog_seed.py）。
- base_url + chat_path 拼成实际请求 URL：`{base_url}{chat_path}`。绝大多数厂商是标准的
  OpenAI 兼容 `/chat/completions`；个别非标（MiniMax）用 chat_path 覆盖，保证真能通（铁律#1）。
- models 是各家**公开文档**里的真实模型名；模型会上新/下线，前端支持按厂商增删（override 存 DB）。
  这些值是首屏预置，用户可自行调整；base_url 若某家有变，走「自定义模型」兜底或后续再改注册表。
"""
from __future__ import annotations

# id 须 ASCII 且稳定（作为选择键 `@{id}:{model}` 与 DB 主键的一部分）。
PROVIDERS: list[dict] = [
    {
        "id": "deepseek",
        "name": "DeepSeek 深度求索",
        "base_url": "https://api.deepseek.com/v1",
        "chat_path": "/chat/completions",
        "icon": "🐋",
        "color": "#4D6BFE",
        "key_hint": "sk-...",
        "site": "https://platform.deepseek.com",
        # WB-134：官方现役 v4 命名（旧 chat/reasoner 已过时）。
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    },
    {
        "id": "zhipu",
        "name": "智谱 AI · GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "chat_path": "/chat/completions",
        "icon": "Z",
        "color": "#3859FF",
        "key_hint": "id.secret",
        "site": "https://open.bigmodel.cn",
        # WB-134：按 model-overview 更新到现役 GLM 子集（含视觉 4.6v）。
        "models": ["glm-4.6", "glm-4.5-air", "glm-4-flash", "glm-4.6v"],
    },
    {
        "id": "minimax",
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        # 非标准端点：MiniMax 的 OpenAI 兼容对话在 /text/chatcompletion_v2（请求/响应仍是 OpenAI 形态）。
        "chat_path": "/text/chatcompletion_v2",
        "icon": "M",
        "color": "#E5484D",
        "key_hint": "eyJ... (JWT)",
        "site": "https://platform.minimaxi.com",
        "models": ["MiniMax-Text-01", "abab6.5s-chat"],
    },
    {
        "id": "moonshot",
        "name": "月之暗面 · Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "chat_path": "/chat/completions",
        "icon": "K",
        "color": "#17181C",
        "key_hint": "sk-...",
        "site": "https://platform.moonshot.cn",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k", "kimi-latest"],
    },
    {
        "id": "qwen",
        "name": "阿里 · 通义千问",
        # DashScope 的 OpenAI 兼容模式。
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "chat_path": "/chat/completions",
        "icon": "通",
        "color": "#615CED",
        "key_hint": "sk-...",
        "site": "https://bailian.console.aliyun.com",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo", "qwen-long", "qwen2.5-72b-instruct"],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "chat_path": "/chat/completions",
        "icon": "🤖",
        "color": "#10A37F",
        "key_hint": "sk-...",
        "site": "https://platform.openai.com",
        "models": ["gpt-4o", "gpt-4o-mini", "o1", "o1-mini", "gpt-4-turbo"],
    },
]

PROVIDERS_BY_ID: dict[str, dict] = {p["id"]: p for p in PROVIDERS}
DEFAULT_CHAT_PATH = "/chat/completions"

# 内置厂商「准确默认」表（WB-134）。key = model_id（小写匹配）。来自各厂商**官方文档**，只作可编辑默认；
# 用户覆盖最高优先，未列出的模型回退名字启发式（models.py _default_capabilities）。价格单位 = 每百万 token。
# input_cost = 缓存未命中输入价；input_cost_cached = 缓存命中输入价（DeepSeek 两者差 ~50×，故分开）。
# 来源：DeepSeek api-docs.deepseek.com（定价/思考/工具，2026）；智谱 docs.bigmodel.cn model-overview。
# 说明：智谱只给了能力矩阵未给价格 → 价留空；思考对 DeepSeek 是参数开关，此处记为「具备推理能力」。
MODEL_DEFAULTS: dict[str, dict] = {
    "deepseek-v4-flash": {
        "capabilities": ["text", "tools"], "input_cost": 1.0, "input_cost_cached": 0.02,
        "output_cost": 2.0, "context_window": 1_000_000, "currency": "CNY",
    },
    "deepseek-v4-pro": {
        "capabilities": ["text", "tools", "reasoning"], "input_cost": 3.0, "input_cost_cached": 0.025,
        "output_cost": 6.0, "context_window": 1_000_000, "currency": "CNY",
    },
    # 智谱 GLM：能力来自 model-overview（工具/推理/视觉标志）；官方定价未在所给文档 → 留空由用户补。
    "glm-4.6": {"capabilities": ["text", "tools", "reasoning"], "context_window": 200_000, "currency": "CNY"},
    "glm-4.5-air": {"capabilities": ["text", "tools", "reasoning"], "context_window": 128_000, "currency": "CNY"},
    "glm-4-flash": {"capabilities": ["text", "tools"], "context_window": 128_000, "currency": "CNY"},
    "glm-4.6v": {"capabilities": ["text", "image", "tools", "reasoning"], "context_window": 128_000, "currency": "CNY"},
}
