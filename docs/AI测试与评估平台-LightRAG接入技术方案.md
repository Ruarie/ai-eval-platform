# AI 测试与评估平台 — LightRAG 接入技术方案

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.0 |
| 审查日期 | 2026-11-02 |
| 对应 PRD | V1.55（F-RAG-01 / F-RAG-05） |
| 对应 API 契约 | V2.46 §3.9 |
| 上游依赖 | [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) `lightrag-hku==1.5.7`（MIT，锁 tag） |
| 适用范围 | 知识库文档建索引、删除联动、检索 Playground 与 RAG 检索指标链路 |

---

## 1. 背景与目标

PRD F-RAG-01 要求「内置 LightRAG：Compose 服务；上传建索引；`doc_id` UUID 写入 metadata；查询走 LightRAG 原生 `query` API，平台适配成内部 `{text, contexts[{id,text}]}`，不把 LightRAG 伪装成 OpenAI Chat」。

改造前 `backend/lightrag/app.py` 是空返回 stub：`/query` 恒返回 `{text:"", contexts:[]}`，文档上传不进入任何引擎，`shared/kb.py` 因为拿不到 contexts 一律回退本地关键词检索。本次目标：

1. 容器内运行真实 LightRAG 引擎（锁版本），按 PRD 契约对外提供检索能力；
2. 上传文档真正建索引，删除文档/知识库真正清索引，状态如实展示；
3. 平台侧无需感知 LightRAG 版本差异与原生 API 细节；
4. 保持「诚实降级」：引擎未配置或失败必须显式标注，禁止 mock 成功。

## 2. 集成方式选型

| 方案 | 说明 | 结论 |
| --- | --- | --- |
| A. 直接跑官方 `lightrag_server:app` | `pip install lightrag-hku[api]` 后 uvicorn 起官方服务，平台侧实现全部适配逻辑 | 否决：平台要同时承担「按知识库过滤、doc_id 还原、状态映射、降级判定」，且 api/worker 需理解 LightRAG 的多套原生端点与版本差异 |
| B. 适配服务内嵌 `LightRAG` SDK（**采用**） | `backend/lightrag` 保留平台内部契约，内部用 SDK 构造 `LightRAG` 实例 | 采用：契约稳定、职责单一、平台其余代码零改动；`lightrag-hku` 及其重依赖（pandas/numpy/networkx）只存在 lightrag 镜像，api/worker 镜像不膨胀 |

方案 B 下 `backend/lightrag` 从 stub 升级为「平台内部适配层」，是唯一持有 LightRAG 依赖的容器。

