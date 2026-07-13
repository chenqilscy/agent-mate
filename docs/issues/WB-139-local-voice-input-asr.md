---
id: WB-139
title: 语音输入落地 —— 本地 ASR 小模型（faster-whisper），按住说话松开转写
severity: P2
area: fullstack
status: fixed
origin: 既有实现
files:
  - src/components/composer/Composer.tsx:216
  - backend/routers/asr.py
  - backend/config.py
  - backend/requirements.txt
created: 2026-07-14
---

## 问题

Composer 底部的麦克风按钮是个桩：点击只弹 `toast('语音输入')`
（[Composer.tsx:216](../../src/components/composer/Composer.tsx#L216)），没有接任何语音识别。
语音输入功能从未实现。

## 触发场景

首页/会话页输入框 → 点麦克风图标 → 只弹一条「语音输入」toast，无任何录音/识别行为。

## 影响

一个可见的入口是死的（伪功能，违背铁律#1「不模拟」的精神——按钮在但不干活）。
用户期望能说话转文字。P2：非核心链路，但是显式暴露的空壳入口。

## 建议修法

**方向（已与用户确认）**：本地 ASR 小模型 + 「按住说话、松开转写」。
不走浏览器 Web Speech API（Chrome 底层发云端、违反 local-first，Tauri WebView2 未必可用）。

数据流：
```
麦克风按钮 (按住)
  → 浏览器 MediaRecorder 录一段 webm/opus
  → 松开 → POST multipart /api/asr/transcribe
  → 后端本地 faster-whisper(base) 转文字
  → 返回 { text, language } → 填进输入框（可编辑再发）
```

- **后端**：新增 `backend/routers/asr.py`，`POST /api/asr/transcribe` 收音频字节，
  懒加载单例 `faster-whisper` base 模型（CT2，CPU int8），`decode` 走 PyAV（webm/opus 直解，无需外部 ffmpeg），
  返回转写文本。`GET /api/asr/status` 报告是否可用（依赖是否装、模型是否就绪）。
  依赖未装时端点诚实返回 503 + 提示 `pip install faster-whisper`（铁律#1：不假装能用）。
  模型缓存放 `DATA_DIR/models/whisper`（首次使用触发下载，需联网一次）。
  config 加 `ASR_MODEL`（默认 base）/`ASR_ENABLED`（默认开）/`ASR_DEVICE`/`ASR_COMPUTE_TYPE` 开关。
- **前端**：Composer 麦克风按钮改真录音——pointerDown 起录、pointerUp/Leave 停录并转写；
  录音态按钮红色脉冲、转写态 loading；权限拒绝/后端不可用给 toast。转写结果**追加**到 textarea 现有文本。
  首帧短按（未成功起流）不误触发。api.ts 加 `transcribeAudio(blob)`（FormData + authHeaders，仿 uploadFile）。

密钥/音频不出本机（local-first，铁律#4 精神）。

## 验证

- 后端：`python -m py_compile backend/routers/asr.py backend/config.py`；
  `GET /api/asr/status` 返回可用性；构造/录一段中文音频 POST /api/asr/transcribe 拿到合理中文文本。
- 前端：`npx tsc --noEmit` 过；浏览器实测按住麦克风说一句 → 松开 → 文本进输入框；
  明暗双主题看录音态样式；拒绝麦克风权限/后端未装依赖时给出友好提示不崩。

## 处理记录（2026-07-14）

- **后端**
  - `config.py`：加 ASR 配置项（`ASR_ENABLED`/`ASR_MODEL`=base/`ASR_DEVICE`=cpu/`ASR_COMPUTE_TYPE`=int8/`ASR_MODEL_DIR`）。
  - 新增 `routers/asr.py`：`GET /api/asr/status`（轻探测依赖是否装，不触发下载）+ `POST /api/asr/transcribe`
    （收原始音频字节，非 multipart）。模型懒加载进程内单例（线程锁），加载+转写都 `asyncio.to_thread`
    丢线程池不阻塞事件循环（WB-002 教训）；解码走 faster-whisper 自带 PyAV，webm/opus 直解无需外部 ffmpeg。
    依赖没装/模型没就绪 → 诚实 503（铁律#1，不返回假文本）；空体 400、超 8MB 413。
  - `main.py`：import + `include_router(asr.router)`。`requirements.txt` 加 `faster-whisper==1.1.1` + `requests`
    （1.1.1 未自动拉但 utils 需要）。`.gitignore` 加 `backend/models/`（模型缓存 ~145MB 不入库）。
- **前端**
  - `lib/api.ts`：加 `asrStatus()` + `transcribeAudio(blob)`（把 Blob 直接作 body 发，带 Bearer token，仿 uploadFile；
    503 把 detail 带出来）。
  - 新增 `components/composer/useVoiceInput.ts`：按住说话 hook——pointerDown 起录 / pointerUp·Leave·Cancel 停录，
    getUserMedia + MediaRecorder 录 webm/opus，松开 POST 转写、结果回填；挂载时探测可用性；
    权限拒绝/不可达/后端不可用均 toast 兜底，getUserMedia 未就绪就松手也能正确停。
  - `Composer.tsx`：麦克风按钮从 `toast('语音输入')` 桩改为真录音（pointer 事件 + 录音态 class + disabled）；
    转写文本追加到 textarea 现有内容。`styles/app.css`：`.cicon.mic.rec` 红脉冲（复用全站红 #E5484D，明暗皆宜）、
    `.busy` 图标旋转、`.cicon:disabled` 态。
- **验证**
  - 后端 `py_compile` 过；`GET /api/asr/status` → `{enabled:true,available:true,model:base}`；
    SAPI 合成中英文语音（EN「The quick brown fox…」/ZH「你好，我想帮我写一份季度工作总结报告。」）
    经 PyAV 转成**浏览器同款 webm/opus**，HTTP POST `/api/asr/transcribe` 得准确转写（EN 逐字对、ZH 完全对）；
    空体→400。首次调用触发 base 模型下载到 `backend/models/whisper`，暖调用 <1s。
  - 前端 `tsc --noEmit` 过；MCP 浏览器被并发会话占用，改用独立 headless chromium + Node CDP 驱动：
    注入假 getUserMedia/MediaRecorder（吐真 webm blob）按住/松开麦克风，走**真后端**——
    title=「按住说话，松开转写」、录音态 class=`cicon mic rec`、`busySeen=true`、textarea 落
    「你好,我想帮我写一份季度工作总结报告。」、结束回 `cicon mic`；明暗双主题录音态截图均正常。
- 未提交（用户未要求）。共享工作树有并发会话在改 `main.py`（加了 `knowledge` 路由），提交须按 hunk 显式文件暂存。
