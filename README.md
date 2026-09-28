# 食鉴 NutriLens

上传或拍摄一张食物照片，识别菜品名称、主要食材与份量，估算营养成分，并给出中立、尊重用户的饮食参考。

前后端分离：**Vue 3 + Vite + TypeScript + Pinia** 前端，**FastAPI + SQLAlchemy + SQLite** 后端，多模态大模型通过 **OpenAI 兼容接口** 调用。

---

## 1. 快速开始

需要 Node.js ≥ 20.19 与 Python ≥ 3.10（本项目在 Node 24 / Python 3.14 上验证）。

### 后端

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS / Linux
cp .env.example .env
./.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8010
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

打开 <http://localhost:5183>。五个页面：

| 页面 | 作用 |
|---|---|
| **识别** | 单次分析：上传 1–4 张照片，出一份结果卡 |
| **对话** | 多轮：先传照片识别，再就这一餐继续追问 |
| **历史** | 单次分析的历史记录（可逐条删除） |
| **画像** | 饮食画像（过敏原、忌口、偏好），只存在本机浏览器 |
| **关于** | 隐私说明与能力边界 |

**不配置 API Key 也能完整跑通**：后端检测到 `LLM_API_KEY` 为空时会自动切到内置 Mock，页面顶部会显示「演示模式」横幅，返回的是内置示例数据。

### 跑测试

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest      # 157 个测试
cd frontend && npm run type-check                        # vue-tsc
```

---

## 2. 假设与默认值

规格里没有明确的地方做了如下假设，全部可在 `backend/.env` 覆盖。

| 项 | 默认值 | 说明 |
|---|---|---|
| 后端端口 | **8010** | 本机 8000 已被其他项目占用，故改用 8010 |
| 前端端口 | **5183** | 本机 5173 已被其他项目占用 |
| 上传大小上限 | 10 MB / 张，合计 20 MB | 前端先压缩，后端流式读取时硬截断 |
| 允许格式 | JPG / PNG / WebP | **以 Pillow 实际解码结果为准**，不信任扩展名与 Content-Type |
| 图片张数 | 最多 4 张 | 超出直接拒绝并提示 |
| 像素上限 | 5000 万 | 超出直接拒绝，防解压炸弹 |
| 前端压缩 | 单图 1600px、多图 1024px，质量 0.8 | 后端按同样的规则再压一次 |
| 默认模型 | `qwen-vl-max-latest` | DashScope OpenAI 兼容端点 |
| 思考模式 | **关闭** | 参数名可配（Qwen 系为 `enable_thinking`） |
| 低置信度阈值 | 0.55 | 低于此值前端固定提示「可能识别不准」 |
| 无 Key 行为 | 自动降级 Mock | 也可用 `LLM_PROVIDER=mock` 强制 |

改端口时需同步改 `frontend/vite.config.ts` 的 proxy 目标（或用 `BACKEND_PORT` 环境变量启动 Vite）。

---

## 3. 配置

`backend/.env` 由 `.env.example` 复制而来。**API Key 只存在于后端**，前端拿不到也不需要。

关键项：

| 变量 | 作用 |
|---|---|
| `LLM_PROVIDER` | `auto`（默认，有 Key 走真实接口）/ `openai_compat`（强制真实，无 Key 直接启动失败）/ `mock` |
| `LLM_BASE_URL` | 换厂商只需改这里，例如 OpenAI、vLLM、其他兼容网关 |
| `LLM_MODEL` | 模型名 |
| `LLM_API_KEY` | 密钥。留空即演示模式 |
| `LLM_ENABLE_THINKING` | 推理模式开关，默认 `false` 以降低首字延迟 |
| `LLM_THINKING_PARAM` | 思考开关的参数名。**填了值就每次显式下发布尔值**（`false` 也发），这是真正关掉思考的唯一方式；留空则完全不提该字段，适合不接受未知参数的厂商。详见 §10 |
| `LLM_JSON_MODE` | 是否要求 `response_format=json_object`。个别模型不支持时置 `false`，解析器仍会从自由文本里抽取 JSON |
| `LLM_REQUEST_USAGE` | 流式请求末尾附带 token 用量，用于诊断思考模式是否真的关掉了。厂商拒绝该参数时置 `false` |
| `MAX_IMAGES` | 单次最多上传几张（默认 4） |
| `MULTI_IMAGE_MAX_EDGE` | 多图时单张的边长上限（默认 1024）。多一张图就多一份 prefill，靠降分辨率把预算让出来 |
| `MAX_TOTAL_UPLOAD_MB` | 一次请求所有图片的合计上限（默认 20），避免 4 张各自顶到单张上限 |
| `MAX_HISTORY_TURNS` | 对话回放给模型的消息条数（默认 8）。第一轮的分析永远保留，是整段对话的锚点 |
| `CORS_ORIGINS` | 前端来源，逗号分隔 |

> `LLM_PROVIDER=openai_compat` 且没有 Key 时，后端会**拒绝启动**并给出明确报错，而不是静默返回假数据——演示数据绝不能和真实结果混淆。

---

## 4. 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 服务状态、当前 provider、是否演示模式 |
| GET | `/api/config` | 公开运行时配置（上限、模式列表、声明文案）——前端不硬编码任何限制 |
| POST | `/api/analyze` | `multipart(files[], mode, note?, profile?)` → 完整 `AnalysisResult` |
| POST | `/api/analyze/stream` | 同上入参 → SSE 流 |
| GET | `/api/history?limit=&offset=` | 单次分析历史 |
| GET / DELETE | `/api/history/{id}` | 单条详情 / 删除 |
| POST | `/api/conversations` | `{mode}` → 建一个空会话，立即返回 id |
| POST | `/api/conversations/{id}/turns/stream` | `multipart(files[]?, message, profile?)` → SSE 流 |
| GET | `/api/conversations?limit=&offset=` | 会话列表 |
| GET / DELETE | `/api/conversations/{id}` | 会话详情（含全部轮次）/ 删除 |

`mode` 取值 `quick` | `detailed`；`note` ≤300 字；`message` ≤1000 字；`files` 最多 4 张。

**为什么建会话和第一轮分开**：第一轮要 10 秒以上。先建会话拿到 id（毫秒级返回），再用 SSE 打第一轮，前端从第一秒就有进度反馈，而不是干等一个非流式响应。

**所有错误**都返回统一信封，不会是裸堆栈：

```json
{ "error": { "code": "invalid_image", "message": "这张图片无法识别，可能已损坏或不是有效的图片文件。",
             "hint": "请换一张照片，或重新拍摄后再试。", "request_id": "3dd07d813718" } }