## 3. 内部契约（容器内网，非平台 REST 契约）

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/health` | 引擎就绪状态、文档状态计数、模型与维度（不含密钥） |
| POST | `/documents/index` | 受理建索引 `{kb_id, doc_id, filename, text}` → `{doc_id, status}` |
| GET | `/documents/status?doc_ids=a,b` | 批量回读 `{items:[{doc_id,status}]}`，未收录的 ID 不返回 |
| POST | `/documents/delete` | 批量删除 `{kb_id, doc_ids[]}` → `{deleted, results}` |
| POST | `/query` | 检索 `{query, mode, top_k, kb_id}` → `{text:"", contexts[], mode, engine, engine_version}` |
| POST | `/graph` | 只读图谱 `{kb_id, limit}` → `{nodes[], edges[], truncated, engine}`；按来源前缀过滤 |

约定：

- 所有非 `/health` 端点在校验 `X-API-Key`（对应 `LIGHTRAG_API_KEY`）后放行；未配置口令时依赖 Compose 内网隔离；
- `mode` 仅接受 PRD 定义的 `naive / local / global / hybrid`，`mix` / `bypass` 不对平台开放；
- `/query` 使用 `only_need_context=True`，只做召回不生成答案：RAG 评测口径是检索指标（Hit Rate@K / MRR / Recall@K / contain），避免为每条样本额外付费；
- 引擎不可用统一返回 503，由平台侧判定降级。

### 3.1 文档来源标识（关键约束）

LightRAG 的 `file_path` 会被 `normalize_document_file_path` 收敛为 **basename**（`Path(file_path).name`），目录层级会被丢弃。因此不能把 ID 放在路径里，统一用双下划线前缀：

```text
{kb_id}__{doc_id}__{filename}
```

- 写入：`rag.ainsert(text, ids=[doc_id], file_paths=[source], track_id=doc_id)`，`doc_id` 直接沿用平台 UUID（PRD 要求）；
- 读取：`aquery_data` 返回的 `chunks[].file_path` 反解出 `kb_id` / `doc_id` / `filename`；
- 隔离：按 `{kb_id}__` 前缀过滤，`kb-1` 不会误命中 `kb-10`；
- 兼容：来源标识非法的切块在指定知识库时被过滤，未指定时只作为纯文本上下文返回，不参与命中判定。

## 4. 关键实现

### 4.1 异步建索引

实体/关系抽取需要多轮 LLM 调用，单篇长文档可能耗时数分钟，所以：

1. `POST /documents/index` 只把任务登记进内存队列并 `create_task`，立即返回 `indexing`；
2. 后台任务持有 `asyncio.Lock` 串行执行 `ainsert`——LightRAG 的写入/删除共用同一条管线，busy 时调用会被拒绝；
3. 真实进度由 LightRAG 自己的 `doc_status` 承载，平台 `GET /api/kb/{id}/documents` 回读并收敛：
   `pending/processing → indexing`、`processed → indexed`、`failed → failed`；
4. 入队前就失败的文档记入进程内 `_failed`，状态直接 `failed`，避免永远停在 `indexing`；
5. 队列有上限（`LIGHTRAG_MAX_QUEUE_DOCUMENTS`，默认 64 篇）：排队文档的正文驻留内存，超限返回 429，平台落 `failed` 由用户重试，避免把容器推到 OOM；
6. 引擎重启后 `_queued` / `_failed` 丢失：若 `doc_status` 仍为 `pending/processing` 而本进程没有对应任务，说明上次抽取被中断，按 `failed` 返回，前端因此能停止轮询，而不是永久 `indexing`；
7. 停机时先给 30 秒宽限期（`LIGHTRAG_SHUTDOWN_GRACE_SECONDS`）让在建任务收尾，超时才取消，降低 `processing` 残留概率。

### 4.2 按知识库过滤与召回窗口

LightRAG 的 query 不支持按文档过滤，单实例多知识库共享同一向量库与图谱。因此：

- 指定知识库时把 `chunk_top_k` 放大到 `min(max(k*4, 20), 60)`，过滤后再截断到 `k`，降低其它知识库挤占导致的召回损失；
- 未指定知识库时按 `k` 原样召回（仅调试用途）。

### 4.3 降级口径（收紧）

改造前「召回为空」也回退本地关键词检索，会把真实未命中伪装成降级。现口径：

| 场景 | 行为 | 报告 |
| --- | --- | --- |
| 引擎返回 2xx，含空 contexts | 不回退，返回空列表 | `source=lightrag`，真实未命中 |
| 引擎未配置 / 不可达 / 5xx / 超时 | 回退本地关键词检索 | `source=local`，报告 `degraded=local_keyword` |
| 部分样本回退 | 逐样本记账 | `degraded=partial` + `engine_counts` |

### 4.4 删除一致性

`DELETE /api/kb/{id}/documents/{doc_id}` 与 `DELETE /api/kb/{id}` 改为「先删引擎、再删库内记录」：LightRAG 已配置但删除失败时返回 `UPSTREAM`(502) 并保留记录，避免出现「库里已删、向量库仍召回」的脏数据。引擎未配置时没有索引可删，直接完成（不阻塞知识库维护）。

两个边界必须区分：

- **按索引状态分组**：`indexed` 文档强制引擎删除成功；`indexing` / `failed` 文档在引擎里可能从未落库，删除失败不阻断清理，否则引擎一旦不可用，用户连空知识库都删不掉；
- **按批提交**：删除按 50 篇/批、状态回读按 200 篇/批发送，避免整库文档数超过单请求上限或撞上代理超时；对调用方仍是一次请求。

删除前会用 `doc_status` 里的 `file_path` 做一次知识库前缀校验，跨库 doc_id 返回 `forbidden` 并拒绝删除（平台侧已校验归属，这里作为第二道防线）。

### 4.5 图谱读取（只读）

实体与关系是索引阶段的副产品，平台以 `GET /api/kb/{id}/graph` 只读展示：

- 适配层调用 `get_knowledge_graph("*", max_nodes=…)` 取全局最高度数子图，再按节点属性里的 `file_path` 前缀过滤；过滤同样发生在召回之后，因此候选窗口取 `min(max(limit*5, 200), 1000)`；
- 实体/关系节点上的 `file_path` 是 `<SEP>` 拼接的多来源字段，`parse_doc_ids` 逐段判定前缀并回填 `doc_ids`，供前端关联到文档名；
- 返回前按库内度数降序截断到 `limit`（≤500），并丢弃两端不全在结果中的边，避免前端出现悬空关系；
- 只读：不提供实体合并、关系编辑或图谱写入；`external_chat` 知识库无本地图谱，平台侧直接返回 `VALIDATION`；
- 与检索不同，图谱**不做本地兜底**：引擎不可用返回 `UPSTREAM`，空图只表示"该库尚未抽出实体"，不用空图掩盖引擎故障。

### 4.6 健康与可观测

`GET /health` 返回 `ready / configured / missing[] / documents{status counts} / queued_documents / llm_model / embedding_model / embedding_dim`，不含密钥与正文。Compose 健康检查只验证进程可服务；是否真能建索引看 `ready` 字段。

## 5. 部署与配置

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `LIGHTRAG_LLM_BASE_URL` / `LIGHTRAG_LLM_API_KEY` | 空 | OpenAI 兼容网关；地址为空 = 引擎未就绪，密钥缺失时按 `EMPTY` 占位（适配无鉴权的本地网关） |
| `LIGHTRAG_LLM_MODEL` | `gpt-4o-mini` | 图谱抽取模型 |
| `LIGHTRAG_LLM_TIMEOUT_SECONDS` | `180` | 抽取单次超时 |
| `LIGHTRAG_EMBEDDING_BASE_URL` / `_API_KEY` | 复用 LLM | 独立向量网关时才填 |
| `LIGHTRAG_EMBEDDING_MODEL` / `LIGHTRAG_EMBEDDING_DIM` | `BAAI/bge-m3` / `1024` | **维度必须与模型一致**，否则写入向量报维度不匹配 |
| `LIGHTRAG_CHUNK_TOKEN_SIZE` / `_OVERLAP_TOKENS` | `1200` / `100` | 切块粒度与抽取成本 |
| `LIGHTRAG_API_KEY` | 空 | 平台 ↔ 适配服务内部口令（9621 发布到宿主机，对外可达时必须设置） |
| `LIGHTRAG_QUERY_TIMEOUT_SECONDS` | `60` | 平台侧检索超时（hybrid 等模式先做关键词抽取）；旧名 `LIGHTRAG_TIMEOUT_SECONDS` 仅作检索回退 |
| `LIGHTRAG_INDEX_TIMEOUT_SECONDS` | `15` | 建索引受理超时（只入队，返回很快） |
| `LIGHTRAG_STATUS_TIMEOUT_SECONDS` | `15` | 文档状态回读超时；不应长时间阻塞列表 |
| `LIGHTRAG_DELETE_TIMEOUT_SECONDS` | `120` | 删除超时；删除会重建受影响实体的图谱摘要 |
| `LIGHTRAG_MAX_QUEUE_DOCUMENTS` | `64` | 待索引队列上限，超限返回 429 |
| `LIGHTRAG_SHUTDOWN_GRACE_SECONDS` | `30` | 停机时等待在建任务收尾的宽限期 |
| `LIGHTRAG_MEM_LIMIT` | `1g` | 真实引擎内存高于旧 stub（768m 在长文档抽取时会 OOM） |

其他要点：

- 数据目录 `./data/lightrag` 挂载为 `/data/lightrag`，图、向量与 doc_status 随卷持久化；
- `tiktoken` 需 BPE 词表：镜像构建期预热到 `/app/.tiktoken`；构建机无外网时预热失败不阻塞镜像，但运行期缺词表会导致建索引失败并如实显示 `failed`；
- 传递依赖由 `backend/lightrag/constraints.txt` 锁定（pandas / numpy / networkx / openai / tiktoken 等），升级 `lightrag-hku` 时必须同步复核，否则同一 commit 会构建出行为不同的镜像；
- 密钥只注入 lightrag 容器，api/worker 只持 `LIGHTRAG_BASE_URL` 与 `LIGHTRAG_API_KEY`；
- `deploy/plan_services.py` 已按 `backend/lightrag/Dockerfile` 输入计算增量构建，无需改动部署链路。

## 6. 已知限制

1. **内容哈希去重跨库**：LightRAG 按正文哈希去重，同一份正文分别上传到两个知识库时，后一次会被标记为重复并落 `failed`。这是「单实例多库共享存储」的固有约束，需多库共存同一文档时后续可评估按知识库分 workspace/实例。
2. **召回稀释**：过滤在召回之后，多库共存且语料高度相似时命中率会低于独立引擎；已用放大 `chunk_top_k` 缓解，未做向量级过滤。
3. **答案生成未启用**：平台不校验 `response` 文本，`answer_contain` 仍是「参考答案子串出现在检索文本中」的文档包含判定（与 PRD F-RAG-04 的 contain 口径一致）。
4. **图谱抽取成本**：每次建索引会产生多次 LLM 调用，大量小文档同时上传被串行化，属于预期行为。
5. **RAG 评测入口现状**：按 AGENTS.md V2.8，`kind=rag` 任务的新建已停用；本次接入覆盖的是知识库上传/删除/Playground 与 `shared.kb` 检索层，历史 RAG 报告仍只读。
6. **部署形态**：适配服务必须单容器单 uvicorn worker（`CMD` 未设置 `--workers`），队列、锁与失败表都在进程内，多副本共享同一 `./data/lightrag` 会损坏图与向量库。

## 7. 验证

```bash
# 适配层契约 + 引擎行为单测（无需 lightrag 依赖；需本地安装 pytest）
cd backend/lightrag && python -m pytest tests

