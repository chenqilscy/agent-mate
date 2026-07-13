---
id: WB-135
title: 补齐智谱 GLM 官方定价（文本+视觉，人民币/分档）+ seed 对齐现役旗舰 + 视觉模型补 image/video 能力
severity: P2
area: backend
status: fixed
origin: 既有实现
files:
  - backend/storage/provider_seed.py
  - src/components/composer/ModelConfigModal.tsx
created: 2026-07-13
---

## 背景

WB-134 给智谱留了价格空（当时读不到 JS 渲染的定价页）。用户贴来官方定价表（bigmodel.cn/pricing
「旗舰模型 → 文本模型 / 视觉理解」），人民币、每百万 tokens、**按输入长度分档**、带缓存命中价；
视觉表还标了**输入模态=图片/视频/文件/文本**。且表内现役是 GLM-5.2/4.7/4.5-Air/GLM-4.6V 等——
说明 seed 的 `glm-4.6` 也过时。

## 范围（重要）

只收 **chat 模型（文本模型 + 视觉理解）**——它们走 `/chat/completions`、是 Auto 选型对象。
**不收**多模态生成(GLM-Image/CogVideoX/Vidu)、语音(GLM-TTS/ASR/Voice/Realtime)、向量(Embedding)、
重排(Rerank)：这些走不同 API 端点（本应用 chat 运行时调不了），且按次/万字符/分钟计费，与「每百万
token 输入·输出价」schema 不符——硬塞成聊天模型属造假（铁律#1）。用户提供了这些页面，如实说明不纳入。

## 方案

- `MODEL_DEFAULTS` 补齐 GLM 文本+视觉各型号：能力（overview 矩阵的 tools/reasoning + 视觉表的 image/video）
  + 价格（**基础档=最短输入长度**的输入/输出/缓存命中价）+ 上下文 + 币种 CNY。单价 schema 存不下分档，
  用基础档价 + `note` 标注「价按输入长度分档」（诚实）。免费模型价记 0。
- seed 智谱模型对齐现役：`glm-5.2 / glm-4.7 / glm-4.5-air / glm-4.6v`。
- 前端：价格徽标 tooltip 带上 note（让分档提示可见）。

## 验证

- py_compile；TestClient：glm-5.2=8/28 cache2 1M、glm-4.7=2/8 cache0.4 200K(note 分档)、
  glm-4.6v 含 image+video 且 1/3 cache0.2、glm-4.7-flash 免费(0)；source=preset。
- Playwright：智谱卡片显现役型号 + 价格/能力徽标；tooltip 有分档说明。

## 处理记录（2026-07-13）

- **后端** `provider_seed.py`：
  - 智谱 seed 模型 → `glm-5.2 / glm-4.7 / glm-4.5-air / glm-4.6v`（对齐官方定价页现役旗舰；旧 glm-4.6 过时）。
  - `MODEL_DEFAULTS` 智谱段重写：**文本** glm-5.2/5.1/5-turbo/5/4.7/4.7-flashx/4.7-flash/4.5-air + **视觉** glm-5v-turbo/4.6v/4.6v-flashx/4.6v-flash。
    能力据 model-overview（tools/reasoning + 视觉 image/video）；价据官方表**基础档**（输入/输出/缓存命中，CNY/百万tok），
    分档者 note 标注、免费记 0。**只收 chat 模型**——生成/语音/向量/重排非 chat、按次计费，如实不纳入。
- **前端** `ModelConfigModal.tsx`：价格徽标 tooltip 追加 note（分档说明可见）。
- **验证**
  - py_compile / tsc / vite build 过。
  - TestClient(干净库)：智谱 seed=现役4型；glm-5.2=8/2/28·1M、glm-4.7=2/0.4/8·200K(note 分档)、
    glm-4.5-air=0.8/0.16/2、**glm-4.6v 含 image+video·1/0.2/3**；source=preset —— 断言过。
  - 硬重启 :8000 live spot-check：glm-4.7/4.5-air/4.6v 官方价正确加载；glm-5.2/5-turbo 因**用户库存在空的 custom 覆盖**
    显 None（source=custom，非 bug；点「恢复默认」即回 preset）——未动用户数据。
- commit：（待用户确认时提交）