```

### SSE 事件协议

`/api/analyze/stream` 依次发出四类事件（含 15s 心跳注释帧）：

| 事件 | 载荷 | 说明 |
|---|---|---|
| `status` | `{stage, message}` | 阶段：`calling_model` → `parsing` |
| `partial` | `{text}` | **增量文本**，只含 `advice` 字段内容 |
| `result` | 完整 `AnalysisResult` | 结束时一次性下发 |
| `error` | `{code, message, hint}` | 流中途出错时下发 |

设计要点：**流式阶段只推 `advice` 文本，不推原始 JSON**。后端在模型输出累积过程中做增量字段提取（`parser.extract_partial_advice`），把 `"advice": "..."` 的内容边生成边解码（含 `\n`、`\"`、`\uXXXX` 转义，跨 chunk 的半截转义会暂缓输出）。否则用户会看到一屏滚动的 JSON。

前端**没有用 `EventSource`**：它只能发 GET 且不能带请求体，而这两个接口都需要 POST 一张图片。所以改用 `fetch` + `ReadableStream` 手写 SSE 帧解析（`src/api/stream.ts`）。

图像校验与预处理在**流开始之前**完成，因此坏图、超大图会返回正常的 HTTP 错误码，而不是一个「立刻报错的 200 流」。

### 对话轮次的两种形态

`/api/conversations/{id}/turns/stream` 按**本轮有没有附新照片**分两条路径，这对应两种合理的用户预期：

| 本轮 | 产出 | `partial` 事件内容 |
|---|---|---|
| 附了照片 | 结构化 `AnalysisResult`（结果卡） | 增量 `advice` 文本 |
| 只有文字 | 自然语言回复（Markdown），**不解析 JSON** | 原始增量文本 |