# 平台侧客户端契约单测（跟随 api 门禁执行）
cd backend/api && pytest tests/test_kb_lightrag.py

# 真实引擎冒烟（需可用的 OpenAI 兼容网关）
curl -s localhost:9621/health | python -m json.tool
```

覆盖范围：

- `tests/test_contract.py`：来源标识往返与非法输入、分隔符拒绝、状态映射、召回窗口、切块过滤/去重/截断；
- `tests/test_engine.py`：队列上限、停机宽限与超时取消、`processing` 残留自愈、删除归属校验、失败表容量；
- `tests/test_kb_lightrag.py`：响应映射、降级口径、超时变量隔离、删除/状态分批、受理与删除失败。

本地已用假 LLM/Embedding 跑通 `ainsert → doc_status=processed → 检索 → 跨库删除拦截 → adelete_by_doc_id` 全链路，并实测队列上限返回 429，确认与 `lightrag-hku 1.5.7` 的实际契约一致。

## 8. 修改代码文件与作用清单

| 文件 | 作用 |
| --- | --- |
| `backend/lightrag/app.py` | 由 stub 改为真实适配服务：`/health`、`/documents/index`、`/documents/status`、`/documents/delete`、`/query` + 内网 `X-API-Key` 鉴权 |
| `backend/lightrag/adapter/config.py`（新增） | 环境变量归一为不可变配置；`ready` / `missing` 如实表达未就绪原因 |
| `backend/lightrag/adapter/contract.py`（新增） | 文档来源标识、状态映射、召回窗口与切块映射（纯函数，可脱离引擎测试） |
| `backend/lightrag/adapter/engine.py`（新增） | `LightRAG` 实例生命周期、异步串行建索引（含队列上限与停机宽限）、批量删除（含归属校验）、状态回读（含中断残留自愈）、检索与只读图谱读取；`EngineUnavailable` / `EngineBusy` 区分失败与队列满 |
| `backend/lightrag/adapter/__init__.py`（新增） | 适配层包导出 |
| `backend/lightrag/requirements.txt` | 新增 `lightrag-hku==1.5.7`（锁 tag）与 `openai` 绑定依赖 |
| `backend/lightrag/constraints.txt`（新增） | 锁定 lightrag-hku 未锁的传递依赖（pandas/numpy/networkx/openai/tiktoken 等），避免构建漂移 |
| `backend/lightrag/Dockerfile` | 拷贝适配层；构建期预热 tiktoken 词表（失败不阻塞构建） |
| `backend/lightrag/conftest.py`、`backend/lightrag/tests/test_contract.py`、`tests/test_engine.py`（新增） | 适配层契约与引擎行为单测（不进镜像） |
| `backend/shared/kb.py` | 新增 `index_document` / `delete_documents` / `document_statuses` / `engine_available` / `fetch_graph`；检索改为按知识库过滤并收紧降级口径；超时从 2s 提升为可配置 60s |
| `backend/api/app/routers/kb.py` | 上传即受理建索引并落真实状态；列表回读引擎状态；文档/知识库删除先清引擎索引；新增 `GET /{id}/graph`（只读，仅 lightrag 库）；失败返回 `UPSTREAM` |
| `backend/api/app/schemas.py` | 新增 `KbGraphOut` / `KbGraphNodeOut` / `KbGraphEdgeOut` |
| `backend/api/tests/test_kb_lightrag.py`（新增） | 客户端契约单测：映射、降级口径、受理失败、删除与状态回读 |
| `frontend/src/views/Kb.vue` | `similarity` 允许为空并显示占位符（不再用 0 冒充）；`indexing` 期间 5s 轮询状态，收敛后自动停止；顶部新增「知识图谱」入口 |
| `frontend/src/components/drawers/KbGraphDrawer.vue`（新增） | 只读图谱抽屉：自实现力导向布局（无额外图表依赖）、按实体类型着色、点击节点看描述与来源文档、截断与空态提示 |
| `frontend/src/layouts/MainLayout.vue` | 评测组恢复「知识库」菜单项（PRD 5.8 路由 `/kb`），此前页面只能手输地址进入 |
| `frontend/src/api/{http,types}.ts` | 新增 `kb.getGraph` 与图谱类型 |
| `docker-compose.yml` | lightrag 服务补 LLM/Embedding 绑定、内部口令、数据目录、健康检查与内存上限；api/worker 注入内部口令与检索超时 |
| `.env.example` | 新增/完善 LightRAG 配置段与说明 |
| `docs/AI测试与评估平台-API.md` | V2.46：§3.9 明确异步建索引状态收敛、删除顺序、`similarity` 可空与降级口径 |
