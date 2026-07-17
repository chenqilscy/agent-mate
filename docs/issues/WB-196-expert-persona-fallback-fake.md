---
id: WB-196
title: 专家人格也有兜底话术伪装 —— persona_for 对未知专家编一句「以「X」的专业身份作答」
severity: P2
area: backend
status: open
origin: 既有实现
files:
  - backend/agent/experts.py:13
  - backend/storage/db.py:663
created: 2026-07-17
---

## 问题

`agent/experts.py:13`：

```python
def persona_for(name: str) -> str:
    persona = db.builtin_persona(name)
    return persona if persona else f"以「{name}」的专业身份与专长作答。"
```

这与 WB-179 刚从技能侧删掉的兜底话术（`f"运用「{name}」技能的专长完成相关任务。"`）
**是同一类伪装**：目录里任何一张专家卡，哪怕后端没有它的人格定义，也会被编一句话，
让 UI 上「已召唤 XX 专家」看起来生效了 —— 而 agent 收到的只是把卡片名字复述一遍的空话。

`runtime.py:308-310` 的注入：
```python
f"- {custom_personas.get(n) or persona_for(n)}" for n in active_experts
```
`persona_for` 永不返回空，所以**未知专家与真专家在 system_prompt 里长得一样**，
且 SSE 的 loadout 事件照报「专家 X」已加载 —— 用户无从分辨。

## 触发场景

召唤一个 `catalog_experts` 里没有人格定义的专家（或人格被运营清空 / 该行被 `enabled=0`）
→ system_prompt 出现「- 以「XX」的专业身份与专长作答。」→ 无任何真实人格影响回答，
但 UI 全程显示已召唤。

## 影响

P2，违反铁律#1（同 WB-179 的技能侧）。规模待测：需查 `catalog_experts` 里有多少 enabled 行
`persona` 为空、以及前端 `EXP_GRID`/`NP_EXPERTS` 里有多少名字在库里查不到。

注：用户已明确让「专家」功能靠后（暂时跳过其自动化测试），故本条**登记不立即处理**。

## 建议修法

照 **WB-179** 在技能侧的做法逐字复刻（那套已实测跑通）：

1. `persona_for` 改返回 `str | None`，删掉兜底话术；
2. `runtime.py` 只注入解析到的，解析不到的收进 `experts_skipped`，
   在 loadout 事件里如实报「专家未就绪 X（无人格定义）」
   —— 同 `mcp_skipped`（连接器）/ `skills_skipped`（技能，WB-179）的既有范式；
3. `lines` 为空时连「# 专家人格」段都不加。

## 验证

- 召唤一个库里无人格的专家 → system_prompt **无**「以「X」的专业身份」字样、无「# 专家人格」段；
  SSE 报「专家未就绪 X（无人格定义）」；
- 回归：召唤真专家（`catalog_experts` 有 persona 的）→ 人格照常注入，loadout 正常列出；
- 自定义专家（WB-049 的 `custom_personas`）路径不受影响。