`result` 事件返回的是**已存库的那条 assistant 消息**，前端渲染的就是服务端存下的内容。

**追问看不到原图**，这是设计的核心约束之一。每轮只把**本轮的新照片**发给模型，历史轮次只带文本（其中分析轮以紧凑 JSON 形式回放，保证数字精确）。系统提示词里有一节明确告诉模型「你看不到用户之前上传的照片，不要对旧照片的视觉细节做新的断言」——否则它会在第三轮自信地编造「照片里的油很多」这类细节，直接违反「不误判」。

---

## 5. 隐私与数据处理

这一节是本项目的设计重点，不只是文案。

**图片**

- 图片处理**全程在内存中完成**，服务端不把原图写入磁盘。
- 重新编码时会**一并抹掉全部 EXIF**，包括 GPS 定位，因此定位信息不进入识别环节。
- 日志经过脱敏过滤器（`app/core/logging.py`）：`sk-` 形态的密钥、`Authorization`/`api_key` 赋值、`data:image;base64,...`、超长 base64 串都会被替换；日志只记录尺寸与字节数，**不记录图片内容**。
- 前端在浏览器本地压缩后才上传，减少传输量。

**数据库**

- SQLite 只存**结构化分析结果 JSON** 与**对话文本**。三张表（`analysis_records` / `conversations` / `conversation_messages`）里都**没有任何图片相关列**——没有二进制、没有路径、没有 base64，也没有图片哈希。
- 对话消息里的 `images` 字段只存元数据（尺寸、字节数、处理动作），用来告诉用户「这一轮附过几张照片」。
- 历史记录与对话都可以逐条删除。

**饮食画像**

- 画像**只存在浏览器的 localStorage**（键名 `nutrilens.profile.v1`），随每次请求上传，服务端**用完即弃**。
- 数据库里只留一个 `profile_used: true` 布尔标记，用来在结果上显示「已参考你的饮食画像」；**画像的任何字段都不落库**。
- 日志脱敏过滤器额外拦了 `allergies` / `avoidances` / `preferences` / `dietary_pattern` / `health_notes` / `age_band` 这些字段名，作为第二道防线。
- 画像页提供一键清除。清除后建议不再参考它。

**第三方**

- 页面不加载任何第三方统计、广告或 CDN 字体脚本。除调用模型服务本身外，图片不会被发往其他位置。

---

## 6. 合规与安全边界

这些约束落在**代码结构**里，而不是靠文案遮盖。

| 约束 | 实现位置 |
|---|---|
| **不输出健康评分** | `AnalysisResult` / `Nutrition` 的字段里**根本没有** `health_score`、`grade`、`rating`。不是「暂不输出」，是没地方放。`tests/test_schemas.py` 与 `tests/test_prompts.py` 各有一条测试守住这一点 |
| **不做医疗诊断** | 系统提示词明文禁止；免责声明必填且由后端下发 |
| **不评判用户** | 系统提示词明确禁止提及体型、体重、胖瘦、节食、减肥、自律、生活习惯，禁止命令句（「你应该」「必须」），要求改用中性表达 |
| **避免误判** | 输出 `confidence` 与 `confidence_reason`，不确定时给 `dish_name_alternatives` 候选名。低于阈值时前端**固定显示**「可能识别不准，请对照照片确认菜品，或重新拍摄一张更清晰的照片。」 |
| **数值必须带口径** | `nutrition.basis` 必填，说明数值对应的份量。缺少口径的营养数字会被读成比实际更权威 |
| **不知道就留空** | 所有营养字段可为 `null`。提示词明确要求「判断不了填 null，不要编造，也不要用 0 表示不知道」——0 是一个具体主张，`null` 才是「未知」 |
| **输出可控** | 模型输出经括号配平抽取 → 尾逗号修复 → 中文引号修复 → Pydantic 校验。全失败时**降级**为纯文本展示并置 `degraded=true`，而不是返回 500；前端会明确说明「本次没有返回标准结构」 |
| **画像不越界** | 画像字段刻意**不含身高、体重、BMI 与疾病诊断**——结构化身体数据会直接引出「算 BMI、评判体型、推断病情」这类结论。唯一自由文本入口 `health_notes` 由提示词约束为「只作食材筛选」，并明文禁止计算 BMI/体重/体脂/基础代谢、禁止评价体型、禁止把自述当诊断、禁止在回复里复述用户健康信息。`tests/test_profile.py` 逐条守住这些规则 |

置信度做了尺度归一：模型可能返回 `0.87`、`87` 或 `"87%"`，都会落到 0–1。超出范围的异常值**向低置信度一侧收敛**——宁可让用户多确认一次，也不要虚报把握。

---

## 7. 图像处理流水线

顺序是刻意的（`app/services/image_service.py`）：

1. **流式读取并计数**，超过上限立即中断——不会先把 100MB 读进内存再检查。
2. **真实解码**（Pillow）判断格式与完整性。改后缀的假图片走的是内容判断，不看扩展名或 Content-Type。
3. **像素数上限**，从文件头判断，不会为炸弹分配像素缓冲。
4. **EXIF 方向校正**，手机竖拍照片不会躺着。
5. **转 RGB**，透明 PNG 合成到白底，而不是渲染成黑块。
6. **缩放**到最长边 ≤ 1600（LANCZOS）。**多图时改用 1024** —— prefill 开销随张数近似线性增长，多一张就要靠降分辨率把预算让出来。
7. **重新编码**为 JPEG——这一步顺带丢弃全部元数据。

多图还有两道额外的闸门：张数上限（4）与**跨文件的合计字节上限**（20 MB，而不是每张 10 MB 各自为政）。张数在读取之前就检查，用的是 Starlette 已经解析出的文件大小，所以超限的请求不会被读进内存。

处理结果里的 `image.operations` 会回显给用户（「已修正拍摄方向 / 已缩放至 … / 已移除照片元数据」），多图时若各张处理一致会合并成一行，不一致才逐张列出。

损坏文件、非图片、不支持格式、超大文件、超限尺寸、超张数、合计超限各自映射到独立的错误码与友好文案，提示也都可操作。

---

## 8. 目录结构

```
backend/app/
├─ main.py              # 装配、CORS、统一异常处理
├─ config.py            # pydantic-settings 读 .env
├─ schemas.py           # ★ 契约单一来源（含 UserProfile / Conversation）
├─ api/
│  ├─ common.py         # 两条路由共用的 SSE 封装与校验
│  ├─ routes_analyze.py     # 单次分析
│  ├─ routes_conversations.py # 多轮对话
│  └─ routes_health.py / routes_history.py
├─ services/
│  ├─ image_service.py  # 校验·EXIF·缩放·去元数据（单图与多图）
│  ├─ prompt_service.py # 提示词、安全约束、画像块、多轮规则
│  ├─ parser.py         # JSON 抽取·修复·校验·降级·增量提取
│  ├─ analysis_service.py     # 单次分析编排 + 耗时埋点
│  ├─ conversation_service.py # 多轮编排（分析轮 / 对话轮分流）
│  └─ llm/              # base / mock / openai_compat / factory
├─ db/                  # session / models / repository
└─ core/                # errors（友好错误）/ logging（脱敏 + 画像字段）

frontend/src/
├─ api/                 # client.ts（axios）/ stream.ts（SSE 读取器，两条流共用）
├─ types/api.ts         # 与 schemas.py 一一对应
├─ stores/              # app / analysis / conversation / profile
├─ composables/         # useImageCompress / useImageSelection / useResultExport
├─ utils/               # format / exportCard
├─ components/          # ImagePicker / AnalysisPanel / ChatMessage / ResultCard / …
└─ views/               # Home（识别）/ Chat（对话）/ History / Profile / About
```

---

## 9. 结果卡与本地保存

结果卡展示：菜品名与候选名、置信度分档、主要食材及估算用量、估算份量、营养估算表（含口径）、饮食建议（Markdown）、风险提示、不确定项、图片处理说明、免责声明。

保存到本地三种格式，全部在浏览器内完成、不经过服务端：

- **图片**：`html-to-image` 抓取结果卡节点渲染为 2× PNG（导出前会隐藏工具栏，成品里没有按钮）。
- **JSON**：完整结构化结果，便于二次处理。
- **文本**：可读摘要，含全部字段与免责声明。
- 另有「复制」直接写入剪贴板。

长建议用 Markdown 渲染（`marked` + `DOMPurify` 白名单消毒，链接强制 `rel="noopener noreferrer nofollow"`），并在**实测高度**超过阈值时提供「展开全文 / 收起」。

> 折叠判定用的是渲染后 `scrollHeight` 而不是字符数：列表、标题、表格都会改变同样字符数占用的高度，按字符数猜会在最需要折叠的时候恰好不折叠。

---

## 10. 性能与耗时诊断

识别慢的时候，先看数据再改配置。每次识别都会打一行分解日志，`/api/analyze` 还会在响应头里带上同样的数据。

### 日志行

```
识别耗时 12096ms（provider=openai_compat mode=detailed）| prep=186ms request=11904ms
first_token=n/a gen=0ms total=12096ms out_chars=928 prompt_tokens=2794 completion_tokens=445
```

| 字段 | 含义 |
|---|---|
| `prep` | 读取上传 + Pillow 校验/EXIF/缩放/重编码。**通常只占 1–2%**，基本不是瓶颈 |
| `request` | 发起 HTTP 到收到响应头。非流式下等于整个模型调用；流式下等于连接 + 上传 + 图片 prefill |
| `first_token` | 到第一个内容 token（仅流式）。这是用户真正感知的"开始出字"时刻 |
| `gen` | 第一个 token 到结束，即纯生成耗时（仅流式） |
| `total` | `prep` + 模型调用，服务端整体耗时 |
| `out_chars` | 模型返回的原始字符数 |
| `prompt_tokens` / `completion_tokens` | 厂商返回的用量（需 `LLM_REQUEST_USAGE=true`） |

### 响应头

```bash
curl -s -D - -o /dev/null -X POST http://127.0.0.1:8010/api/analyze \
  -F "file=@food.jpg" -F "mode=detailed" | grep -i x-nutrilens-timings
```

### 两个自动告警

**思考模式**是"突然变慢一个数量级"最常见、也最难察觉的原因。埋点会主动报警，两条独立线索：

1. `reasoning_chars > 0` —— 厂商确实返回了 `reasoning_content`，这是**确证**。
2. `completion_tokens > out_chars × 2.5` —— 生成的 token 远多于可见字符，说明有用户看不到的输出。

任一命中都会打 WARNING 并点名 `LLM_ENABLE_THINKING` / `LLM_THINKING_PARAM`。

> 关键点：`LLM_ENABLE_THINKING=false` 只有配合**正确的参数名**才生效。代码现在会显式下发该字段的布尔值（`false` 也发），因为不下发等于"用厂商默认值"，而 Qwen3 系列不少型号默认开启思考。若某厂商不接受该参数，把 `LLM_THINKING_PARAM` 留空即可完全不提它。

### 怎么判断瓶颈在哪

- **`prep` 占比高**（>20%）→ 图片太大或 CPU 太弱。调低 `MAX_IMAGE_EDGE`。
- **`prompt_tokens` 很大**（>3000）→ 图片过大，prefill 和上传都在付钱。调低 `MAX_IMAGE_EDGE`（1600 → 1024 可省约 40–60% 的视觉 token）。
- **`completion_tokens` 高但 `out_chars` 低** → 思考模式没关掉，见上面的告警。
- **`gen` 占 `total` 的绝大部分** → 纯粹的模型输出速度瓶颈，只能从模型档位或提示词长度入手，改图片尺寸没用。
- **`request` 与 `first_token` 差距大** → 连接/上传/prefill 段偏慢，检查网络与图片体积。

### 多图与多轮的额外成本

单图实测 `prompt_tokens ≈ 2790`，其中图片占大头。**prefill 随张数近似线性增长**，所以：

| 场景 | 图片 token 大致量级 | 相对单图 |
|---|---|---|
| 1 张 @1600px | ~1850 | 1× |
| 4 张 @1600px（未做限制时） | ~7400 | ~3× |
| 4 张 @1024px（当前策略） | ~2960 | ~1.6× |

把多图边长降到 1024 正是为了这个：**不加限制的话，4 张图的固定开销会从 2.2 秒涨到 6–8 秒**。上表是按「单图 2790 token」反推的估算，不是实测（我用的是纯色测试图，token 数不具代表性）——真实数字请看你自己的 `prompt_tokens`。

多轮对话还有第二重增长：历史会随轮次变长。当前策略是**永远保留第一轮的分析**（它是整段对话的锚点），加上最近 `MAX_HISTORY_TURNS=8` 条消息，超出即裁剪。追问轮不带任何图片，所以只有文本在增长。

### 优化杠杆（按实测影响力排序）

1. **换更快的模型档位**。生成速度由厂商和模型决定，通常是唯一的大杠杆（大小模型可差 2–4×）。可按模式分级：`quick` 用小模型、`detailed` 用大模型。
2. **缩小图片**。降 `MAX_IMAGE_EDGE` 直接减少上传量与视觉 token，对"认出这是什么菜"几乎无损。
3. **流式**。不改变真实耗时，但把"开始出字"的时刻从生成末尾提前到开头附近——提示词已把 `advice` 排在字段第 5 位，就是为了这个。
4. **复用 HTTP 连接**（尚未实现）。当前每次调用新建 `httpx.AsyncClient`，每请求多付一次 TLS 握手；跨地域约 200–600ms。改成模块级长连接客户端可省掉。
5. **Prompt caching**。system prompt 每次完全相同，支持前缀缓存的厂商可省 prefill。
6. **两段式返回**（尚未实现）。先请求 `{dish_name, confidence}` 快速显示菜名，再请求完整结果。双倍调用成本换首屏速度。

`max_tokens` 调小**通常没用**：正常输出远低于上限，减少上限不会加快生成。

---

## 11. 与规格的差异

明确记录几处有意的偏离：

1. **不做临时文件清理**（规格提到「临时文件设置过期清理」）。
   图片处理全程在内存，服务端从不落盘，因此**没有需要清理的东西**——这比「写盘再定期删」是更强的隐私保证，也少一个会失效的定时任务。
   唯一的落盘来自 Starlette 自身：超过约 1MB 的上传会暂存到系统临时目录，并在请求结束时由框架自动删除。
2. **数据库不存 `image_sha256`**。规格把它列为「仅用于去重」，但去重并未实现，因此不收集——不存用不到的数据是更干净的选择。将来真要做去重再加。
3. **未提供「持久化原图」的隐私开关**。规格里是可选（「或提供隐私开关」），不实现，因为它的隐私成本远高于调试收益。这也是「追问看不到原图」这个限制的由来——见 §4。
4. **前端未引入 Element Plus / Naive UI**，改为手写 CSS 设计令牌（`src/styles/tokens.css`）。为了做出清爽、沉浸式且移动端完全可控的视觉。产物体积（gzip）：主包 62KB；识别页与对话页共用一个约 39KB 的按需分块（Markdown 渲染 + 图片导出），各自再加 5–6KB；画像页 4KB；历史页与关于页各约 2KB。
5. **`vue-router` 用 4.x 而非 5.x**。v5 把 Vite 与 Pinia 列为 peer 依赖，架构改动较大；本项目只需要经典 SPA 路由。
6. **饮食画像刻意收窄字段**。规格只说「支持用户录入个人信息」，这里主动排除了身高、体重、BMI 与疾病史。理由是它们与「不评分、不评判、不诊断」三条硬约束直接冲突——有了结构化体重，模型算 BMI 只是时间问题。**这不是能力缺失，是有意的边界**，也写进了画像页的说明里。

---

## 12. 扩展点

已经落地的扩展点（原规格里列为「后续」的三项）见 §4 与 §5：**多图**、**多轮对话**、**饮食画像**。仍留待将来：

- **多模型识别**：`VisionProvider` 协议 + `llm/factory.py` 是唯一的选择点。加一个厂商 = 加一个类；做多模型投票 = 并发调用多个 provider 再合并。
- **按模式分级模型**：`factory.get_provider` 目前只看 provider 类型，加一个按 `mode` 选模型的策略即可（quick 用小模型）。
- **健康分析 / 长期趋势**：对话与历史都走仓储层，换 PostgreSQL 只改 `DATABASE_URL`；两张表都已按时间建索引。
- **自动发布**：`AnalysisResult` 的 JSON 已是稳定的对外结构，导出逻辑集中在 `utils/exportCard.ts`。
- **WebSocket / 多端同步**：当前用 SSE（单向、够用）。`conversation_service.stream_turn` 的 `(event, payload)` 产出与传输方式无关，换掉路由层即可。

---

## 13. 已验证 / 未验证

诚实说明验证边界。

**已实测**（后端用 curl 打真实接口，前端在浏览器中实际操作）：

- 后端 157 个 pytest 全绿；前端 `vue-tsc` 与 `vite build` 无错误。
- 完整链路：上传 → 压缩预览（2400×1600/122KB → 1600×1067/38KB，省 69%）→ 选模式 → 流式分析 → 结果卡 → 三种格式导出。
- SSE：`status` → 6 个 `partial` → `status` → `result`，且增量文本拼起来与最终 `advice` 完全一致。
- 错误路径逐一实测并确认状态码：损坏文件 400、文本改名 400、BMP 415、12MB 文件 413、非法 mode 400、缺文件 422。
- EXIF 方向 6 的图片被正确旋转并回显「已修正拍摄方向」；输出已无 EXIF。
- 低置信度 UI：危险配色 + 4 档位/2 格点亮 + 「可能识别不准…」提示。
- 降级 UI：模型返回散文时，接口仍返回 200 与可用内容，卡片顶部提示已按纯文本兜底。
- 导出产物：JSON 17 个字段、TXT 54 行含全部章节、PNG 665KB 且 magic bytes 正确。
- 历史记录增删查（200/204/404）；`PRAGMA table_info` 确认无任何图片列。
- 移动端 375×812：无横向溢出，工具栏改双列网格，触控目标达标（正文内联链接除外）。
- 耗时埋点：日志行与 `X-NutriLens-Timings` 响应头字段完整、可解析；无用量数据时不误报。
- 思考模式告警的两条线索（`reasoning_chars > 0`、token/字符比异常）均按预期触发。
- `advice` 前移后，流式首字时刻从总耗时的 **63% 提前到 21%**（mock 实测 2250ms → 824ms，2.7×）。
- 真实模型的一次调用：`prep=186ms`、模型调用 `11904ms`、`out_chars=928`、`completion_tokens=445`。

**多图**（浏览器实测 + curl）

- 单图保持 1600px，多图自动降到 1024px；3 张图返回 3 条图片元数据、`index` 依次为 0/1/2。
- 5 张 → 400 并提示「已忽略多出的 N 张」；前端缩略图、单张删除、合计大小与压缩率显示正常。
- 从 3 张删到 1 张时，剩余那张会**重新按单图边长压回 1600px**（预览与实际发送一致）。
- 多菜品：3 张图时返回 `additional_dishes`，卡片分区渲染出第二道菜（含自己的置信度与营养表）。

**饮食画像**（浏览器实测 + curl）

- 表单录入（过敏原/忌口/偏好/饮食方式/年龄段/健康备注）写入 localStorage 并跨刷新保留；一键清除生效。
- 带画像分析后，结果卡出现「已参考你的饮食画像」徽标；清空画像后同一流程**不再显示**该徽标。
- **画像内容零落库**：把最近一条 DB 记录序列化后逐字搜索，画像里的值一个都不出现，只有 `profile_used: true`。
- **画像内容零日志**：`grep` 服务端日志，画像字段值零命中。
- 畸形画像 JSON → 400，且错误信息不回显原始内容。

**多轮对话**（浏览器实测 + curl）

- 三段链路全部实测：带图首轮 → 分析；纯文本追问 → 自然语言回答（不是 JSON）；再附新图 → 又一次分析。
- 会话与消息正确落库（6 条消息、`seq` 连续、图片元数据只挂在 user 消息上、无任何 base64）。
- 首轮分析后会话标题自动变为菜品名（「番茄炒蛋」）；列表显示轮次数与时间。
- 错误路径：会话不存在 404、空轮次 400、坏图 400（**不是 200 流**）。
- 追问回复里模型主动声明「看不到你之前上传的照片」，与提示词要求一致。
- 中文表单字段往返无损（用显式 UTF-8 客户端验证）。

**未验证**：

- **真实模型下的识别质量与多轮表现**。真实 provider 的耗时链路已用一次 qwen3.8-max 调用验证过，但**识别准确度**、**多轮追问的答案质量**、以及**画像是否真的改善了建议**都没有实测（本机只有 mock 可跑）。首次接真 Key 时建议先用「详细分析」跑几张图，再试一轮追问。
- 思考模式**开启**（`LLM_ENABLE_THINKING=true`）的表现——当前实现只用 `content` 组装结果，`reasoning` 仅用于诊断计数。
- `stream_options.include_usage` 与 `enable_thinking` 两个扩展参数在**不支持它们的厂商**上的报错路径（代码里做了 400 映射与提示，但未逐一实测）。
- 连接复用、prompt caching、两段式返回三项优化**尚未实现**，见 §10。
- 多图 prefill 成本只有估算（测试图是纯色块，token 数不具代表性），真实数字需看实际 `prompt_tokens`。
- Safari / iOS 真机。`createImageBitmap(file, {imageOrientation})` 在旧版 Safari 上会抛错，代码里有 `<img>` 回退路径，但未在真机验证。
- 高并发与长时压测。

---

## 14. 故障排查

| 现象 | 处理 |
|---|---|
| 页面顶部显示「演示模式」 | 未配置 `LLM_API_KEY`。填好后重启后端 |
| 后端启动即报错提示未设置 Key | 用了 `LLM_PROVIDER=openai_compat`。改成 `auto` 或补上 Key |
| 前端提示「无法连接到分析服务」 | 后端没起，或端口不是 8010（前端 proxy 目标） |
| 识别突然变慢很多 | 看日志有没有「模型仍在输出思考内容」的 WARNING。有就检查 `LLM_ENABLE_THINKING` 与 `LLM_THINKING_PARAM`，见 §10 |
| 想看耗时花在哪 | `grep 识别耗时` 看日志，或 `curl -D -` 看 `X-NutriLens-Timings` 响应头，见 §10 |
| 启动报 `Address already in use` / 10048 | 8010 已被占用。`netstat -ano \| grep :8010` 找到 PID，确认是自己的旧进程再停 |
| 想让 .env 不被覆盖 | 别用 `cp .env.example .env` 覆盖已有文件；先备份，或用 `cp -n` |
| 传多张图提示张数超限 | 上限是 `MAX_IMAGES`（默认 4）。要更多就调大，同时留意 §10 的耗时代价 |
| 多图识别明显变慢 | 预期内：prefill 随张数增长。日志里的 `images=N` 和 `prompt_tokens` 能看到代价；可下调 `MULTI_IMAGE_EDGE` |
| 追问时模型说「看不到照片」 | 这是设计如此。原图已删除，追问基于已提取的结果；需要重新看图就再附一张 |
| 追问回答开始编造视觉细节 | 说明 `CONVERSATION_BLOCK` 没生效。检查 `conversation_service` 是否把历史传给了模型 |
| 画像没起作用 | 分析结果上没有「已参考你的饮食画像」徽标，说明画像为空或未发送。去画像页确认已保存 |
| 换浏览器/清缓存后画像没了 | 预期内：画像只存在本机 localStorage，不上传服务端 |
| 对话记录占空间 | 会话与消息都存在 `backend/.runtime/nutrilens.db`；在对话页逐条删除，或直接删库文件 |
| 模型返回「不支持强制 JSON 输出」 | 设 `LLM_JSON_MODE=false` 后重启 |
| 一直提示「识别超时」 | 换「快速识别」模式，或调大 `LLM_TIMEOUT_SECONDS` |
| 上传后立刻报「图片无法识别」 | 文件确实损坏；后端按内容而非扩展名判断 |
| 想清空历史 | 删除 `backend/.runtime/nutrilens.db` |
