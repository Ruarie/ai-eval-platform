# AI 测试与评估平台 PRD

> ⚠️ **当前产品边界（2026-09-28）**：平台已转向测试用例生成 Agent，只新建用例生成任务；Benchmark、RAG 评测及压测全部停用，历史任务与报告只读保留。下文旧评测功能表和里程碑保留为历史设计，不构成当前可执行需求；用例生成、草稿审核及停用行为以 V1.51–V1.55 修订为准。
>
> **文档维护提示（2026-09-11）**：部分章节含已删除模块的历史引用（如 `agent/react.py`、`plan_solve.py`）；当前实现与接口以 `AGENTS.md` 状态地图和 API 最新修订为准。

| 项目 | 内容 |
| --- | --- |
| 文档版本 | V1.69 |
| 本轮审查日期 | 2026-11-09（用量中心新增模型单价与费用估算；未配置单价仍明确标为未计价） |
| 文档状态 | V1.31 已实现三类准备专家与受控草稿；V1.30 的完整计划/报告连接仍待实现，后台恢复与专家通讯仍待 P2/P3 |
| 撰写日期 | 2026-08-17 |
| 本轮修订 | 2026-09-26：V1.47 新增“我的记忆”，支持个人／个人工作区范围的主动保存、更正、撤回及私有主会话按预算召回；语义向量检索和自动抽取仍未交付。 |
| 最近修订 | 2026-08-31：V1.17 增加危险 bash 的 LangGraph 人在回路：风险命令必须弹出确认卡，原发起成员确认后才进入 bwrap 沙箱；拒绝不执行。思考卡只呈现过程摘要，禁止显示会与工具真实结果冲突的原始推理。2026-08-30：V1.16 增加受控 Agent 技能文件与协议档专属补充提示词管理；技能正文遵循渐进式披露，核心安全提示词不可覆盖。2026-08-28：V1.15 统一基准目录治理、独立导入队列、staging 并发发布、成员同权双人复核与 M3 里程碑；冻结任务必须锁定数据集/黄金集版本。2026-08-28：V1.14 新增基准数据集目录、异步导入、staging 表格和发布门禁；下载/解析仅由 Worker 执行，未审核行不得评测。2026-08-24：补充 Agent 多附件交互：支持图片（PNG/JPG/JPEG/WEBP/GIF）、Markdown/TXT/HTML/JSON/YAML、PDF、Word（DOC/DOCX）、Excel（XLS/XLSX）、CSV/JSONL 与音频；输入区支持文件选择和拖拽上传，图片显示缩略图，PDF/文本支持预览，Office 文件显示类型卡片并可打开/下载。2026-08-23：补齐 Gemini OpenAI 兼容端点的思考摘要请求与增量归一化；增加 Agent 思考摘要开关与思考强度设置；将用户回显固定为 `user_message`，将完成信号固定为 `response.completed`，明确 `thought` 不承载助手正文；协议档增加可选 Embedding / Reranker 独立端点配置，三类 Key 均按 profile 写入受控环境文件 |
| 适用版本 | 平台 V1.0 |
| 技术栈 | Vue3 + Naive UI、Python FastAPI、PostgreSQL、WebSocket、Docker Compose、go-stress-testing |

### 修订记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| V1.0–V1.4 | 2026-08-17 | 能力清单与决策收口 |
| V1.5 | 2026-08-17 | 三模块 + 共享压测；Agent / MCP / 三协议 |
| V1.6 | 2026-08-17 | 补缺陷：任务状态机、Agent/Worker 分工、MCP/REST 契约、协议细节、评测/压测配置、页面与验收、预算与并发 |
| V1.6.1 | 2026-08-17 | 复查修复：一任务一种 kind、LightRAG 查询契约、会签/取消权限、指标与协议档数量对齐 |
| V1.6.2 | 2026-08-17 | 与问答复核：压测内核改回 go-stress-testing；附录 B 逐条对照 |
| V1.6.3 | 2026-08-17 | 再核：WS 用 ticket 非长期 token；压测由 stress 容器执行且取消立即停；LightRAG 压测走 query 而非 Chat；会话槽位含子任务 |
| V1.6.4 | 2026-08-18 | 全面去除静态 Mock 数据，全量接入后端 API 统一客户端；落实全员同权协作与智能体/调度/任务中心动态交互 |
| V1.6.5 | 2026-08-20 | 新增默认私有、创建者可切换团队共享的 Agent 会话；补齐软删除、多人实时正文流与确认卡作者边界 |
| V1.7.1 | 2026-08-21 | 协议档支持可选 Embedding / Reranker 的 URL、模型标识与 Key；Key 只写不回显 |
| V1.8 | 2026-08-23 | Agent 运行基线切换为 LangGraph；首期只交付单轮模型调用与 WebSocket 流式链路，Harness、MCP、确认卡与长任务保持后续阶段 |
| V1.9 | 2026-08-23 | 拆分用户消息、思考摘要、助手正文增量、助手最终消息和 done 事件，明确 `pong` 为独立心跳 |
| V1.10 | 2026-08-23 | 用户回显使用 `user_message`，助手正文使用 `assistant_delta` / `assistant_message`，回合结束使用 `response.completed`，`thought` 严禁承载助手正文 |
| V1.11 | 2026-08-23 | Agent 后台增加思考摘要开关与 `low/medium/high/xhigh/max` 强度；不改变 WebSocket 公共头与正文事件语义 |
| V1.12 | 2026-08-23 | Gemini OpenAI 兼容流式请求增加 `include_thoughts` 与强度映射；思考摘要仍通过 `thought` 事件独立展示 |
| V1.14 | 2026-08-28 | 基准数据集页新增受控目录筛选、异步制品导入、staging 表格预览和审核发布门禁；不做社交媒体抓取 |
| V1.15 | 2026-08-28 | 补齐目录/release 双人复核、导入队列租约与重试、staging 版本号发布和版本锁定；将该能力与 RAG 黄金集统一收敛至 M3，代码题继续不做 |
| V1.16 | 2026-08-30 | Agent 技能文件统一规格、渐进式加载、管理端预览/编辑及协议档专属补充提示词；核心安全提示词继续固定 |
| V1.17 | 2026-08-31 | 危险 bash 先弹人工确认卡再执行；推理仅呈现过程摘要，工具结果是唯一执行事实 |
| V1.18 | 2026-08-31 | ReAct / Plan-and-Solve / reflect 的内部过程不再生成对话卡；只显示 Plan、工具、确认与真实最终结果 |
| V1.19 | 2026-09-09 | 废除首次登录强制改密；账号自助改密入口保留（右上角「修改密码」），密码强度规则不变 |
| V1.20 | 2026-09-09 | 协议档收敛为 OpenAI Chat 与 Anthropic Messages，删除 OpenAI Responses 适配与已有档位凭据 |
| V1.21 | 2026-09-12 | 协议档 → MCP 与工具新增受控媒体 MCP 配置；Qwen 生图和 HappyHorse 首帧图生视频接入 AgentLoop，视频仅异步提交与查询，不新增媒体任务表或结果归档 |
| V1.22 | 2026-09-15 | 新模型用供应商与协议的受控思考模板逐档真实验证后才登记；验证结果限制 AgentLoop 可选思考强度，旧协议档保持 legacy 解析 |
| V1.25 | 2026-09-15 | 补齐 Kimi K3、智谱 GLM 与火山方舟豆包的 Anthropic Messages 思考模板；Kimi 使用 output_config 强度，GLM/豆包使用标准 thinking 开关，均以真实探测为准 |
| V1.60 | 2026-11-09 | 需求基线与用例覆盖 MVP：从需求原文抽取编号条目、人工确认基线、用例集绑定与覆盖率、自动关联候选与人工确认；不新增评测/压测入口 |
| V1.61 | 2026-11-09 | 全局搜索 MVP：Cmd/Ctrl+K 命令面板，跨用例集、任务、会话、报告、知识库、数据集、工作区、记忆只读检索；私有资产按属主过滤 |
| V1.62 | 2026-11-09 | 用例评审工作流与版本历史 MVP：人工评审请求/结论/评论、AI 评审历史、版本快照/字段级 diff/回滚为新草稿；不改变确认与任务联动 |
| V1.63 | 2026-11-09 | 用例质量看板 MVP：按时间窗聚合运行数、生成/确认、采纳率、成功率、最新 AI 评分、按天/模型/状态/模块分布；只读现有事实，不新增生成链路 |
| V1.64 | 2026-11-09 | 需求变更分析 MVP：需求基线版本链、版本差异、受影响用例集/用例清单；只做分析，不自动修改用例 |
| V1.65 | 2026-11-09 | 用例资产库 MVP：确认入库物化、跨集合检索、标签、文本查重与历史回填；不做自动合并或复制 |
| V1.66 | 2026-11-09 | 站内通知中心 MVP：任务生成完成/失败、评审指派/结论通知；顶栏未读徽标与通知列表；不做邮件/Webhook 外发 |
| V1.67 | 2026-11-09 | Agent 历史轨迹查询 MVP：按回合聚合计时/工具/模型/token，事件级脱敏展示；只读已持久化 AgentEvent，不新增结构化轨迹表 |
| V1.68 | 2026-11-09 | Token 用量中心 MVP：按天/模型/成员聚合 assistant 消息 turn_stats 用量；未配置逐模型单价，不展示费用 |
| V1.69 | 2026-11-09 | 用量中心费用估算：按模型名维护 USD/百万 token 单价，按输入/输出估算；未配置模型保持未计价 |

---

## 1. 背景与目标

### 1.1 背景

当前用 **Agent** 从需求文档或用户描述生成测试用例，候选内容先存草稿，经人工审核后在用例域入库。历史基准、RAG 评测和压测能力已停止运行。

| 痛点 | 后果 |
| --- | --- |
| 评测靠脚本、协议各写一套 | 无法一句话跑完「选模型 → 跑集 → 报告 → 加压」 |
| 无统一任务与基线 | 选型不可复现 |
| LightRAG 与自建 RAG 指标不一 | 知识库更新后不敢发 |
| 质量与容量断开 | 效果好但一压就垮 |

### 1.2 产品定位

面向**单一团队**，以 WebSocket Agent 对话和 `/cases` 用例工作台为入口。Agent 或任务接口只能创建 `testcase` 任务；生成结果先以草稿关联用例页，人工审核后确认入库。以下评测模块仅保留历史数据和说明：

| 模块 | 职责 |
| --- | --- |
| A. Agent | 会话、拆解、确认卡、进度；**不执行长任务** |
| B. Benchmark | 自定义文本集、三类协议调用、规则评分 / Judge、对比与基线 |
| C. RAG | Compose 内 LightRAG，或外部 **OpenAI Chat Completions** RAG HTTP |
| 共享压测 | 质量成功后压同一推理 / query 接口；平台面板 + Prometheus scrape |

### 1.3 目标

1. 对话或用例页从需求生成候选用例，人工采纳、保存草稿并审核确认；保存冲突不能覆盖他人版本。
2. 只领取用例生成队列，取消遗留评测与压测任务；历史任务和报告可查询，不发起新的评分或发压。
3. Web、API、Worker 与 PostgreSQL 支撑当前流程；遗留 LightRAG 和 stress 服务不得产生新评测或压测。

### 1.4 成功指标

| 指标 | 目标 | 口径 |
| --- | --- | --- |
| 用例生成闭环 | 对话与用例页均可生成用例 | 候选采纳、保存草稿、人工确认与导出可追溯 |
| 用例采纳率 | ≥ 70% | 确认入库条数 / 当次生成条数 |
| 停用门禁 | 新评测与压测任务 0 单 | REST、Agent、Worker 和压测引擎一致拒绝 |

### 1.5 术语

| 术语 | 含义 |
| --- | --- |
| 协议档 | `openai_chat` / `openai_responses` / `anthropic_messages` 之一 + 主模型 base_url/模型名/Key；可选 Embedding、Reranker 各自 base_url/模型名/Key，均写入受控环境文件 |
| 会话 | 每成员可多开；默认仅创建者可见，也可由创建者设为团队共享；**会话内任务串行**，会话间可并行（受平台并发上限） |
| 长任务 | 当前只执行 `testcase.generate`；旧评测与压测任务仅保留历史记录 |
| 短工具 | `*.list` / `report.get` / `task.get`，Agent 可同步调用 |
| 草稿审核 | 用例先存 `generated` 草稿，人工确认后为 `confirmed`；取消或超时为 `cancelled` |
| 待补全 | 映射缺字段，不进入评分队列 |

### 1.6 已确认决策

| 议题 | 决策 |
| --- | --- |
| 切分 | Agent + 用例工作台生成测试用例；评测与压测停用 |
| 交互 | Agent 主、表单辅；同一任务表 |
| MCP | 仅内部；Agent 当 Host 调短工具并下单；长任务由 worker 调同一 MCP |
| Skill | 当前仅启用测试用例生成；旧评测技能停止调用 |
| 协议 | Chat Completions + Responses + Anthropic Messages |
| Key | 管理员平台级池 |
| 队列 | PG 任务表 + worker；WS 只推事件 |
| RAG | 内置 LightRAG + 外部 OpenAI Chat HTTP |
| 压测 | 不再创建或执行；旧运行任务取消，压测引擎拒绝新的 `/run` |
| 部署 / 登录 / 文件 | Compose；本地账号；本地盘 + PG 路径 |
| 公开集 | 无 |
| 人设 | 固定资深评测工程师 |
| 合规 | 单团队；不涉密不强制私有化；报告不进审批；用例不同步 TMS |

### 1.7 Agent 运行基线（V1.8）

当前首期实现以以下链路为唯一事实源：

```text
WebSocket 短票
  -> LangGraph Agent Graph（单轮）
  -> ModelGateway（LangGraph 模型调用图）
  -> 三类协议适配器
  -> user_message / thought / assistant_delta / assistant_message / response.completed / error / pong
```

- `app/agent/graph.py` 只编排一次模型调用，不持有数据库、WebSocket、工具或任务状态；
- `app/llm/` 只负责 `ModelRequest`、`ModelResponse`、三类协议适配与流式事件，不承载 Harness；
- `app/routers/ws.py` 负责短票、会话事件、后台 Task 和流式 WS 投影，收包循环不得等待整轮模型调用；
- 首期支持 `user_message(role=user)`、`thought` 思考摘要、`assistant_delta` 正文增量、`assistant_message` 最终交付句和 `response.completed` 结束信号；`pong` 为独立应用层心跳；`message` 不再作为新用户回显事件；
- Harness、ReAct/MCP、人工确认、任务取消、长任务队列和记忆层属于后续设计，不得在首期代码中提前实现。

本节是对“最终产品能力”和“当前实现阶段”的区分：下文 M2–M4 的任务、MCP、确认卡和评测闭环仍是产品目标，但在首期 Agent 基础链路稳定前不宣称已交付。

---

## 2. 用户、权限与账号

### 2.1 角色架构（单一角色「成员」· 全员同权）

平台面向敏捷 AI 评测团队，采用**单一角色「成员」（全员同权）**架构，彻底摒弃复杂的 RBAC 三级角色阻碍：

| 权限范围 | 权限能力说明 | 审计与约束 |
| --- | --- | --- |
| **Agent 与任务** | Agent 交互、创建或重跑用例生成任务、取消任务；历史评测任务只读查询 | 任务创建与取消均记录审计日志 |
| **资产与工作台** | 用例草稿保存、审核确认与导出；历史数据集及知识库资产按现有权限维护 | 旧用例到评测数据集的映射入口停用 |
| **配置与治理** | 协议档维护与连通性检查、当前任务调度配置；历史压测配置仅供查看 | 新发压及压测会签停用 |
| **账号与成员** | 开户、停用账号、重置密码、修改个人凭据 | 强制保护：不可停用系统中最后一名正常账号 |

首次部署：环境变量创建初始成员账号。密码 ≥8 位，含字母和数字。浏览器会话使用 HttpOnly Cookie（12h 可续）。WebSocket 连接使用 5 分钟短票（ticket），见 F-AGT-01。（V1.19 修订：不再强制首次改密——账号可自主在右上角「修改密码」更新凭据。）

#### 2.1.1 数据资产治理（不新增 RBAC）

目录、release、导入和发布仍由同一个 `member` 角色执行；“提报人”“审核人”是某一次操作的审计身份，不是永久角色或权限等级。这样既保持全员同权，也避免同一人对自己的来源、许可证和数据行作无复核发布。

| 治理动作 | 执行规则 | 必须记录的审计信息 |
| --- | --- | --- |
| 新建目录来源、登记 release、发起允许的导入 | 任一正常成员可执行 | actor、对象 ID、来源/release manifest 哈希、原因、时间 |
| 审核并批准 release、审核并发布 staging、确认许可证例外 | 审核成员必须与该 release/导入的提报成员不同；同一成员不得审批自己的提交 | 提报人与审核人、前后状态、许可证证据引用、审核意见、冻结版本 ID |
| 暂停或封禁 release | 任一正常成员可立即暂停新的导入以止损；另一成员必须复核为 `blocked` 或恢复 | 暂停原因、影响版本、复核结果与时间 |
| 撤销正式版本 | 任一正常成员可提交撤销；另一成员复核后将旧版本置为 `deprecated`，历史报告只读保留 | 版本 ID、内容/manifest 哈希、撤销原因、两名操作者 |

系统初始化账号、运行并发上限和密钥托管是运维配置，不授予数据资产的单人发布豁免。所有上述操作均写入 `audit_logs`；浏览器和模型上下文不得获得下载令牌、授权文件正文或未脱敏上游响应。

### 2.2 团队协同原则

团队全员同权，通过全局顶栏「大模型 / RAG」双模式与统一任务工作台实现高效无阻碍协同。

Agent 会话采用以下更细的资产边界，不把「全员同权」误解为默认公开历史：

- 新会话默认 `private`，仅会话创建者可浏览、发送消息、连接 WS、压缩上下文、设置共享或软删除；
- 创建者可切为 `team`，表示当前单一内部团队的正常成员均可浏览历史、发送消息并看到在线协作者产生的 AI **正文**流式增量；本期不是邀请制成员表；
- 创建者可随时收回为 `private`，服务端立即断开协作者连接；已删除会话对所有成员返回“会话不存在”；
- 共享会话中的确认卡只允许提出该卡的成员确认、拒绝或提交 patch；任务仍归该成员创建，取消/重跑仍按任务创建者；
- 原始模型推理 `think` 流不对协作者广播。附件被发送到共享会话即视为授权本团队成员查看。

---

## 3. 业务流程

### 3.1 职责：谁调 MCP

| 角色 | 可调用 | 不可 |
| --- | --- | --- |
| Agent（WS 进程） | 当前仅调用 LangGraph 单轮模型图；后续可由 Harness 组合短工具并写「待执行」任务 | 自己跑完 Benchmark/RAG/压测 |
| Worker | 评测 / RAG / 用例生成 MCP；`stress.run` 只负责向 stress 容器下发 | 向用户闲聊；自己打满压测连接 |
| 表单 REST | 直接 `POST /api/tasks`，状态与 Agent 下单相同 | — |

这样 WS 断开不影响后续异步执行；确认卡只决定「是否入队」。当前首期尚未启用确认卡和任务下单，WS 只完成单轮文本生成与事件持久化。

### 3.2 主路径

```
打开会话 → 说话 → Agent 澄清并调短工具列选项
        → 确认卡（见 5.1.2）  ※ 一任务仅一种 kind
        → INSERT task queued
        → worker 执行该 kind
              testcase → awaiting_case_confirm → 用户确认后终态 succeeded
                    Agent 可自动再弹一张 Benchmark/RAG 确认卡（新任务）
              benchmark / rag → succeeded 且 with_stress
                    → 自动入队压测子任务
              report 落库
        → WS 推 progress / report / error（重连按 last_event_id 补发）
```

V1 **不允许**一个任务同时跑 Benchmark 和 RAG。要两份报告就下两单（可同一会话连续确认）。质量任务 `failed` / `cancelled` 不创建压测。

### 3.3 任务状态机

```
queued → running → succeeded
                 → failed
                 → cancelled
                 → awaiting_case_confirm → succeeded（确认入库）
                                         → cancelled（拒绝或 72h）
```

| 状态 | 含义 | 谁能改 |
| --- | --- | --- |
| queued | 等待 worker | 当前只允许新建用例生成任务；创建者可取消 |
| running | worker 执行用例生成 | 创建者可取消；遗留评测与压测运行任务统一取消 |
| awaiting_case_confirm | 用例已生成未确认 | 人工确认则 **succeeded**（用例域入库）；取消或 72h → cancelled |
| succeeded / failed / cancelled | 终态 | 用例生成任务可复制为新任务；旧评测与压测只读 |

压测子任务是历史机制；当前不再派生、不接受会签，旧运行任务进入取消与外部停发流程。

### 3.4 并发

- 会话内：同时最多 1 个处于 `queued` / `running` / `awaiting_case_confirm` 的用例生成任务。
- 平台：管理员配置 `max_running_tasks`（默认 3）与 `max_inflight_model_calls`（默认 8）。超限新任务保持 queued。

---

## 4. 范围

### 4.1 内

测试用例生成 Agent、用例页候选采纳与人工审核、现有协议档、内部工具、任务队列、历史任务和报告只读查询。

### 4.2 外

新建或重跑 Benchmark/RAG 评测、发起压测、旧评测数据集映射、报告分享与基线修改；其他历史排除项（如多租户和 TMS 同步）继续适用。

---

## 5. 功能需求

### 5.1 模块 A — Agent

#### 5.1.1 功能表

| 编号 | 功能 | 优先级 | 交付 | 说明 |
| --- | --- | --- | --- | --- |
| F-AGT-01 | WS 会话 | P0 | M1 | 登录后发 5 分钟 `ws_ticket`，`GET /ws/agent?ticket=` 升级（不用长期 JWT 进 query）。心跳 30s；重连带 `session_id`+`last_event_id` |
| F-AGT-02 | 事件流 | P0 | M1 | 见 5.1.3 |
| F-AGT-03 | MCP Host | P0 | 后续阶段 | 目标是只连内部 Server；短工具同步，长任务只 `task.create`；首期保持能力未启用 |
| F-AGT-04 | 确认卡 | P0 | 后续阶段 | 见 5.1.2；未确认不入队；首期不生成确认卡 |
| F-AGT-05 | 人设与技能治理 | P0 | 后续阶段 | 核心系统提示词由 Harness 固定生成；每个 Agent 协议档预留独立补充提示词入口，内置技能以统一 `SKILL.md` 受控预览/编辑，均需审计 |
| F-AGT-06 | Agent 后端 | P0 | M1 基础 | 管理员指定一个协议档；LangGraph 单轮调用默认读取最近 20 条用户/助手消息；系统提示词与复杂上下文策略留后续 |
| F-AGT-07 | 表单双入口 | P0 | M2 | `POST /api/tasks` 与确认卡字段一致 |
| F-AGT-08 | 历史报告查看 | P1 | 现有能力 | 仅阅读已有 `report_id`；不调用评测 Skill 或重跑评测 |
| F-AGT-09 | 取消 / 重跑 | P0 | 现有能力 | 成员取消自己创建的非终态任务；仅用例生成任务可重跑。旧运行中的压测取消后须请求引擎停发，失败保留重试标记 |
| F-AGT-10 | 团队共享与软删除会话 | P0 | M1 基础 | 默认私有；会话创建者可切为 `team`，在线协作者实时看到用户消息与 AI 正文 chunk；删除为软删除，运行中的 Agent 回合、待确认卡或非终态任务必须先结束 |

#### 5.1.1.1 Agent 技能与 Prompt 管理边界

内置任务技能统一存为 `skills/<skill_id>/SKILL.md`，头部固定 `id`、`name`、`kind`、`version`、`enabled`、`summary`，正文固定以 `## 工作流` 开始。系统提示词常驻的仅是技能目录摘要；仅当本轮计划选中技能后，Harness 才读取该技能全文。读取技能前必须验证目标 `SKILL.md` 存在；缺失或规格不合法时不得降级为硬编码工作流。

管理端可预览和编辑已登记的 Skill 文件，写入必须采用修订指纹并发保护、原子替换和不含正文的审计记录。每个 `agent` 用途的协议档预留独立 Prompt 管理入口：核心角色/安全/任务状态机提示词始终只读且优先，管理员只能维护该协议档的补充提示词。普通会话中的文件工具始终限制在会话工作区，不得读取或写入运行时 Skill/Prompt 配置。

#### 5.1.2 确认卡字段（P0）

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `kind` | 是 | 仅四选一：`benchmark` / `rag` / `testcase` / `stress`（`stress` 一般不手选，由系统在质量成功后创建） |
| `profile_ids[]` | `benchmark` 必填 | 1–5 个被测协议档；`rag` 打外部 Chat 时填 1 个「RAG 服务」档 |
| `dataset_id` | `benchmark` 必填 | |
| `kb_id` + `gold_qa_id` | `rag` 必填 | 内置库或外挂 RAG 都要黄金 QA |
| `rag_mode` | `rag` 且目标为 LightRAG | 1–4 个模式，默认 `["hybrid"]` |
| `run` | 评测必填 | 见 5.2.2，RAG 复用 sample/concurrency/timeout |
| `with_stress` | `benchmark`/`rag` 必填 | 默认 false；true 时质量成功后自动建子任务 |
| `stress` | `with_stress` 时必填 | `env`, `qps`, `duration_s`, `sla_p99_ms?` |
| `case_source` | `testcase` 必填 | `file_id` 或粘贴文本 |

`prod` + 压测：确认卡展示会签人，未完成会签不得把压测设为 running。

REST、Agent 工具与历史重跑均创建新的生产压测会签请求，不能复用旧任务的 `approved_by`。Worker 发压前还须校验会签已经完成且会签人不是任务创建者。历史重跑同样受个人活动任务配额和会话待确认卡限制。

#### 5.1.2.1 危险工具确认卡（P0）

`bash` 不是任务确认卡：它只处理会话工作区内的短命令。删除、覆盖、移动、权限变更，或无法静态证明只读的命令，必须在任何副作用前暂停并展示 `ToolApprovalCard`。卡片必须显示待执行命令、风险原因与沙箱边界；仅命令原发起成员可选择“确认执行”或“拒绝”。确认后才允许 Runner 在 bwrap 中执行；拒绝后命令不得执行，并把 ToolCard 标为“已拒绝”。`sudo`、网络和远程连接命令不属于可确认范围，必须保持硬拒绝。

思考卡每回合至多一张，只描述“正在分析/校验”这类固定过程状态，不得展示模型原始推理、未执行动作或任何“已成功”结论。ReAct JSON 的 `thought`、Plan-and-Solve / reflect 阶段状态以及带 ToolCall 响应中的正文草稿均为内部控制信息，禁止生成卡片或回放。工具的 `tool_result.ok=true` 才是可向用户陈述已执行成功的唯一事实来源。

#### 5.1.3 WS 事件

公共头：`event`, `session_id`, `task_id?`, `event_id`（单调）, `ts`。

| event | payload 要点 |
| --- | --- |
| `thought` | 当前回合最多一条固定过程摘要；不得含阶段、推理原文或业务结论，历史 UI 不重放 |
| `user_message` | 已持久化用户消息、作者与浏览器幂等键；协作者即时补气泡 |
| `tool_call` | `name`, `arguments` |
| `tool_result` | `name`, `ok`, `data` 或 `error`；用户拒绝危险工具时 `status=rejected` |
| `tool_approval` | 危险 bash 的命令、风险、沙箱边界与可选决定；命令尚未执行 |
| `tool_approval_ack` | 原发起成员的 `approve` / `reject` 回执；确认才恢复原 ToolNode |
| `confirm` | 确认卡 JSON，等前端 `confirm_ack` |
| `progress` | `percent?`, `done`, `total`, `message` |
| `report` | `report_id` |
| `error` | `code`, `message`（可给用户看） |
| `pong` | 心跳 |

前端 → 服务：`user_message` `{text, attachments[]?, client_message_id?}`，`confirm_ack` `{ok, patch?}`，`cancel_task` `{task_id}`，`clarify_reply` `{id, answer}`，`tool_approval_ack` `{id, action:"approve"|"reject"}`。

`assistant_delta` 只在在线时即时广播，断线不回放；含 ToolCall 的上游响应不得下发正文草稿。`thought.stream=think` 仅发给本轮发起连接，不向团队协作者泄露；`think_final` 只保留固定摘要且历史 UI 不重放。`assistant_message` 只保存已验证的最终交付句，`response.completed` 标记本轮结束。

当前已实现事件以 API 契约为准：`tool_call`、`tool_result`、`tool_approval`、`tool_approval_ack`、`plan`、`confirm`、`confirm_ack`、`progress` 与 `report` 均按各自状态机处理。任何未启用能力必须返回 `VALIDATION`，不得伪造任务或工具成功。

附件：先 `POST /api/files` 得 `file_id`，再在消息里引用。单文件 ≤20MB；支持图片（PNG/JPG/JPEG/WEBP/GIF）、PRD/OpenAPI/Markdown/TXT/HTML/JSON/YAML、PDF、Word（DOC/DOCX）、Excel（XLS/XLSX）、JSONL/CSV 与 wav/mp3。Agent 输入区支持多选和拖拽上传；本地暂存阶段图片显示缩略图，PDF/文本支持预览，Office 文件显示文件类型卡片并可打开/下载。

---

### 5.2 模块 B — Benchmark（历史设计，当前停用）

#### 5.2.1 功能表

| 编号 | 功能 | 优先级 | 交付 | 说明 |
| --- | --- | --- | --- | --- |
| F-BM-01 | 协议档 CRUD 与模型验证 | P0 | M1 | 见 6.2；主模型及可选 Embedding / Reranker 端点配置，三类 Key 只写不回显，审计变更；新模型按供应商与协议模板真实验证思考能力后才登记 |
| F-BM-02 | 统一调用 | P0 | M1 | 入 `messages`，出 `text,usage,raw,latency_ms` |
| F-BM-03 | 数据集 | P0 | M2 | JSONL/CSV UTF-8；列 `question,reference,context?`；导入/编辑先写 `draft` 或 staging，审核发布才生成可评测版本；单集 ≤50MB、≤2 万行 |
| F-BM-04 | 用例入集 | P0 | M2 | 5.4.2；待补全不评分 |
| F-BM-05 | 规则评分 | P0 | M2 | 每集选一种主指标：exact / contain / regex / rouge_l / bleu；默认 contain |
| F-BM-06 | 多模型 | P0 | M2 | 1–5 个 profile；报告并排 |
| F-BM-07 | 基线 | P0 | M2 | 成员冻结某次 succeeded；同 dataset 版本+主指标才能对比 |
| F-BM-08 | Judge | P1 | M3 | 裁判协议档 ≠ 被测（警告，不强制）；1–5 分 + 理由 |
| F-BM-09 | 代码题 | — | 不做 | |
| F-BM-10 | 基准目录与异步导入 | P1 | M3 | 仅展示双人复核的固定 release；独立 Worker 队列下载/校验/解析后写入带版本号的 staging 表格，非提报人审核原子发布前不得评分 |

#### 5.2.2 运行配置 `run`

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `sample_size` | min(1000, 全集) | 随机抽样，种子写入任务便于复现 |
| `concurrency` | 4 | 受 `max_inflight_model_calls` 限制 |
| `timeout_s` | 60 | 单样本 |
| `retry` | 1 | 仅超时/5xx |
| `temperature` | 0 | |
| `max_tokens` | 1024 | |
| `system_prompt` | 空 | 可选，写入任务快照 |

失败样本记 `error`，不中断整次任务；失败率写入报告。

#### 5.2.3 验收（M2）

两个协议档 + 一份 ≥20 条 JSONL，对话确认后出对比报告（contain 分）；断线重连仍看得到进度；缺 question 的映射行在待补全，不进分母。

#### 5.2.4 基准目录、导入与发布（M3）

`/datasets` 提供“导入公开基准”入口，只展示**来源与固定 release 均已复核批准**的目录条目。成员可按能力场景、任务族、语言、许可状态、测试标签可用性、评分器支持度、污染风险与预计规模筛选，并选择 release 明示的 split、subject/子集与目标数据集。页面不得提交任意 URL、Cookie、请求头、Token 或解析脚本；筛选字段、枚举值、默认值、最大行数和确定性排序均由目录 release 返回的 `filter_schema` 定义。

目录治理分为来源和 release 两层：成员先登记来源和固定 release manifest（官方地址、允许域名、revision、制品清单/哈希、许可证证据、允许 split、解析器与筛选 schema），另一成员审核后才可见、可导入。release 一经批准不可原地编辑；修订、许可证变化或上游制品变化必须新建 release。任一成员可暂停 release 阻止新导入，复核后再恢复或置为 `blocked`；被封禁 release 的正式版本只保留历史报告，不得新建任务。

提交后 API 只创建独立 `DatasetImport` 作业并立即返回；Worker 负责下载、哈希/许可证/格式校验、解压、解析、去重和 staging 写入，API 进程不得等待或执行这些耗时步骤。作业状态：`queued → downloading → validating → parsing → review_ready → published`，或转为 `failed | rejected`。作业有不可变导入 manifest、唯一请求指纹、尝试次数和租约；Worker 使用行锁领取，租约过期时回收重排，超过重试上限才置为 `failed`。同一 release manifest、切分、规范化过滤规则、解析器版本和目标数据集的重复请求必须幂等返回既有作业，禁止重复写行或由失效 Worker 覆盖新尝试结果。

当导入状态为 `review_ready`，目标数据集在左侧树和主表格中可见，主表展示该 `import_id` 的 staging 行、稳定行 ID、`staging_revision`、split、来源 release 和解析告警；这些行可审核修订，但不进入确认卡、任务分母或基线。表格编辑必须带回读取时的 `staging_revision`，成功编辑递增该版本号。由**非提报成员**点击“审核并发布”时，服务端锁住 import 与数据集，校验 `import_id + staging_revision + accepted_row_ids[]`，并在一个事务中冻结审核通过行、来源 manifest、制品/行内容哈希、解析器/评分器版本和审核记录为新的 `DatasetVersion`；过期 revision、重复发布或并发编辑返回 `CONCURRENCY`，不得按行号猜测选择。数据集容器可继续保持旧 `active_version_id`，新 staging 不影响正在运行任务；发布成功才原子切换新的 `active_version_id`，作业变为 `published`。`failed`/`rejected` 只保留最小审计与错误摘要。标准集的 `train` split 默认禁止导入；无公开 test 标签的条目只能导入 validation 并显著标记“非官方 test”。

创建 benchmark 任务时，服务端在同一事务读取数据集当前 `active_version_id` 并锁定为 `Task.config.dataset_version_id`；请求方不能指定、替换或在重跑时漂移到最新版本。Worker、报告、基线和重跑只读取该冻结版本。RAG 任务同理锁定 `gold_qa_version_id` 与 KB 文档快照。

---

### 5.3 模块 C — RAG 评测（历史设计，当前停用）

#### 5.3.1 功能表

| 编号 | 功能 | 优先级 | 交付 | 说明 |
| --- | --- | --- | --- | --- |
| F-RAG-01 | 内置 LightRAG | P0 | M3 | Compose 服务；上传建索引；`doc_id`=UUID 写入 metadata。**查询走 LightRAG 原生 `query` API**（模式见 F-RAG-05），平台适配成内部 `{text, contexts[{id,text}]}`，不把 LightRAG 伪装成 OpenAI Chat |
| F-RAG-02 | 外部 RAG | P0 | M3 | 仅 `POST {base}/v1/chat/completions`；答案 `choices[0].message.content`；上下文 `message.context` 或 `message.contexts[]`（字符串或 `{id,text}`） |
| F-RAG-03 | 黄金 QA | P0 | M3 | `question,reference,expected_doc_ids[]?`；≤1 万条；整集覆盖上传版本 +1 |
| F-RAG-04 | 指标 | P0 | M3 | `expected_doc_ids` 非空：Hit Rate@K、MRR、Recall@K，**K 默认 5 可配 1–20**。答案：contain。Judge P1 |
| F-RAG-05 | LightRAG 模式 | P0 | M3 | naive/local/global/hybrid，一次任务可选 1–4 个 |
| F-RAG-06 | 基线 | P0 | M3 | 同 kb + gold 版本对比；退化 ≥5pp 标红。**通知在 M4**，M3 只在报告内标红 |
| F-RAG-07 | 知识图谱视图 | P1 | V1.56 交付只读版 | 知识库页面按知识库展示 LightRAG 抽取的实体与关系：节点含实体名、类型、描述、关联文档，边含关系描述与权重；只读、按库过滤、限量（单次 ≤500 节点），不做图编辑，不改变检索与评测口径 |

命中判定：返回的 context.id 或可解析的 doc_id **集合相交** `expected_doc_ids` 即命中。纯文本无 id 时该样本不计入 Hit Rate 分母。

#### 5.3.2 验收（M3）

默认库 + ≥20 条带 `expected_doc_ids` 的 QA，hybrid 出 Hit Rate@5；同一套 QA 打外部 OpenAI Chat RAG（可用 mock）出答案 contain。

---

### 5.4 Skill

#### 5.4.1 用例生成

| 项 | V1 |
| --- | --- |
| 输入 P0 | PRD 文本、OpenAPI JSON/YAML、Excel（标准列或 模块/名称/步骤/预期） |
| 输入 P1 | Postman、Markdown 接口 |
| 输出 | XMind + Excel（`GET /api/case-sets/{id}/export?fmt=xlsx\|xmind`），状态 `generated` |
| 自检 P0 | 无核心正向、缺约束反向 → 确认页红字 |
| 规模 | 参考上限：PRD 简单/中/复杂 20/45/80 条；超上限停并提示拆分，禁止灌水 |
| 超时 | 5 分钟，超时 failed |

生成使用当前成员上传的需求文件或粘贴文本，文件 ID 不代表授权；API 入队和 Worker 消费均检查来源。已有用例编辑必须保持身份、前置条件、功能点和扩展字段，保存失败不得继续确认或丢弃草稿。Excel/XMind 导出必须返回实际文件，失败不得提示成功。

长任务领取记录 Worker 身份与租约，阻塞模型调用期间由独立心跳续租。租约失效或升级前遗留的无租约运行中任务明确转为失败并释放并发名额；用户核对结果后可手动重跑，不自动重复结果未知的供应商调用。该故障收尾不等于 Agent 专家后台续跑能力。

#### 5.4.2 映射

| 目标 | 自动 | 否则 |
| --- | --- | --- |
| Benchmark | 问句→question，预期→reference，前置→context | 待补全 |
| 黄金 QA | 同上；doc_ids 手补 | 无 id 仅答案侧 |
| 压测 body | 步骤中 `METHOD path` + 示例 JSON | 无 path 则压测只用评测时的默认 chat 模板 |

映射写 `source_case_id`+用例版本。

#### 5.4.3 评测 Skill

规则实现、Judge 提示词、报告解读提示词。随镜像发布，无热更新 UI。

---

### 5.5 MCP 工具中心与技能编排

平台采用受控 MCP Host 统一智能体架构。长评测任务由 Worker 异步执行；Agent 仅调用短工具与 `task.create` 结构化建单。媒体 MCP 是唯一允许的远程扩展：API 固定经 Compose 私网 Streamable HTTP 连接 `media-mcp`，浏览器不能配置任意第三方地址，模型和密钥仅由“协议档 → MCP 与工具”受控配置保存。

#### 5.5.1 内置受控短工具清单 (Tools Manifest)

| 工具名称 | 类型 | 入参（摘要） | 出参 | 权限与用途 |
| --- | --- | --- | --- | --- |
| `model.list` | 短 | — | 协议档 id/名称/协议（无 Key） | READ · 模型资产发现 |
| `dataset.list` | 短 | — | 数据集 id/版本/行数/主指标 | READ · 评测集检索 |
| `kb.list` | 短 | — | 知识库 id/文档数/黄金 QA | READ · RAG 资产列表 |
| `report.get` | 短 | `report_id` | 指标摘要 + 下载路径 | READ · 报告在对话中解读 |
| `task.create` | 短 | 确认卡 TaskSpec JSON | `task_id`, `status` | WRITE · 下单推入调度队列 |
| `task.cancel` | 短 | `task_id`, `reason` | `ok: true` | WRITE · 任务取消分流 |
| `dispatch.overview` | 短 | — | Worker 节点数/CPU负载/策略 | READ · 调度大盘感知 |
| `image.generate` | 短 | prompt、可选参考图、尺寸/数量 | 临时图片地址 | NET · Qwen 图片生成 |
| `video.create` | 短 | prompt、首帧、分辨率/时长 | 上游异步任务 ID | NET · HappyHorse 图生视频提交 |
| `video.status` | 短 | 上游任务 ID | 状态、临时视频地址 | READ · 查询视频结果 |

媒体工具受既有会话权限档位裁决。视频创建不等待生成完成，当前不创建平台 `Task`、不归档图片或视频、不提供上游取消和播放器；这些属于后续媒体任务阶段，不能把上游临时地址当作平台文件资产。

#### 5.5.2 智能体 4 大核心内置技能 (Skills)

1. **`skill-benchmark`（基准对比）**：自动识别被测模型数量、推荐标准评测集并构建先评后压 TaskSpec；
2. **`skill-rag`（RAG 质量评估）**：自动装载知识库切块与黄金 QA，评测 LightRAG 4 模式检索表现；
3. **`skill-testcase`（PRD 用例生成）**：按 6 大策略精细配比（40/25/15/10/5/5）提炼测试用例；
4. **`skill-stress`（共享容量压测）**：继承父任务 endpoint 与抽样问答，定位 SLA 拐点与成本开销。

错误码：`UNAUTHORIZED` `VALIDATION` `NOT_FOUND` `BUDGET_EXCEEDED` `CONCURRENCY` `WHITELIST` `NEED_APPROVAL` `UPSTREAM` `TIMEOUT` `INTERNAL`。

---

### 5.6 共享压测（历史设计，当前停用）

| 编号 | 功能 | 优先级 | 交付 | 说明 |
| --- | --- | --- | --- | --- |
| F-ST-01 | 继承目标 | P0 | M4 | **Benchmark / 外部 RAG**：URL、Header、协议来自父任务协议档；body 用父任务抽样最多 50 条 `question` 轮询，包成该协议请求。**内置 LightRAG**：压 Compose 内网 `query` HTTP（不是 Chat Completions），body 按父任务 `rag_mode` 组装 |
| F-ST-02 | 指标 | P0 | M4 | 模型：QPS、RT、错误率、TTFT、TPOT、tokens/s（SSE）。RAG：QPS、RT、错误率（非流式可不记 TTFT） |
| F-ST-03 | 面板与停止 | P0 | M4 | 任务页与 Agent 进度区展示 QPS/RT/错误率曲线；取消压测 **立即** 停发（与评测的协作式取消不同） |
| F-ST-04 | `/metrics` | P0 | M4 | 内网；Basic 或 IP 白名单；前缀 `ai_eval_stress_`；label `env,model,task_id`；任务结束后 10min 内停止该 task 序列 |
| F-ST-05 | 安全 | P0 | M4 | env 必填；host 白名单；默认 QPS≤500、时长≤30min；错误率 60s≥50% 停；`prod` 会签 |
| F-ST-06 | 拐点与 SLA | P0 | M4 | 未填 `sla_p99_ms` 不出「是否达标」；填了则拐点=首次 P99>SLA 或错误率≥1% |
| F-ST-07 | 费用 | P0 | M4 | 用父任务 usage 单价估算压测窗口费用（管理员配单价 /1k tokens） |

V1 压测内核：**go-stress-testing**（Apache-2.0）扩展，独立 `stress` 容器，由 worker 下发任务；指标契约见上。不在 api 进程内用 Python 替代（询问中未改内核）。

**验收（M4）**：test 白名单地址，质量成功后自动压 2 分钟；平台曲线与 Grafana 同 `task_id`；无白名单无法 running。

---

### 5.7 通用

| 编号 | 功能 | 优先级 | 交付 | 说明 |
| --- | --- | --- | --- | --- |
| F-CM-01 | 任务中心 | P0 | M1 | 列表筛选状态/kind；日志=task_events |
| F-CM-02 | 报告 | P0 | M2 | 对比：profile + dataset/kb 版本 + 时间；导出 Markdown；分享 7 天 |
| F-CM-03 | 账号 | P0 | M1 | 2.1 |
| F-CM-04 | 审计 | P0 | M1 | 登录失败、Key、基线、白名单、prod、角色 |
| F-CM-05 | 通知 | P1 | M4 | 终态、退化、会签；企微/邮件/出站 Webhook，管理员配开关 |
| F-CM-06 | 预算 | P0 | M2 | 单任务 `max_usd`（默认 5）；累计 usage 超限停；`BUDGET_EXCEEDED` |
| F-CM-07 | 文件 | P0 | M1 | 本地卷 `./data/files/{id}`；PG 存路径与 sha256 |
| F-CM-08 | Open API | P1 | V1.1 | |

---

### 5.8 前端信息架构（Vue3 + Naive UI / 原型工作台）

| 路由 | 页 | 功能说明 | 角色 |
| --- | --- | --- | --- |
| `/login` | 登录 | 居中登录卡、统一错误提示（不区分用户或密码）（V1.19 起不再首登强制改密） | 成员（全员） |
| `/agent` | 智能体 | 会话列表、对话流式交互、过程摘要卡、工具卡、危险 bash 确认卡、TaskSpec 确认卡、底部吸附进度坞、内嵌迷你调度视图 | 成员 |
| `/memories` | 我的记忆 | 本人主动保存的常用偏好与事实资料；搜索、查看、更正、删除和个人工作区范围管理 | 成员（仅本人数据） |
| `/dispatch` | 调度中心 | 调度内核雷达、分发策略切换、并发容量滑块、Task 队列 → Worker 节点平滑三次贝塞尔连线拓扑、调度日志流 | 成员 |
| `/tasks` | 任务中心 | 六态徽章、24h 吞吐面积图与状态分布分段条、多维筛选、AI 智能编排、任务详情抽屉与事件时间线 | 成员 |
| `/reports` `/reports/:id` | 历史报告中心 | 已有 Benchmark、RAG 与压测报告只读查询及导出；不提供新的分享或基线修改 | 成员 |
| `/datasets` | 数据集工作台 | 目录树结构管理、自定义列管理（+新增列）、单元格行内即点即改、多行/JSON 弹窗编辑器、AI 智能合成新数据与补全缺失行 | 成员 |
| `/cases` | 用例工作台 | 用例集目录树、6 大测试策略分布与自检、AI 从 PRD 生成候选、草稿编辑与人工审核、72h 倒计时及导出；旧评测映射停用 | 成员 |
| `/case-quality` | 用例质量看板 | 按 7/30/90 天聚合生成运行、采纳率、成功率、AI 评分、按天/模型/模块分布与最近运行明细 | 成员 |
| `/case-assets` | 用例资产库 | 已确认用例的跨集合资产检索、模块/策略/优先级/标签筛选、文本查重与历史回填 | 成员 |
| `/notifications` | 通知中心 | 全部/未读筛选、单条/全部已读、跳转任务或用例集；顶栏铃铛展示未读数 | 成员 |
| `/usage` | 用量中心 | 按 7/30/90 天聚合 token、调用、会话、模型与成员分布；不展示费用估算 | 成员 |
| `/kb` | 知识库与切块检索 | 文档分块预览、2D 向量投影散点图、Top-K 相似度召回连线与重排前后位次对比 (Rerank Delta)、黄金 QA 维护 | 成员 |
| `/admin/profiles` | 协议档治理 | 三类协议（`openai_chat`、`openai_responses`、`anthropic_messages`）及可选 Embedding / Reranker 端点维护、Key 只写不回显、连通性检查 | 成员 |
| `/admin/stress` | 历史压测配置 | 现有配置与历史数据按保留的页面展示；不触发新的压测 | 成员 |
| `/admin/users` | 账号协同 | 成员开户、停用、重置密码（系统安全保底：不可停用最后一名正常账号） | 成员 |

智能体与用例工作台以测试用例生成为主；旧「大模型 / RAG」评测发起入口不再接受新任务。

无独立「改系统提示词」页。

---

### 5.9 REST 一览（V1，均需登录）

`POST /api/auth/login` `POST /api/auth/logout`  
`GET/POST /api/users`（管理）  
`GET/POST /api/files`  
`CRUD /api/profiles`（Key 只写）  
`CRUD /api/datasets` `CRUD /api/case-sets` `POST .../confirm`  
`CRUD /api/kb` `POST /api/kb/{id}/docs` `CRUD /api/gold-qa`  
`POST /api/tasks` `GET /api/tasks` `GET /api/tasks/{id}` `POST /api/tasks/{id}/cancel` `POST /api/tasks/{id}/rerun`  
`GET /api/reports/{id}` `POST /api/reports/{id}/share`  
`GET /api/admin/settings` `PUT /api/admin/settings`  
`POST /api/auth/ws-ticket` `GET /ws/agent?ticket=`

---

## 6. 技术架构

### 6.1 栈

FastAPI（REST + WS）+ worker 进程 + PostgreSQL + Vue3/Naive/Vite + LightRAG 容器 + **stress（go-stress-testing 扩展）**。压测进程暴露 `/metrics`，Compose 固定端口供现有 Prometheus 抓取。

### 6.2 协议适配

内部：`{messages, temperature, max_tokens}` → 适配器 → `{text, usage{prompt,completion}, raw, latency_ms}`。

| 类型 | 请求 | 鉴权 |
| --- | --- | --- |
| `openai_chat` | `POST {base}/v1/chat/completions`，`messages` | `Authorization: Bearer` |
| `openai_responses` | `POST {base}/v1/responses`，`input` / `instructions` | `Authorization: Bearer` |
| `anthropic_messages` | `POST {base}/v1/messages`，`system` 拆出，`messages` 仅 user/assistant | `x-api-key` + `anthropic-version: 2023-06-01`（可配） |

被测评测：**非流式**。压测：对 chat/responses 解析 SSE 以算 TTFT。适配失败归 `UPSTREAM`，raw 截断入库（≤32KB）。

每种协议至少 2 个夹具单测（成功 + 4xx）。

### 6.3 架构图

```
浏览器 Vue3
  /agent  ──WS── FastAPI WS Bridge
                    │
                    ▼
              LangGraph Agent Graph
                    │
                    ▼
              ModelGateway（LangGraph）
                    │
                    ▼
              三类协议适配器 / 上游模型

  其它页 ──REST─┐
                └── PostgreSQL（sessions / messages / ws_events / tasks）
                                      │
                                      ▼
              worker（后续长任务：评测 / RAG / 生成用例；压测下发到 stress）
                 │         │              │
                 ▼         ▼              ▼
           三类协议适配 LightRAG      go-stress-testing
                         /外部 Chat        /metrics
                                            ▼
                                    现有 Prometheus
```

### 6.4 表

`users, sessions, messages, ws_events, protocol_profiles, settings, files, dataset_catalog_entries, dataset_catalog_releases, dataset_catalog_reviews, dataset_source_artifacts, dataset_imports, dataset_import_attempts, dataset_import_rows, datasets, dataset_rows, dataset_versions, dataset_version_rows, case_sets, cases, case_maps, kbs, kb_docs, gold_qa, tasks, task_events, eval_items, baselines, reports, share_links, audit_logs, usage_ledger`。

### 6.5 开源

testcase-tools：只对齐，不进镜像。LightRAG：MIT，锁 tag。go-stress-testing：Apache-2.0，二次开发保留 NOTICE。

---

## 7. 里程碑与验收

| 阶段 | 交付 | 演示门禁 |
| --- | --- | --- |
| M1 | Compose、账号、协议档、LangGraph 单轮 Agent、WS 基础事件、会话回放、文件 | 登录后完成单轮流式对话；断线按 event_id 续；确认卡、短 MCP、任务下单进入后续 Harness 阶段 |
| M2 | 真调用、规则分、对比、基线、用例 Skill、表单、预算 | 5.2.3 |
| M3 | LightRAG、外部 Chat RAG、黄金 QA、Hit Rate、目录/release 双人复核、独立导入队列、staging 原子发布和任务版本锁定 | 5.3.2 + 5.2.4；仅支持当前 PRD 已列任务族，不含代码题 |
| M4 | 先评后压、白名单、Grafana、解读、通知 | 5.6 验收 |

---

## 8. 非功能

| 项 | 要求 |
| --- | --- |
| 性能 | ≤1k 样本且被测稳定 ≥5 QPS → 规则评测 ≤30min；中等 PRD 用例 ≤5min |
| 稳定 | 断点：评测按样本行号续跑；可用性 99%/月 |
| 安全 | 协议档 URL、模型 ID、API Key 按 profile 写入服务器受控环境文件（文件权限 0600、API 加锁刷新并 fsync、Worker 只读）；旧数据库密文仅迁移后清空；WS 使用短票 `ws_ticket`；`/metrics` 不暴露公网 |
| 成本 | usage_ledger + 任务预算 |
| 兼容 | 被测仅 HTTP 三类协议；导出 xlsx / xmind 8+ |

---

## 9. 风险

| 风险 | 应对 |
| --- | --- |
| 三类协议字段差 | 夹具单测 |
| 并行打爆 API | 平台并发 + 预算 |
| 映射失败 | 待补全；可手传 JSONL |
| LightRAG 升级 | 锁 tag |
| 压测误伤 | F-ST-05 |
| 抓取失败 | M4 对齐网络；默认 job/前缀已写死 |
| 用例确认悬挂 | 72h 自动取消 |

---

## 10. 复查记录（V1.6）

### 10.1 已修缺陷

| 原问题 | 处理 |
| --- | --- |
| Agent 与 worker 都像在跑长任务 | 3.1 明确：Agent 只入队 |
| 无状态机、用例确认会卡死流水线 | 3.3 + 72h 超时 |
| MCP 名与流程不一致（`report.build`） | 统一 5.5 |
| 确认卡、WS、REST、页面缺失 | 5.1.2 / 5.1.3 / 5.8 / 5.9 |
| 评测无并发/超时/抽样 | 5.2.2 |
| Hit@K、doc 命中规则不清 | 5.3.1 |
| 压测 body 从哪来 | F-ST-01 抽样轮询 |
| 通知写在 M3、能力在 M4 | 报告 M3 标红，通知 M4 |
| 预算/并发只有风险没有功能 | F-CM-06、3.4 |
| 协议只有路径无鉴权头 | 6.2 |
| 无验收门禁 | 各模块 + 第 7 节 |
| 引导管理员、密码、分享 | 2.1 |
| 压测 Go/Python 摇摆 | V1.6.2 **改回 go-stress-testing**（与询问/初稿一致，未再征询 Python） |

### 10.2 复查（V1.6.1）又修

| 问题 | 处理 |
| --- | --- |
| `kind` 既有 `benchmark+stress` 又有 `with_stress` | 一任务一种 kind，压测用 `with_stress` 派生子任务 |
| 流程暗示 Benchmark 与 RAG 同单混跑 | V1 禁止；连续两张确认卡 |
| LightRAG 怎么 query 未写 | 原生 `query` API，再映射内部结构 |
| REST `/tasks` 与 `/api/tasks` 不一 | 统一 `/api` |
| WS 长期 token 进 query | 短票 `ws_ticket` |
| 管理员不能取消他人任务 | RBAC 已补 |
| 黄金 QA 无版本 | 覆盖上传 +1 |
| 成功指标 3 个模型 vs 功能 5 个 | 统一 1–5 |

### 10.3 仍接受的限制

- MCP 完整 JSON Schema 开会时出。
- Prometheus 抓取网段依现网。
- Judge 不强制与被测不同模型。
- 无 Open API、无分布式压测。

---

## 附录 A  用例策略

对齐 [testcase-tools](https://github.com/Rue1218/testcase-tools) 公开策略：正向 / 反向 / 边界 / 等价 / 状态 / 场景；P0–P3。自研，不引入源码。

---

## 附录 B  问答复核（V1.6.3）

后答覆盖先答。未询问、由文档补的实现细节标「补全」，不是你的选项。

| 你的结论 | PRD | 一致？ |
| --- | --- | --- |
| 三模块：Agent（MCP+Skill）/ Benchmark / RAG，压测共享 | 1.2、1.6 | 是 |
| OpenAI Chat Completions + Responses + Anthropic Messages | 1.3、6.2 | 是 |
| Agent 主、表单辅 | 1.2、F-AGT-07 | 是 |
| 内部 MCP，Agent 当 Host | 1.6、3.1 | 是（长任务由 worker 调同一 MCP，避免 WS 绑死，询问未单独选） |
| 压测目标：模型推理 + RAG query，不压平台 | 4.2、5.6 | 是 |
| 评测 Skill + 用例生成 Skill | 5.4 | 是 |
| Agent/Judge 三种协议可切换，另配裁判 | F-AGT-06、F-BM-08 | 是 |
| PG 任务表 + worker，WS 只推进度 | 3.1、6.1 | 是 |
| RAG：LightRAG + 外部 HTTP | 5.3 | 是 |
| 外部 RAG 契约：仅 OpenAI Chat（后答覆盖「也可 Anthropic RAG」） | F-RAG-02 | 是（以最后一问为准） |
| 压测进现有 Grafana（后答覆盖「不对接」） | F-ST-04 | 是 |
| 自建账号 | 2.1 | 是 |
| FastAPI + Vue3 Naive UI | 文头、6.1 | 是 |
| WS 自定义事件流 | 5.1.3 | 是 |
| 单机 Compose | 1.3 | 是 |
| 多会话、会话内串行、会话间可并行 | 1.5、3.4 | 是 |
| 先评后压 | 3.2 | 是 |
| 文件本地盘 | F-CM-07 | 是 |
| Key 管理员池 | 1.6 | 是 |
| LightRAG 进同一 Compose | F-RAG-01 | 是 |
| 不内置公开集 | 1.3 | 是 |
| 核心人设固定；协议档可维护受审计补充提示词 | F-AGT-05 | 是 |
| 单团队；先文本后多模态 | 1.2、4.2 | 是 |
| 不涉密、不强制私有化 | 1.6 | 是 |
| 报告不进审批 | 1.6、4.2 | 是 |
| 用例不同步禅道/Jira | 1.6 | 是 |
| 接受 testcase-tools 自研对齐 | 附录 A | 是 |
| 压测内核 | 曾误写 Python，**已改回 go-stress-testing** | 已纠正 |

询问中未出现、文档自行补全（可改）：一任务一种 kind、预算默认 5 USD、平台并发默认 3、用例确认 72h、ws_ticket、Hit@K=5、prod 会签、通知渠道（企微/邮件/Webhook）。

### 本版（V1.6.3）相对问答仍无冲突的说明

- 「Agent 调 MCP」：Host 仍是 Agent；长任务进 PG 后由 worker / stress 执行，避免对话断线任务停。与「PG 队列 + worker」那一问一致。
- 外部 RAG 只用 OpenAI Chat：以最后一问为准；被测/Agent/Judge 仅支持三类协议。
- 压测 Grafana：以「需要接入」为准，覆盖更早的「不需要」。

### 会话上下文持久化修订（2026-08-20）

思考卡、工具/MCP 卡、技能徽标、确认卡及其回执均通过 `ws_events` 或会话状态保存；
流式增量仍为瞬态，成功回合额外保存 `thought.stream=think_final` 完整思考快照。
历史接口同时返回 `compact_summary` 与服务端 ContextMeter，刷新不得依赖浏览器临时状态。

### 协议档多模型端点修订（2026-08-21）

协议档在主模型配置之外，可选保存 Embedding 与 Reranker 的独立 URL、模型标识和 API Key；
三类 Key 均只写入受控环境文件，不进入数据库或任何响应正文。

| 文件 | 作用 |
| --- | --- |
| `backend/api/app/schemas.py` / `backend/api/app/profile_env.py` | 定义附加端点字段及按 profile 隔离的环境变量写入契约 |
| `backend/api/app/routers/profiles.py` / `backend/worker/app/profile_env.py` | CRUD 保存、脱敏返回与 Worker 只读解析 |
| `frontend/src/components/modals/ProfileModal.vue` / `frontend/src/views/AdminProfiles.vue` | 配置表单和协议档列表标识 |

### Agent 附件交互修订（2026-08-24）

| 文件 | 作用 |
| :--- | :--- |
| `backend/api/app/routers/files.py` | 扩展图片与 DOC/DOCX 上传白名单，继续执行单文件 20MB 校验 |
| `frontend/src/components/agent/AttachmentPreview.vue` | 提供图片缩略图、PDF/文本预览和 Office 文件类型卡片 |
| `frontend/src/views/Agent.vue` | 支持多选/拖拽上传、附件暂存、移除、上传状态与消息内展示 |
| `frontend/src/api/http.ts` | 同步文件上传响应的内容类型字段 |
| `backend/api/tests/test_files.py` | 增加附件扩展名白名单回归测试 |

### V1.15 修改代码文件与作用清单

| 实际修改文件 | 作用 |
| :--- | :--- |
| `docs/AI测试与评估平台-PRD.md` | 统一成员同权双人复核、目录/release 生命周期、独立导入队列、staging 并发发布、版本锁定及 M3 边界 |
| `docs/AI测试与评估平台-API.md` | 定义目录治理、导入租约与重试、稳定 staging 行 ID/revision、原子发布和任务快照接口契约 |
| `docs/AI测试与评估平台-测试数据集与黄金集采集技术方案.md` | 细化来源 manifest、队列领取/回收、审计、发布事务和与 PRD 一致的分期实施方案 |

### V1.16 修改代码文件与作用清单

| 实际修改文件 | 作用 |
| :--- | :--- |
| `backend/api/app/harness/skills/files/*/SKILL.md` / `storage.py` | 统一内置技能文件规格、持久化副本、文件存在校验、头部按需读取和全文工作流延迟加载 |
| `backend/api/app/harness/skills/registry.py` / `workflows.py` | Skill Hint 从文件头部生成，选中技能后才加载正文 |
| `backend/api/app/routers/admin.py` / `agent_prompt_settings.py` | 受审计的 Skill 预览/编辑和协议档补充提示词管理接口 |
| `backend/api/app/harness/prompts/system.py` / `routers/ws.py` | 固定核心系统策略与协议档补充提示词装配，禁止设置项替换核心规则 |
| `frontend/src/views/AdminProfiles.vue` / `frontend/src/components/modals/*` | Agent 技能文件预览/编辑与当前 Agent 提示词管理入口 |

### V1.17 修改代码文件与作用清单

| 实际修改文件 | 作用 |
| :--- | :--- |
| `backend/api/app/harness/execution/dispatch.py` / `feedback/rules.py` | 识别危险 bash、保留提权/网络硬拒绝，定义确认后才可执行的工作区修改范围 |
| `backend/api/app/harness/execution/toolnode.py` / `routers/ws.py` | 在 Runner 前执行 LangGraph 中断、持久化确认卡/回执并恢复同一图线程 |
| `backend/api/app/agent/react.py` / `agent/think_stream.py` | 收紧原始 reasoning 和工具前草稿正文，防止假性成功与过程卡堆积 |
| `frontend/src/components/agent/ToolApprovalCard.vue` / `ToolCard.vue` / `views/Agent.vue` | 提供确认/拒绝交互和 ToolCard 等待确认、已拒绝状态 |
| `frontend/src/api/ws.ts` / `api/types.ts` | 增加危险工具确认的 WS 上行/下行事件类型 |
| `backend/api/tests/test_bash_hitl.py` / `test_agent_react.py` / `test_stream_p3_integration.py` | 覆盖确认前不执行、拒绝不执行、ToolCall 草稿延迟投影和 bash 串行边界 |
| `docs/AI测试与评估平台-API.md` / `docs/AI测试与评估平台-Agent开发文档.md` | 固定 HITL 卡片、恢复、事件与过程输出契约 |

### V1.18 修改代码文件与作用清单

| 实际修改文件 | 作用 |
| :--- | :--- |
| `backend/api/app/agent/react.py` | 将 JSON ReAct `thought` 完全限制为内部控制字段；删除 ToolCall 前正文草稿投影，并在最终回合重新请求自然语言交付，防止把未执行动作说成结果 |
| `backend/api/app/harness/execution/dispatch.py` | 硬拒绝检测覆盖多段、嵌套 shell 与包装命令，确保 `bash -c "sudo …"` 等不会降级为可确认操作 |
| `backend/api/app/agent/plan_solve.py` / `reflect.py` | PlanCard 与确认卡保留为唯一可见规划产物；删除 Plan/reflect 的阶段 thought，避免每个图节点增加过程卡 |
| `frontend/src/views/Agent.vue` | 一个回合最多显示一张固定过程摘要卡；历史事件跳过 `thought`，阶段事件只更新生成状态，不创建对话卡 |
| `backend/api/tests/test_agent_react.py` / `test_agent_routing.py` / `test_agent_multiturn.py` | 覆盖 JSON ReAct thought 不出站、ToolCall 草稿不出站、Plan/Reflect 无阶段卡与最终回答重新生成 |
| `docs/AI测试与评估平台-PRD.md` / `AI测试与评估平台-API.md` / `AI测试与评估平台-Agent开发文档.md` | 统一过程卡、最终交付和历史重放边界 |


## 2026-09-09 协议档供应商与完整 URL 优化

详见 [协议档供应商思考适配](AI测试与评估平台-协议档供应商思考适配.md) V1.1：十个供应商新建入口、真实模型品牌图标、只读能力投影及 `full_url` 字段以该节定义为准。管理页和编辑弹窗删除思考强度设置，仅在对话输入框选择；AgentLoop 按供应商能力初始化，不再继承 legacy 全局思考偏好。完整 URL 开启后不追加版本或协议后缀，后台主模型调用使用同一规则。


### V1.24 修改代码文件与作用清单（审查日期：2026-09-15）

供应商模板推荐不再阻断未知型号；注册仍必须由用户触发真实请求。开关、固定思考、等级和预算使用不同展示语义，版本失效时要求重新验证。失败只展示安全分类，空响应、截断或关闭后仍有思考不能通过。

- `backend/api/app/llm/providers/reasoning_templates.py`、`llm/loop_contracts.py`：供应商方言与受控参数。
- `backend/api/app/profile_probe.py`、`profile_reasoning.py`：证据、超时、重复档位去重与版本生效范围。
- `backend/api/app/schemas.py`、`routers/profiles.py`、`routers/sessions.py`：能力展示契约。
- `frontend/src/api/types.ts`、`api/agentLoopTypes.ts`、`components/agent/loop/ThinkingControl.vue`、`AgentComposer.vue`、`components/modals/ProfileModal.vue`：模式文案及逐模型推荐。
- `backend/api/tests/test_reasoning_templates.py`、`test_loop_profile_selection.py`：自动化回归。

详见[API V2.2](./AI测试与评估平台-API.md)及[方案 V1.3](./AI测试与评估平台-模型思考模板自动继承实施方案.md)。

### V1.25 修改代码文件与作用清单（审查日期：2026-09-15）

Anthropic Messages 兼容供应商的思考配置必须由供应商模板解析。Kimi K3 只开放 `low/high/max` 并发出 `output_config.effort`，不伪造关闭开关；智谱 GLM 和火山方舟豆包开放关闭/开启并发出标准 `thinking.type`。任何模板都只有在真实探测取得思考证据后，才在 Agent 输入栏显示为可用。

| 修改文件 | 作用 |
| --- | --- |
| `backend/api/app/llm/providers/reasoning_templates.py` | 登记 Kimi、智谱和火山方舟的 Anthropic Messages 模板及受控参数映射 |
| `backend/api/app/llm/providers/anthropic.py` | 兼容供应商回放没有签名的 thinking 块，原生 Claude 的签名校验保持不变 |
| `backend/api/tests/test_reasoning_templates.py`、`backend/api/tests/test_loop_llm.py` | 覆盖模板推荐、最终 SDK 参数、关闭/强度边界及无签名 thinking 的工具回放 |
| `docs/AI测试与评估平台-API.md`、`AI测试与评估平台-模型思考模板自动继承实施方案.md` | 固化供应商差异、验证门禁和官方依据 |

### V1.26 修改代码文件与作用清单（审查日期：2026-09-15）

十家供应商的快速填充按 `供应商 × 协议` 保存官方 Base URL。选择协议时必须同步替换 URL 和建议模型；未公布 OpenAI 或 Anthropic 兼容层的组合显示为不可选。火山 Anthropic 入口明确限定 Coding Plan；NVIDIA NIM 的 Messages 与扩展思考能力按部署版本、模型和真实探测结果生效。

| 修改文件 | 作用 |
| --- | --- |
| `frontend/src/utils/profileVendors.ts`、`components/modals/ProfileModal.vue` | 协议 URL 矩阵、协议可用性、切换联动和适用范围提示 |
| `backend/api/app/llm/providers/reasoning_templates.py`、`providers/anthropic.py` | DeepSeek、NVIDIA NIM 的 Messages 模板与兼容 thinking 回放 |
| `frontend/tests/profileVendors.test.mjs`、`backend/api/tests/test_reasoning_templates.py` | URL、协议支持、模板推荐和 SDK 请求体回归 |
| `docs/AI测试与评估平台-协议档供应商思考适配.md` | V1.1 官方 URL 与协议支持矩阵 |

## V1.27 专家协作实施登记（2026-09-15）

依据[专家 Subagent 与多 Agent 协作技术方案](AI测试与评估平台-专家Subagent与多Agent协作技术方案.md)，开始分阶段实施。当前批次为 **P0 运行时基础接缝**，不等于 P0 全部门槛或 P1 专家调度已完成。

### 本批产品边界

1. 专家复用现有原生 AgentLoop；主会话仍为唯一面向用户的事实写者。子运行日志端口承载独立历史，`session_id` 保持授权所属会话，`run_id` 标识子运行。
2. 主回合正常结束、取消或异常时，先取消并等待当前回合拥有的子任务清理，再写主回合唯一终态。收尾开始后禁止继续创建子任务；累计实例额度不因完成而返还。
3. 同一协作可注入共享模型调用预算，按实际尝试累计（含网络重试），并限制模型流并发及单运行调用数。等待模型槽位不扣次数；已派发的失败或取消调用不返还次数。本批限额为同进程精确计数，不作为持久账本、token 硬限额或金额硬限额。
4. 本批通过确定性适配器验证独立运行和生命周期。生产 `SubagentLog`、协作表/迁移、权限快照、工作区隔离、`agent.*` 工具及前端面板仍未交付，不向用户宣称已可调度专家。既有 `task` 继续只表示任务规划。
5. 被测调用、裁判执行与批量评测继续遵循 Worker 分工；本批不修改评测分数、报告或榜单规则。

### 修改代码文件与作用清单

| 文件 | 作用 |
| --- | --- |
| `backend/api/app/harness/contracts/fact_log.py` | 最小事实日志接口、授权会话与运行命名空间分离 |
| `backend/api/app/agent/loop.py`、`runtime.py` | 日志端口、子任务终态前收拢、运行缓存和审批域隔离 |
| `backend/api/app/agent/collaboration_scope.py` | 当前回合的子任务所有权、累计上限和幂等取消清理 |
| `backend/api/app/agent/model_budget.py` | 可注入的共享模型调用预算和适配器包装 |
| `backend/api/app/harness/execution/scheduler.py`、`approval.py` | 工具绑定的运行身份和独立审批路由，保留授权会话 |
| `backend/api/tests/test_subagent_foundations.py` | 独立图运行、主子取消排序、审批和预算竞态实验 |

验证结果与后续退出门槛统一记录在技术方案 §22。

## V1.28 专家协作 P1 产品登记（2026-09-16）

1. 用户在 Agent 页向通用助手提出需要多人分工的目标后，主 Agent 可以自行列出专家、并行启动不同专家、等待或查询状态、读取成果并停止运行。用户无需手工建立固定工作流。
2. 每个专家拥有独立实例、运行状态、模型/专家/权限快照、事实历史和沙箱子目录。子专家只获得当前会话档位可自动执行的权限交集；不能在 P1 继续委派，也不能使用 bash、人工确认或直接创建评测 Worker 任务。
3. 主 Agent 与子专家共享每协作 80 次模型调用硬上限，最多 3 个模型流并发、8 个累计实例、每专家 20 次调用。页面显示已用调用数；该额度不代表 token 或费用硬预算。
4. Agent 页新增可折叠“专家协作”区域，展示协作目标、根回合、总状态、预算、专家名称、模型、目标、交付契约、成果与错误码。会话创建者可以停止单个专家或整组协作。
5. 协作状态写 PostgreSQL。刷新页面、浏览器 WS 重连或重新打开会话时，从持久查询接口恢复，不重复启动实例。主回合正常结束、取消或异常前，必须停止并等待尚未完成的前台子任务。
6. P1 仍为 API 单进程内的前台协作。专家信箱、共享工作项、继续委派、跨进程租约、服务重启续跑和关闭页面后后台执行分别属于 P2/P3，当前不得显示为已支持。
7. 被测模型、评分模型、批量 benchmark/RAG/stress 仍由 Worker 执行；专家协作只负责分析、组织和交付，不改变冻结的评测样本、裁判策略或榜单口径。

### V1.28 修改代码文件与作用清单

| 文件/目录 | 作用 |
| --- | --- |
| `backend/shared/models.py`、`backend/api/migrations/versions/f70e5a53bd54_新增专家协作与子运行事实表.py` | 协作、实例、运行、事实和命令回执持久化 |
| `backend/api/app/agent/collaboration.py`、`subagent_log.py`、`subagent_tools.py` | 前台协调、独立运行日志和六个模型工具 |
| `backend/api/app/routers/collaborations.py` | 持久查询、记录分页和用户停止操作 |
| `frontend/src/components/agent/loop/CollaborationPanel.vue` | Agent 页协作状态、成果与停止 UI |
| `backend/api/tests/test_subagent_collaboration.py` | 并行、幂等、隔离和工具契约回归 |

## V1.29 专家协作 P1 审查修复（2026-09-16）

关闭专家协作开关保留普通助手能力；停止整组后不允许该组继续派发新专家，旧请求的回执仍能恢复。同一主回合允许分批调度，新增运行时页面恢复“执行中”并提供整组停止。当前协作状态汇总已创建运行，父回合是否完成仍以其自身终态为准。单个专家停止不禁止主 Agent 后续安排其他专家。

父回合收尾保存包括最后一次汇总调用在内的最终调用预算，取消已派发请求不返还调用额度。本次无新增页面、接口、数据库迁移或后台运行能力。

### V1.29 修改代码文件与作用清单

| 文件 | 作用 |
| --- | --- |
| `backend/api/app/agent/loop_wiring.py` | 开关回退和当前回合预算收尾接线 |
| `backend/api/app/agent/collaboration.py` | 取消锁存、分批状态与最终预算持久化 |
| `backend/api/tests/test_loop_wiring.py`、`test_subagent_collaboration.py` | 六项复现与回归验证 |

## V1.30 评测专家协作连接目标（拟议、未实现，2026-09-16）

目标是在现有 P1 上接通“专家准备 → 冻结计划 → Worker 执行与独立评分 → 后续专家分析”。这不是新增后台运行产品；当前仅有 `general`、`testcase-agent` 与文本成果，以下角色、制品和交接均须分批实施并验收。

| 拟议能力 | 产品要求 | 验收依据 |
| --- | --- | --- |
| 专家角色 | 按需发布基准设计、数据、评分设计、结果分析四类职责及受控工具；主 Agent 保持统一协调 | 角色可发现且提示版本可追溯；不得以自由提示创建任意高权限角色 |
| 结构化交付 | 蓝图、候选数据清单、评分草案、报告分析分别版本化；服务端验证，作者不能自批准 | 缺失依据、越权引用和 hash 不符被拒绝，返工保留旧修订 |
| 数据发布 | 候选经独立验真及既有授权审核才成为正式资产 | 专家完成不等于题库已发布；沿用采集治理，隐藏答案用途隔离 |
| 计划确认 | 展示测试对象、样本、模型、评分、预算与版本变化；用户批准准确版本 | 改版使旧确认失效，重复确认不重复入队；不支持的执行能力明确拒绝 |
| 执行与评分 | Worker 执行冻结计划，客观题程序评分优先，开放题受限裁判；统计程序提供数字 | 主 Agent 不补写目标回答或修改评分，目标/裁判/组织历史隔离 |
| 报告分析 | 任务完成后可在新的用户回合组织专家分析固定报告修订 | 解释中的数字、排名和样本可追溯；专家意见不能改写成绩 |
| 前端恢复与控制 | 专家面板、计划确认、业务任务、报告通过持久引用关联，各自显示控制对象 | 刷新不产生新实例或任务；停止准备专家不误停已入队评测 |

具体实现以[专家协作方案 V0.8 §13.7–§13.11](AI测试与评估平台-专家Subagent与多Agent协作技术方案.md)、[基准方案 V0.5 §15–§16](AI测试与评估平台-大模型基准测试方法与榜单建设方案.md)及 API V2.8 拟议契约为准。J0–J3 是连接工作包，分别与 B0–B3 配合；不要求先实现 P2 信箱或 P3 后台服务。

范围约束：首批只接已支持的文本 benchmark；RAG、Agent 系统与模型能力分赛道，新增执行器另行登记。正式内部榜单仍需 B3 准入和统计能力，公开榜单不在当前已批准产品范围。单裁判加校准可作为起点，多裁判是否启用由冻结方法和质量/成本验证决定，不要求每道题启动多个专家。

### V1.30 修改代码文件与作用清单

| 文档 | 本次作用 |
| --- | --- |
| `docs/AI测试与评估平台-PRD.md` | 明确评测协作目标、边界和待验收能力 |
| `docs/AI测试与评估平台-API.md` | 登记拟议制品/计划字段与确认交接语义，不开放接口 |
| `docs/AI测试与评估平台-专家Subagent与多Agent协作技术方案.md` | 专家角色、协作顺序、权限隔离、J0–J3 工作包 |
| `docs/AI测试与评估平台-大模型基准测试方法与榜单建设方案.md` | 计划编译、Worker/报告交接、前端与 B 阶段验收 |

本次未修改业务代码、数据库或现有接口，不代表新增能力已可使用。

## V1.31 评测准备专家首批交付（2026-09-16）

落实 V1.30 的 J0/J1 子集：主 Agent 可调度基准设计、数据候选、评分设计三类专家，先取得蓝图，再将同会话已校验成果的精确引用交给其他专家。成果经服务端严格结构/内部引用校验，状态和依据在现有协作面板展示；数据候选和评分草案仍需独立审核、校准与后续用户确认。

本批引用仅适用于三类准备草稿，不接收正式数据资产、隐藏答案、原始文件路径或报告；每次运行产生独立且不可覆盖的第 1 版交付。稳定 ID 的递增修订、正式资产与报告接入、冻结计划确认入队、报告专家和榜单仍未交付。Worker 执行和正式评分保持现有契约。直接在页面选中准备专家仅为角色对话，结构化交付只在 `agent.spawn` 调度链中验收。

接口按 API V2.9；不新增业务任务种类、数据库表或列。运行仍是 P1 同进程前台语义，不能宣称后台服务或重启恢复。三类专家运行提示词属于运行代码，需完整本地门禁。真实供应商联合验收尚待完成。

### V1.31 修改代码文件与作用清单

`agent/experts.py`、三个 `expert_prompts/benchmark_*.md` 注册角色；`agent/preparation.py` 校验与交接；`agent/collaboration.py`、`subagent_tools.py`、`loop_wiring.py` 接通调度；前端 `types.ts`、`CollaborationPanel.vue` 展示草稿；`test_benchmark_preparation.py` 覆盖成功和拒绝路径。无 Worker 行为变更。


## 2026-09-17 Responses 协议与 New API / Ollama 供应商

- 协议枚举增加 `openai_responses`，适用于协议档创建/更新、模型发现、验证、Agent、Judge、被测模型和派生压测。默认路径为 `POST {base}/v1/responses`；已有版本段不重复追加，完整 URL 保留路径与查询串。
- 请求使用 `input`、`instructions`、`max_output_tokens` 和扁平函数工具，默认 `store=false`；工具结果以 `function_call_output.call_id` 配对。平台持有完整历史，Responses 的原始 output 项（含加密 reasoning）按现有协议状态兼容边界回填，不依赖 previous_response_id。
- 流式文本/思考摘要/函数参数映射到既有 Agent 事件，不增加 WS 事件名。失败/缺少终态不视为成功；截断以 length 收尾，非流式评测拒绝截断响应。input_tokens/output_tokens 归一用量，保留缓存与推理明细。
- 新建供应商增加 New API 与 Ollama。New API 可选 Chat、Responses、Messages，地址和模型由用户填写；实际通道支持以真实探测为准。Ollama 提供 Chat 和 Responses，默认地址 http://localhost:11434/v1，必须改为 API/Worker 可访问地址（容器中的 localhost 指容器自身），模型从服务获取或手填。
- Ollama 本地服务可用 `ollama` 作为 SDK 所需的非空占位 Key，受认证代理应填写真实 Key；不放宽其它协议档凭据校验。供应商仍沿用现有预设/端点/名称识别，不新增持久供应商字段。
- Responses 受控思考模板使用 reasoning.effort；各档位必须真实验证通过后才保存为可选能力。

### 修改代码文件与作用清单

| 文件 | 作用 |
| --- | --- |
| `backend/shared/responses.py`、`model_urls.py`、`models.py` | 共享编解码、端点及协议约束 |
| `backend/api/migrations/versions/*responses*.py` | 扩展协议 CHECK 约束，回退前拒绝存在 Responses 档 |
| `backend/api/app/llm/providers/responses.py`、`options.py`、`reasoning_templates.py`、`resolver.py` | 原生 Responses 流、历史回填与思考模板 |
| `backend/api/app/adapters.py`、`schemas.py`、`routers/profiles.py`、`agent/loop_wiring.py` | 旧调用路径、接口枚举与输入预算 |
| `backend/worker/app/protocol.py`、`stress.py` | Worker 评测及派生压测 |
| `frontend/src/utils/profileVendors.ts`、`providerLogo.ts`、`components/modals/ProfileModal.vue`、`api/types.ts` | 供应商预设、协议选择与类型 |

协议依据：[OpenAI Responses 迁移指南](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[Ollama OpenAI 兼容接口](https://docs.ollama.com/api/openai-compatibility)。


### V1.33 协议档验证结果修正（2026-09-17）

针对 Agent 用途，保存前验证补充原生工具调用和结果回填的无副作用探测，并与思考档位结果分别显示。只验证一个已通过思考档位，不能据此宣称所有档位或所有业务工具均可用。失败允许保存评测用途，但显著提示原生工具未通过；旧配置显示未验证，需用户在配置页重新测试。无 Agent 用途时不额外调用模型，不改变现有工具权限或后台任务流程。

修改代码文件与作用清单：后端 `profile_tool_probe.py` / `profile_probe.py` / `routers/profiles.py` / `schemas.py` 实现探测与状态；前端 `api/{types,http}.ts` / `components/modals/ProfileModal.vue` 展示独立结果并适配探测时限。


## New API 网关思考适配修复（2026-09-17）

New API 使用独立、可持久化的协议模板，不再按模型品牌推荐原厂请求扩展：`newapi-chat-effort-v1` 发送 `reasoning_effort`，`newapi-responses-effort-v1` 发送 `reasoning.effort`，`newapi-messages-effort-v1` 发送 `thinking.type=adaptive` 与 `output_config.effort`。Messages 另提供 `newapi-messages-budget-v1`，用于不支持自适应转换的通道。关闭分别发送 `none` / `thinking.type=disabled`；普通模型可选择 `newapi-no-reasoning-v1`，不发送思考字段。

统一五档仍为 off/low/medium/high/max；Chat/Responses 的已知 GPT/o 系列最高档沿用 OpenAI high/xhigh 映射，其它模型及未知别名验证 max 候选。Chat 使用 max_tokens，Responses 使用 max_output_tokens，Messages 使用 max_tokens。网关负责向上游转换；网关版本、别名、通道与模型决定实际有效档位，只有收到思考证据且完成探测的档位才能出现在对话强度选择中。模板声明不代表已验证支持。

显式 New API 模板可用于任意部署地址，并用于恢复编辑时的供应商和管理页品牌分组；运行时模型供应商继续用于各模型的内容回放。旧档需重新编辑并验证 New API 模板后更新已保存能力，不自动沿用旧探测结果。New API Chat 保留工具轮次的 reasoning_content；Messages 兼容无签名的网关转换思考块，原生 Claude 签名要求保持不变。

图标采用与官方公开 logo.png 一致的青紫／粉色渐变版，使用现有 MIT 图标包 newapi-color.svg；图标来源：[官方公开标志](https://github.com/QuantumNous/new-api/blob/69a50029819a26c53e6babd276d49cfe2f8880ad/web/public/logo.png)。参数依据：[Chat 接口文档](https://docs.newapi.pro/en/docs/api/ai-model/chat/openai/createchatcompletion)、[网关统一思考意图与七档解析](https://github.com/QuantumNous/new-api/blob/69a50029819a26c53e6babd276d49cfe2f8880ad/relaykit/relayconvert/reasoning/intent.go)、[Claude 转换](https://github.com/QuantumNous/new-api/blob/69a50029819a26c53e6babd276d49cfe2f8880ad/relaykit/relayconvert/reasoning/claude.go)。文档仅列 low/medium/high，而当前源码接受更多值，因此最高档必须真实探测。

修改代码文件与作用清单：
- `backend/api/app/llm/providers/reasoning_templates.py`：New API 专用目录、三协议字段和普通模式。
- `backend/api/app/llm/providers/{openai,anthropic}.py`、`backend/api/app/agent/loop_wiring.py`：网关思考内容回放与上下文计量一致。
- `frontend/src/utils/{providerLogo,profileVendors}.ts`、`frontend/src/components/modals/ProfileModal.vue`：保存模板恢复供应商与品牌分组。
- `frontend/src/assets/providers/{newapi.svg,README.md}`：渐变品牌图标与来源说明。
- 后端 New API 回归与前端供应商测试：三协议、多模型别名、档位投影与重新编辑。


## 连通检查与 New API Responses 一致性修复（2026-09-17）

列表连接测试沿用实际对话的 build_adapter / resolve_request，不再走旧非流式 call_protocol，不再把输出上限强设为 1，也不丢失保存的思考模板。使用 profile_reasoning 投影的已验证默认档位与实际输出上限；模板未验证或失效时返回 VALIDATION 并要求重新测试。探活等待首个有效正文、思考片段或合法终态，整段上限仍为 30 秒并关闭流及连接池。探活成功只说明本次模型接口可响应，不写回思考档位或工具能力。失败前端显示服务端安全 message，状态文案改为“测试未通过”，避免把参数拒绝、等待超时统称网络断开。

GPT-5.6（含 sol/terra/luna 及快照）的统一最高档发送原生 max；已知旧型号继续 high/xhigh。New API Chat/Responses 模板版本升至 3，OpenAI Chat/通用 Responses 模板升至 4，旧探测结果须重新验证后开放档位，避免使用旧 xhigh 回执宣称 max 已验证。依据：https://developers.openai.com/api/docs/models/gpt-5.6-terra 。

Responses 识别 response.reasoning_text.delta 与已有摘要增量，保留供应商返回的协议状态，不生成或推断隐藏推理。工具调用、加密推理回放与正常结束规则不变。依据：https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_reasoning_text_delta_event.py 。

修改代码文件与作用清单：
- backend/api/app/profile_check.py、routers/profiles.py：复用运行时适配器的单次流式探活与清理。
- backend/shared/reasoning.py、backend/shared/responses.py、backend/api/app/llm/providers/{options,reasoning_templates}.py：原生 max 映射、版本失效与增量识别。
- frontend/src/api/{types,http}.ts、views/AdminProfiles.vue、components/modals/CheckResultModal.vue：保留并展示安全诊断。
- API 探活/Responses 回归测试：真实 SDK 请求、连接清理、档位映射与安全诊断；前端类型检查验证诊断字段贯通。

## 协议档审查修复（2026-09-17）

- 凭据复用限定同源（协议、主机、有效端口）。主模型、Embedding、Reranker 跨源编辑均需显式提供新 Key；保存前探测与模型列表获取使用相同规则。模型列表只从已绑定端点选择环境凭据，不再按域名子串或协议向陌生主机兜底。只有 Key、没有配套地址的旧第三方环境配置需补充 BASE_URL 或显式输入凭据；原生 OpenAI/Anthropic 专属 Key 可匹配其官方默认地址。
- 首批五档探测仍并发，RATE_LIMITED 档位在首批结束后串行重试一次，最多十次实际思考请求（单并发触发场景为九次）。重试和工具探测共用 55 秒总预算；不重试认证、参数或模型错误，不因限流推断模型不支持思考。回执仍按唯一档位保存，无新增 REST 字段。
- Responses 完成快照按 output_index/content_index 校验正文与拒绝文本。可追加的缺失后缀补齐一次；正文冲突、回退、缺失或不能追加的错序返回响应协议错误，不能宣布成功。用户正文与持久回放快照保持一致。
- 不透明协议状态以服务器 HMAC 绑定端点、模型协议、档案版本及凭据身份，不持久化原始地址/凭据或普通密钥哈希。切换连接时使用既有消息迁移流程清理旧状态；旧版兼容键会在首次续聊时清理，正文及工具调用历史保留。修改思考档位不改变连接身份。

Responses 事件字段依据：[OpenAI 官方流式响应示例](https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create)。

修改代码文件与作用清单：
- `backend/shared/model_urls.py`、`backend/api/app/{profile_env.py,routers/profiles.py}`：同源判断、环境凭据绑定及编辑/探测/模型列表防护。
- `backend/api/app/{security.py,llm/resolver.py}`：受保护的协议状态连接作用域。
- `backend/api/app/profile_probe.py`：限流串行重试及剩余总时限。
- `backend/shared/responses.py`、`backend/api/app/llm/providers/responses.py`：正文终态核对、补齐与安全错误分类。
- `frontend/src/components/modals/ProfileModal.vue`：跨源变更重新填写密钥的提示。
- `backend/api/tests/test_{profile_credential_scope,replay_connection_scope,reasoning_templates,responses_protocol,newapi_reasoning,fetch_models}.py`：凭据边界、连接迁移、限流预算与正文一致性回归。

本轮验证：API 全量 1918 passed / 78 skipped；随后补充端口 0 边界并重跑凭据安全测试。Worker 51 passed，前端 99 passed；Ruff、typecheck、生产构建通过。所有新增供应商用例使用虚构凭据及本地替身，未使用生产密钥。


## V1.37 New API Responses 空终态兼容（2026-09-18）

当兼容网关已在流中提供一段可核验的完成正文、却遗漏成功终态的 `output` 数组时，平台可以保存并继续该段文本对话。此能力只适用于没有工具调用的单段助手正文；完成事件必须与前序增量一致。多段输出、拒绝与正文混合、工具调用、缺少完成正文、内容冲突或不完整终态必须明确失败，不能以推断数据继续会话。

工具能力的状态独立于文本兼容：该网关未提供可回放工具终态时，Agent 工具探测保持未通过，不对用户宣称支持工具。思考强度也仍以实际探测证据为准，空终态兼容不会授权任何未验证档位。

修改代码文件与作用清单：`backend/shared/responses.py` 限定重建空终态的安全边界；`backend/api/tests/test_responses_protocol.py` 覆盖单文本成功与工具/缺失完成正文拒绝。

## V1.38 Responses 终态完整性审查修复（2026-09-18）

空终态文本兼容必须核对所有已出现的消息与内容块，存在第二条消息、其他输出或完成快照冲突时明确失败，不静默截断回复。同一内容块的重复完成事件不得覆盖不同正文。缺少消息 ID 的兼容回复以普通助手消息续聊，旧版生成的固定 ID 也在历史回放时转换，避免老会话升级后继续发生身份重复。

修改代码文件与作用清单：`backend/shared/responses.py` 完善事件与终态一致性校验；`backend/api/app/llm/providers/responses.py` 处理新旧兼容历史；`backend/api/tests/test_responses_protocol.py` 验证冲突拒绝和三轮连续回放。

## V1.39 Responses 网关原生工具兼容（2026-09-18）

对于已通过逐项完成事件提供全部工具调用、仅遗漏最终输出数组的网关，允许按完整原始项完成工具往返。此修订扩大此前纯文本兼容范围，不放行缺少完成证据的工具增量。工具身份、完整参数、可回放推理以及所有已出现输出项都必须核验一致。

原生工具能力仍以真实调用和结果回填测试为准。已有协议档需重新测试更新后刷新状态；关闭思考档通过不等于全部思考档位可用。

修改代码文件与作用清单：`backend/shared/responses.py` 完整项恢复及参数核对；`backend/api/tests/test_responses_gateway_tools.py` SDK 往返和拒绝边界；`backend/api/tests/test_responses_protocol.py` Agent 工具执行与续聊回归。


## V1.40 Responses AgentLoop 展示与文件交付（2026-09-18）

公开思考摘要按真实增量和完成快照完整展示并渲染 Markdown；不可生成供应商未提供的内部思考。过程说明和最终回答遵从 Responses 阶段信息分段，复制/记忆不混入过程说明；不同模型的摘要长度、语言和真实工具步骤仍保持原样。新增字段向后兼容，不改变工具执行、重试与回合终态规则。

当前绑定工作区内实际成功 write 的产物增加下载入口，模型 sandbox 引用只能关联本轮精确匹配的真实结果；未绑定工作区、失败写入及越界路径不生成入口。旧历史缺少产物元数据时不凭文字猜测下载地址，可从“我的工作区”访问已生成文件。

修改代码文件与作用清单：Responses 公共解码与摘要辅助模块、供应商适配器、AgentLoop 流/持久投影、事件目录 V7、前端思考 Markdown/正文分段/文件下载映射及对应后端和浏览器回归。详细字段以 API V2.19 为准。


## V1.41 修订：取消与重连展示一致性（2026-09-18）

Responses 取消生成后保留已经显示的过程/回答分段；重新连接不再把已知 commentary 过程误标为本轮总结。阶段在输出项完成时才返回的兼容网关同样适用。Chat 与 Anthropic Messages 无阶段消息沿用既有展示；切换协议不串用私有状态。此次不新增协议、页面操作或能力声明。

### 修改代码文件与作用清单

- `backend/api/app/agent/{stream,loop}.py`：取消前缀的展示阶段进入持久事实。
- `backend/shared/responses.py`、`backend/api/app/llm/providers/responses.py`：模型回放与用户展示使用一致的已验证阶段。
- `frontend/tests/responsePresentation.test.mjs`：验证实时、重连和下一轮展示边界。

## V1.42 步骤预算与服务更新保护（2026-09-18）

步骤预算属于一次 Agent 回合的模型回复上限，不是 `task` 计划条目数量，也不表示工具失败。默认上限保持 16；接近上限时提示模型收敛工作，最后一次回复关闭工具并总结实际进度、产物与待办。工具任务尚未完成时不得显示已完成，也不自动无限续轮。用户可发送“继续”开启下一轮，读取已有工作成果。

部署在更新容器前暂停新回合准入，等待当前回合完成；等待失败或超时保留当前服务，不以更新为由自动停止用户工作。用户取消、服务关闭中断和异常重启恢复分别展示；已落盘文件与已持久化对话不会因为回合结束而删除。本次不提供后台续跑。首次升级旧版本由部署脚本在数据库屏障内确认主回合与专家运行均已结束，再进入短暂维护窗口停止并更新 API；查询失败或仍有活动工作时保留旧服务。具体契约和恢复边界见 API V2.31。

### 修改代码文件与作用清单

- AgentLoop `loop.py` / `loop_wiring.py`：预算内安排收尾回复并预留上下文。
- `runtime.py` / `loop_service.py` / `deploy_guard.py` 与 `routers/ws_v2.py`：真实中断原因和部署期间的新回合准入。
- `deploy/deploy.sh` / `deploy/drain-agents.sh`：更新容器前等待，异常时保留服务。
- AgentWorkspace 与 `workspaceDerived.ts`：服务重启中断提示；后端、部署与前端回归覆盖相应边界。

## V1.43 用例生成工作台与任务一致性（2026-09-26）

本轮修复既有“需求文档 → 候选用例 → 编辑保存 → 确认 → Excel/XMind 导出”流程。生成结果仍须人工采纳；不新增可执行 API/UI 自动化脚本生成、不将工作区专家 CSV 自动发布为平台用例库。

用例确认期限与任务状态在同一加锁事务中复核；保存失败或加载乱序不能造成草稿丢失及跨集覆盖。映射已发布数据集必须走已有版本治理入口，直接映射返回明确错误；尚未发布的数据集重复映射不重复插入。

### 修改代码文件与作用清单

- `frontend/src/views/Cases.vue`、`frontend/src/api/{http,types}.ts`、`frontend/nginx.conf`：生成契约、保存完整性、状态隔离、策略名称、请求等待和实际导出。
- `backend/api/app/routers/{cases,tasks}.py`、`task_policy.py`、`harness/execution/{task_tools,worker_bridge}.py`：来源授权、确认与配额、生产压测重新会签。
- `backend/shared/casegen.py`、API schema 与 Worker 用例执行器：配比一致性和模型系统字段保护。
- `backend/worker/app/{main,task_state,benchmark,stress}.py`：长任务租约失效收尾、停止后续批次、外部压测停止请求、确认超时竞争和发压前会签校验。
- API、Worker 与 Cases 浏览器回归及《用例生成审查修复记录》：本地验证证据和生产验收边界。

## V1.44 AgentLoop v2 会话上下文自动摘要（2026-09-26）

AgentLoop v2 在模型请求前按实际协议序列化的同源 token 估算检查上下文。输入达到可用输入预算的 85% 时自动总结较早历史，目标将输入降至该预算的 65% 以内，为后续对话留出余量；输出与步骤收尾提示的预留保持生效。最新用户输入与最近完整消息、工具调用及结果单元必须保留，不能为满足目标比例拆断工具配对或截断用户原文。

摘要只承载当前会话的目标、已确认约束、已完成工作、重要结果和待办。每次摘要由既有摘要与新覆盖的历史生成；源内容超出单次输入预算时分批处理，每回合最多 3 次摘要调用，并计入已有共享模型调用额度。内部推理、不透明协议状态和图片 base64 不作为摘要源；图片仅保留存在性说明，不把未读取的图片内容写成已知事实。

仅完整成功、正文非空的摘要可以提交为持久事实。原始消息与工具结果不删除、不改写，刷新或运行时重建后可以恢复相同摘要及历史边界，模型继续读取摘要与保留的原始历史。摘要失败时原请求仍可容纳则使用原文继续；原请求已超过硬预算则明确返回 `BUDGET_EXCEEDED`，不以静默丢弃旧历史继续执行。

上下文仪表显示本次实际请求是否使用摘要，并将实际摘要占用列为“会话记忆”。本期不提供跨会话偏好抽取、长期经验检索、语义召回或自动后台续跑；现有“引用记忆”草稿操作也不等同于这些能力。摘要正文不通过压缩通知发送到前端，通知仅展示压缩数量与预算元信息。

### 修改代码文件与作用清单

- `backend/api/app/agent/compaction.py`：同源预算判断、完整单元保留、受控摘要生成与持久摘要恢复。
- `backend/api/app/agent/{loop,loop_wiring,loop_presentation}.py`：模型前异步摘要接线、同会话输入回放、摘要调用预算及实际上下文占用。
- `backend/api/app/harness/contracts/loop_events.py`、`backend/api/app/agent/events.py`：内部摘要事实登记与仅含元信息的前端投影。
- `backend/api/tests/test_loop_compaction.py`：摘要成功、失败、历史恢复、工具配对、调用预算与取消边界回归。
- `backend/api/app/agent/model_budget.py`、`backend/api/tests/test_loop_compaction_pg.py`：并发专家之间的主回答额度预留与真实 PG 隔离恢复测试（需显式测试库）。
- `frontend/src/api/agentLoopTypes.ts`、`frontend/src/components/agent/loop/LoopContextMeter.vue`：可选压缩状态类型、会话记忆标签与状态展示。
- `docs/AI测试与评估平台-API.md`：内部事实、通知投影和仪表兼容字段契约。

## V1.45 会话摘要审查修复（2026-09-26）

模型拒绝生成摘要时，不得用拒绝句替换历史约束；按既有失败策略继续原文或明确终止。正常长回复后，下一轮仍可按完整消息和工具组分批摘要，不能仅因旧回合整体较大就放弃所有可处理的分批边界。

会话累计及可归属回合的 token 用量包含摘要请求已知的实际消耗，包括供应商已返回用量的失败摘要。摘要计量不产生额外助手气泡，不公开摘要正文，刷新或重放不重复累计。缺失用量、耗时或回合身份不推断补值。

### 修改代码文件与作用清单

- `backend/api/app/agent/compaction.py`：拒绝识别、完整组分批和摘要计量归属。
- Agent 事件投影、事实目录与前端 reducer/会话及回合统计：仅通过安全元数据补齐摘要消耗。
- API 摘要拒绝/分批/计量回归和前端统计/恢复测试：验证上述行为；接口细节见 API V2.26。

## V1.46 摘要可追溯与跨会话配置建议（2026-09-26）

会话摘要增加可核对的原始消息引用，保留少量完整用户原文作为独立证据。主 Agent 可按引用分页回读当前运行的历史正文和工具结果；不允许借引用读取其他会话、专家运行、内部推理或供应商私有状态。预算与原始事实保留规则沿用既有自动压缩契约。有界证据及固定摘要栏目用于降低遗漏风险，不等于保证所有历史约束都能无损保留。

已确认入队的评测配置可作为用户下一次私有会话的建议，当前要求优先、每次执行仍须确认并复验资源。配置保存与入队同事务，不能将取消、失败或仅计划的任务当作成功配置。共享会话及子专家不直接读取个人偏好；已注入个人偏好的私有会话不能转为团队共享，需另建共享会话并由用户明确提供需要共享的信息。

本期沿用既有偏好字段，不提供自动个人信息抽取、通用长期事实库、语义召回、Redis 记忆或后台续跑。这些后续能力不因摘要和配置建议上线而被视为已交付。

### 修改代码文件与作用清单

- `backend/api/app/agent/{compaction,history,loop_wiring}.py`：有界原文证据、当前运行来源回读、偏好注入及请求准备复用。
- `backend/api/app/harness/memory/preference.py`、`backend/api/app/routers/sessions.py`：已确认配置复用、资源过滤与共享隔离。
- 事实目录、权限档位及对应 API 回归：来源和敏感数据边界、确认事务、连续压缩恢复；接口以 API V2.27 为准。

## V1.47 个人长期记忆管理与召回（2026-09-26）

新增“我的记忆”页面，用户主动保存标题、正文、类别及适用范围。常用偏好在本人私有主会话提供默认建议，事实资料按关键词相关度召回；所有内容均标注为用户保存的资料，不等于平台核实的事实。当前明确指令优先，记忆不改变工具权限、审批或任务状态。

每人最多 200 条有效记忆，标题最多 80 字符、正文最多 2000 字符。适用范围为本人全局或本人活跃工作区；工作区记忆仅在会话绑定该工作区时使用。共享会话、他人会话及专家子运行不自动读取个人记忆。记忆以 PostgreSQL 既有 `memory_knowledge` 表持久化，保留手动来源、版本和撤回状态；无数据库结构变更。

保存、更正和删除均须用户在页面主动提交；首期没有根据闲聊自动抽取记忆，也不提供模型自主写入工具。编辑／删除必须携带读取版本，过期版本拒绝而非覆盖；删除撤回记录并清空记忆表中的正文和标题，后续召回不再读取。历史对话、已生成回答及审计来源不会因此被改写；正在发送的请求不能追溯撤回。前端应明确告知这一边界并在版本冲突后要求读取最新记录。

每次主模型请求重新查询当前有效记忆，最多五条且完整记录共用 2048 估算 token 预算；无相关事实不强行填充，过大记录整条跳过。检索先按属主及工作区过滤；常用偏好可参与无关键词匹配的召回，候选按关键词相关度、更新时间及 ID 稳定排序。中文双字与英文词只提供确定性关键词匹配，不宣称向量语义理解。实际注入才计入上下文“会话记忆”占用，并沿用 V1.46 的个人上下文使用标记与共享限制。

### 修改代码文件与作用清单

- `backend/api/app/harness/memory/personal.py`、`backend/api/app/routers/agent_memories.py`、`backend/api/app/main.py`：受控 CRUD、来源／版本／撤回、范围过滤、关键词召回及路由注册。
- `backend/api/app/harness/memory/preference.py`、`backend/api/app/agent/loop_wiring.py`：每次请求复验私有范围、动态召回、审计标记和真实输入计量。
- `frontend/src/views/UserMemories.vue`、`frontend/src/api/agentMemories.ts`、前端路由与主布局：本人记忆的主动管理入口及版本冲突处理。
- API 个人记忆／运行时回归与前端浏览器用例：CRUD、属主隔离、失效工作区、撤回与更正、分页／冲突及窄屏操作。

## V1.48 记忆审查修复（2026-09-26）

含已知凭据值的用户消息不作为压缩原文证据，恢复存量证据时也执行此限制，且不跳过较新敏感消息而突出旧约束。原始会话事实不被改写；新摘要输出含已知凭据时失败回退，不新增敏感摘要记录。

用户直接选择任一主专家后，均可按摘要来源回读本次运行原文；专家子运行继续隔离。记忆编辑期间工作区失效时，页面刷新目录、保留草稿，并允许用户在当前弹窗明确选择其他范围；不误报为记忆版本冲突，也不自动扩大到全局。真实版本冲突仍阻止覆盖。

### 修改代码文件与作用清单

- `backend/api/app/agent/compaction.py`、`backend/api/app/harness/security/loop_redaction.py`、`backend/api/app/harness/memory/personal.py`：派生记忆的凭据边界及统一识别。
- `backend/api/app/agent/experts.py`：主专家历史回读工具范围。
- `frontend/src/views/UserMemories.vue`：动态工作区失效恢复流程。
- 压缩凭据、主专家真实回读和记忆浏览器回归：验证新旧证据、子运行隔离、草稿与版本保护；接口细节见 API V2.29。

## V1.49 首次部署保护升级闭环（2026-09-26）

旧 API 缺少文件准入锁时，在数据库屏障下确认主回合和专家工作均已结束，再进入短暂服务切换。等待失败保留原服务；本次主动停止的 API 自动更新并恢复，手动停止的服务仍保持原状。新 API 恢复健康并加载部署保护后才能记录升级成功，不新增后台续跑能力。

### 修改代码文件与作用清单

- `deploy/legacy_agent_barrier.py`、`deploy/drain-agents.sh`：封闭空闲检查与停机间的新回合竞态，保留活动工作。
- `deploy/deploy.sh`：区分部署主动停机与用户手动停机，并验证恢复结果。
- `deploy/tests/test_drain_agents.py`、`backend/api/tests/test_deploy_legacy_barrier.py`：首次升级故障路径与真实 PostgreSQL 并发回归。

## V1.50 合并功能复查修复（2026-09-26）

Excel 同一批次内的重复用例编号按最后一条更新，不重复创建或报数据库冲突；被其他用例集占用的编号只生成一个本集副本，其他集合不变。刷新工作区、新建文件或新建工作区不丢弃当前未保存内容，保留原编辑目标，切换新资源沿用已有放弃修改确认。

### 修改代码文件与作用清单

- `backend/api/app/routers/cases.py`、`backend/api/tests/test_cases_audit.py`：导入批内编号复用与跨集合保全。
- `frontend/src/views/UserWorkspaces.vue`、`frontend/tests/e2e/workspaceAudit.spec.ts`：刷新/创建操作保留未保存内容及保存归属。

## V1.51 测试用例生成 Agent 与评测停用（2026-09-28）

平台的新增任务只支持根据需求生成**功能测试用例**。Agent 通过 `task.create(kind=testcase)` 入队，由 Worker 异步生成测试用例集草稿；`/cases` 的 AI 生成对话框继续使用同一生成提示词，候选用例经人工采纳后保存。生成内容应覆盖需求来源、风险与边界，包含可执行步骤和可观察的预期结果；需求未说明的业务规则标注待确认，不编造结论。已保存的草稿须在用例页审核、确认后入库，支持从任务定位到对应集合。

基准、RAG 评测和压测停止新建、重跑、领取及派生；现存排队和运行中的上述任务取消，运行中的压测停止发压。历史任务、事件与报告保留只读查询。导航与创建表单围绕用例生成收敛，历史数据仍可查看。本次不生成可执行测试脚本，也不启动新的评测或压测。

### 修改代码文件与作用清单

- `backend/api/app/task_policy.py`、`routers/tasks.py`、`routers/reports.py`：阻断旧任务和报告写入口，保留历史查询。
- `backend/worker/app/main.py`、`task_state.py`、`stress_spawn.py`：只领取用例任务，取消旧活动任务并停止压测派生。
- `backend/api/app/agent/`、`harness/` 与 `backend/shared/casegen.py`：仅向 Agent 展示用例生成能力，统一对话与用例页的生成规则。
- `frontend/src/layouts/MainLayout.vue`、`frontend/src/views/Tasks.vue`、`Cases.vue` 等页面：展示用例生成及草稿审核入口，收起旧评测创建操作。
- 对应 API、Worker 与前端回归测试：验证任务停用、草稿定位和生成契约。

## V1.52 用例审核与停用链路缺陷修复（2026-09-28）

多人审核同一用例集时，过期页面不得覆盖其他成员已保存的用例；保存和确认均需携带读取时的修订号，冲突时保留本地编辑并提示刷新。未确认草稿不得通过旧映射入口写入基准数据集。取消等待确认的用例任务须同步废弃关联草稿；废弃的用例集应明确显示终态，不再冒充可编辑草稿。历史报告只读，页面不再提供新的分享操作。新部署不得制造未真实执行过的评测和压测历史；旧压测停止请求失败必须保留可恢复的重试标记，直到引擎接受停止请求。压测服务不再接受新的发压请求。

### 修改代码文件与作用清单

- `backend/api/app/routers/{cases,tasks}.py`、`backend/api/app/schemas.py`、`backend/shared/models.py` 及迁移：用例修订号、审核门禁与取消联动。
- `backend/api/app/main.py`、`backend/api/app/seed.py`：停止伪造历史评测与压测任务。
- `backend/worker/app/{task_state,stress}.py`、`backend/stress/main.go`：旧压测停止失败的重试，并拒绝旧 Worker 迟到的发压请求。
- `frontend/src/views/{Cases,Tasks,Report}.vue` 与 API 类型：修订冲突、废弃态和历史只读界面。
- 对应 API、Worker、前端回归测试：验证并发保存、草稿入库、取消、停止失败及页面状态。

## V1.53 主要页面前端联调修复（2026-09-28）

任务中心必须按服务端分页读取历史任务；任务深链即使不在当前页，也应按 ID 读取详情。状态分布须明确只代表当前页，不展示写死的 Worker 在线数、吞吐曲线或 AI 巡检结论。调度中心的近期时间线只读取最近一页，星图活跃任务须按排队、运行中、待用例确认三种状态分别分页取全，旧运行任务不得因较新的历史终态任务而消失。历史报告导航应显示真实报告列表并可进入只读详情，快速切换报告时不得用迟到请求覆盖当前内容或错配导出文件。

实时模式下知识库接口失败应显示错误，不得回退示例资产、切块或检索结论；只有显式 Mock 模式可使用示例数据。用例页恢复已有 Excel 导入入口，当前用例集导入须携带已加载的修订号；存在未保存草稿时不得在导入、废弃其他集合或切换页面后静默丢弃。数据集保存失败或保存期间继续编辑时，也须保留草稿并阻止误切换；刷新数据集列表应保持已选黄金 QA，切换期间不得在新集下显示旧集行，迟到的旧行响应不得覆盖新选择及其草稿。

### 修改代码文件与作用清单

- `frontend/src/api/http.ts`、`types.ts`：任务与报告分页读取；知识库实时请求不再伪造成功数据。
- `frontend/src/views/{Tasks,Report,Cases,Datasets,Dispatch}.vue`、`layouts/MainLayout.vue`：主要页面真实数据、导航、导入、调度活跃任务及草稿保护。
- `frontend/tests/e2e/` 与对应夹具：覆盖分页、深链、报告乱序、调度旧活跃任务可见性、知识库失败及保存冲突。

## V1.54 前端联调复查缺陷修复（2026-09-28）

覆盖上传当前数据集前必须处理未保存草稿；上传期间不能继续编辑或保存旧表格。服务端将上传与正式行保存串行化，正式行保存携带与当前表格行一同读取的版本，不能使用列表或元信息刷新得到的版本；过期版本拒绝覆盖并保留页面草稿供人工核对。列表刷新发现当前数据集被外部删除时，保留草稿供导出。新建用例集的 Excel 导入须在单次事务中完成，解析或写入失败不产生空草稿。调度星图只读取有限的活跃任务样本，状态总数以服务端统计为准，不能按整个队列每几秒逐页拉取；本条替代 V1.53 的活跃任务取全要求。

### 修改代码文件与作用清单

- `backend/api/app/routers/{cases,datasets}.py`：原子新集导入与正式数据集版本校验。
- `frontend/src/api/http.ts`、`components/modals/{ImportCasesExcelModal,UploadDatasetModal}.vue`、`views/{Datasets,Dispatch}.vue`：单次导入、上传草稿保护、版本提交和有界调度轮询。
- 对应 API 与前端回归测试：覆盖失败导入、过期草稿、上传交错和大队列请求量。

## V1.55 用例生成与审核工作台（2026-09-28）

`/cases` 围绕“提供需求来源 → 生成候选 → 审核完整用例 → 保存草稿 → 确认入库”组织。来源可为粘贴的需求文本或本人已上传的需求文件；用户可指定 1–80 条及六类测试策略各自的整数百分比（合计 100，零权重表示不生成该策略），Agent 创建的异步用例任务也遵循同一规则。模型输出不符合所选策略或没有有效用例时，应给出失败提示供补充需求后重试，不生成空草稿。

生成数量是目标上限，实际候选可能少于指定条数；平台按 1–45 条与 46–80 条两档增加模型输出预算，但不因目标未达成而编造用例。模型配置无法满足预算或输出不可解析时明确提示失败。

候选审核需看到并可修改名称、模块、功能点、策略、优先级、前置条件、执行步骤和预期结果。采纳可保存为新草稿，也可追加到当前可编辑草稿；新草稿一次保存用例与自检结果，失败不留空集。保存后展示服务端自检和待补全项，用户继续人工审核；需求没有确定预期时明确标注待澄清，不编造业务结论。空用例集不能确认入库，已确认集合不能继续编辑。页面不再显示停用的评测映射状态或将用例称为“测试问句”。本次仍只生成功能测试用例，不生成可执行测试脚本。

### 修改代码文件与作用清单

- `backend/shared/casegen.py`、`backend/api/app/routers/cases.py`、`schemas.py`：候选过滤、分段输出预算、原子保存及用例任务参数。
- `backend/api/app/harness/execution/registry.py`、`harness/orchestration/{confirm,confirm_spec}.py`、`agent/workflow_nodes.py`、`agent/expert_prompts/testcase_agent.md`、`harness/skills/files/skill-testcase/SKILL.md`、`backend/worker/app/testcase.py`：Agent 确认及 Worker 使用指定数量与策略快照。
- `frontend/src/views/Cases.vue`、`frontend/src/api/http.ts`：来源输入、六策略百分比配置、完整候选审核、草稿保存和自检展示。
- 对应 API、Worker 和前端回归测试：覆盖生成与审核主流程、保存失败和参数边界。

## V1.56 知识库只读知识图谱视图（2026-11-03）

知识库工作台新增「知识图谱」入口：以当前知识库为范围，展示 LightRAG 在索引阶段抽取的实体与关系。数据直接读引擎自身的图存储，不额外调用大模型，也不改变检索与评测口径。

展示约束：

- **单知识库视角**：单实例多库共享同一图谱，服务端按文档来源标识 `{kb_id}__{doc_id}__{filename}` 前缀过滤实体与关系，前端只看到当前库的节点；
- **只读**：不提供实体/关系的编辑、合并、删除；单次节点上限 500，超出时明确提示已截断；
- **空态区分**：库内无文档、引擎未就绪、图谱为空分别提示，不用示例图冒充真实图谱；
- **失败不静默**：引擎不可用时接口返回 `UPSTREAM`，前端提示重试，不渲染空图充当"没有实体"。

### 修改代码文件与作用清单

- `backend/lightrag/adapter/{contract,engine}.py`、`backend/lightrag/app.py`：新增 `/graph` 内部端点、来源前缀过滤与节点/边映射。
- `backend/shared/kb.py`、`backend/api/app/routers/kb.py`、`schemas.py`：新增 `GET /api/kb/{id}/graph`。
- `frontend/src/components/drawers/KbGraphDrawer.vue`、`views/Kb.vue`、`api/http.ts`、`api/types.ts`、`layouts/MainLayout.vue`：图谱抽屉、力导向绘制与知识库菜单入口。
- 对应适配层与平台侧契约测试：覆盖按库过滤、截断、引擎不可用与空态。

## V1.57 工作区支持远程 SSH 目录（2026-11-05）

「我的工作区」从"平台本地目录"扩展为"本地目录 / 远程 SSH 目录"两种来源：

- **创建时选择类型**：本地（沿用 `data/workspaces/<id>`）或远程（填写主机、端口、登录用户、私钥文件名、远程根目录）；
- **凭据不落平台**：私钥文件放在服务器 `WORKSPACE_SSH_KEY_DIR`（只读挂载），平台只按文件名引用；也可选择「密码认证」——密码由用户在页面临时输入、只存当前标签页 `sessionStorage`，服务端不落库不写日志；
- **密码认证**：创建时选 `password`，首次打开工作区时在页面填入 SSH 密码即可，保存后立即用该密码拉一次目录树，密码错误当场可见；
- **凭据即边界**：平台默认不限制目标主机，能否连上由目标机是否接受该私钥决定；`WORKSPACE_SSH_ALLOWED_HOSTS` 非空时作为可选收紧；
- **文件操作同构**：远程工作区支持目录树、读取、写回、删除（SFTP）；上传、新建文件/文件夹、重命名、原文件下载本轮不支持，页面按类型隐藏入口；
- **命令执行**：远程工作区可执行单条非交互命令，采用**两阶段审批**——先登记请求并返回预览（目标主机、根目录、完整命令、有效期 300 秒），用户在页面上确认后才下发；一条命令只能执行一次，拒绝与执行都写审计；输出与退出码回显、超时 600s；
- **路径边界**：远程根目录可填任意绝对路径（含 `/`），但所有文件操作规范化后必须落在该根内，拒绝 `..` 与越界绝对路径。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/migrations/versions/9c1f4b7d2e30_工作区支持远程ssh.py`：工作区表增量 `kind/ssh_host/ssh_port/ssh_user/ssh_key_name/remote_root`。
- `backend/api/app/remote_workspace.py`（新增）：SSH/SFTP 访问、路径边界、命令执行、白名单与私钥引用校验。
- `backend/api/app/routers/user_workspaces.py`：创建分支、文件端点分派、`POST /{id}/exec`、本地专属操作拒绝远程。
- `backend/api/app/config.py`、`docker-compose.yml`、`.env.example`：私钥目录、白名单与超时配置。
- `frontend/src/views/UserWorkspaces.vue`、`api/http.ts`、`api/types.ts`：新建弹窗的类型与 SSH 字段、远程目录标记、远程隐藏上传入口。

## V1.58 HTTPS 入口（自签证书，2026-11-05）

生产入口是内网 IP，无法使用 Let's Encrypt（公网无法回连校验），且宿主机 443 已被其它应用占用。新增 `https` 服务提供加密入口：

- **地址**：`https://<HTTPS_HOST>:8443`，反代到 `web:80`（web 内再按路径转发 `/api`、`/ws`）；
- **证书**：宿主机执行 `deploy/gen-selfsigned.sh` 生成自签证书（CN/SAN 取 `HTTPS_HOST`），落在 `./data/https`，容器只读挂载；`deploy.sh` 在更新前检测缺失并自动补；
- **WebSocket**：透传 `Upgrade`/`Connection`，`/ws/agent/v2` 可正常握手；
- **浏览器提示**：自签证书未受信任，首次访问会出现"连接不是私密连接"，选择继续即可；要消除提示，把 `data/https/server.crt` 导入客户端"受信任的根证书颁发机构"；
- **不再暴露明文**：密码认证的 SSH 凭据只在 TLS 链路上传输。

### 修改代码文件与作用清单

- `docker-compose.yml`：新增 `https` 服务（`nginx:1.27-alpine`，`8443:443`，只读挂载配置与 `./data/https`）。
- `deploy/https/nginx.conf`、`deploy/gen-selfsigned.sh`：nginx 反代配置与宿主机自签证书生成（镜像用公共 `nginx:1.27-alpine`，无需自建）。
- `deploy/plan_services.py`：把 `https` 纳入构建/部署服务列表。
- `.env.example`：`HTTPS_PORT` / `HTTPS_HOST`。

## V1.59 远程工作区目录浏览（2026-11-05）

创建远程工作区时，「远程根目录」不再只能手输绝对路径：

- 点「浏览」连接目标主机后逐层列出**目录**（不列文件），支持「上级目录」导航；
- 「选择当前目录」把当前路径回填到远程根目录；
- 密码认证时可为浏览临时填入密码（只在本次请求内使用，不保存、不写审计明细）；私钥认证沿用服务端预置私钥；
- 连接或认证失败直接在弹窗内提示原因（缺密码、私钥不对、主机不可达）。

### 修改代码文件与作用清单

- `backend/api/app/remote_workspace.py`：`temporary_workspace`（未落库的临时连接对象，根目录固定 `/`）与 `browse_dirs`（只列目录 + 父路径）。
- `backend/api/app/routers/user_workspaces.py`：新增 `POST /api/workspaces/ssh/browse`，校验认证方式与凭证后代理到 SSH 层。
- `frontend/src/api/http.ts`、`views/UserWorkspaces.vue`：`browseSshDirs` 与创建弹窗的「浏览」入口、目录选择弹窗与回填。

## V1.60 需求基线与用例覆盖（N-01 MVP，2026-11-09）

### 范围

用例工作台新增「需求覆盖」入口，把需求原文中的编号条目保存为可校对基线，并回答三个问题：这份需求有哪些编号条目、当前用例集覆盖了哪些/漏了哪些、哪些用例可能对应哪条需求（仅候选，需人工确认）。

本期只做追溯与统计：不自动修改用例内容，不生成可执行脚本，不接 TMS，不新增 Benchmark / RAG / 压测入口。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-CASE-01 | 需求基线解析 | P0 | 从粘贴文本抽取 `FR-/NFR-/BR-/SR-` 编号条目，保存编号、标题、优先级、模块、原文行号；解析不出编号时拒绝创建空基线 |
| F-CASE-02 | 人工校对与确认 | P0 | 草稿状态可逐条修改标题/描述/优先级/模块；确认后只读，改版需新建基线；确认前不可作为覆盖率分母 |
| F-CASE-03 | 用例集绑定与覆盖率 | P0 | 用例集绑定已确认基线；展示整体覆盖率、P0 覆盖率、未覆盖清单、按模块覆盖率、已关联/未关联用例数 |
| F-CASE-04 | 自动关联候选 | P1 | 按“编号命中 > 标题完整命中 > 文本相似度 + 模块加成”生成候选；只返回候选，人工确认后才落库 |
| F-CASE-05 | 人工关联 | P0 | 按用例替换关联；空数组表示解除；单条用例最多 20 条需求，单次最多 5000 条用例 |

### 业务规则

- 需求条目必须来自原文，平台与模型都不扩写；无编号段落不进入分母。
- 同一基线内需求编号唯一；确认后只读；换绑基线清理旧关联。
- 覆盖率只代表“有用例关联”，不代表功能已验证或正确。
- 自动关联只做候选提示，不静默改写用例；关联不推进用例集 `revision`。
- 已废弃用例集不能绑定或调整关联；已确认用例集允许补充关联元数据，但用例内容仍只读。
- 需求或用例删除时关联级联清理；基线删除时用例集绑定置空。

### 与现有流程的关系

生成流程不变：PRD 推导向导、分批生成、AI 评审、确认入库、导出保持原行为。覆盖率不阻塞确认入库；P0 缺口在抽屉中明确展示，是否豁免仍由人工决定。数据与接口以 API.md V2.52 为准。

### 修改代码文件与作用清单

- `backend/shared/requirements.py`：编号抽取、中英文相似度、自动关联候选、覆盖率纯函数。
- `backend/shared/models.py`、`backend/api/app/models.py`：三张新表与 `case_sets.requirement_baseline_id`。
- `backend/api/app/schemas.py`、`routers/requirements.py`、`main.py`：需求域契约与路由注册。
- `backend/api/migrations/versions/a9d4e6f2b8c1_需求基线与用例覆盖.py`：三张新表与绑定列。
- `backend/api/tests/test_requirements.py`、`test_requirements_route.py`：抽取、去重、相似度、自动关联与覆盖率回归。
- `frontend/src/api/types.ts`、`api/http.ts`、`components/drawers/RequirementCoverageDrawer.vue`、`views/Cases.vue`：需求覆盖抽屉与客户端。
- `docs/AI测试与评估平台-API.md`：V2.52 契约登记。

## V1.61 全局搜索（N-07 MVP，2026-11-09）

### 范围

侧栏顶栏新增搜索入口，支持 `Ctrl/Cmd + K` 打开命令面板，跨八类资产只读检索：用例集、任务、会话、历史报告、知识库、数据集、工作区、个人记忆。本期不包含自然语言问答式搜索、语义检索、搜索历史云端同步。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-SRCH-01 | 命令面板 | P0 | `Ctrl/Cmd+K` 打开；Esc 关闭；点击遮罩关闭；顶部搜索框自动聚焦 |
| F-SRCH-02 | 跨实体检索 | P0 | 每类最多 5 条；用例集支持名称与用例正文命中；任务支持 ID/类型/状态；会话支持标题/ID；报告支持 ID/类型；知识库/数据集/工作区/记忆按名称或标题 |
| F-SRCH-03 | 权限过滤 | P0 | 私有会话仅属主可见，团队会话全员可见；工作区与个人记忆只搜当前成员自己的数据 |
| F-SRCH-04 | 键盘操作 | P0 | ↑↓ 在结果间移动，Enter 打开，Esc 关闭；高亮命中词 |
| F-SRCH-05 | 直达 | P1 | 会话打开 `/agent?session_id=`；任务 `/tasks?id=`；报告 `/reports/{id}`；用例集 `/cases?set_id=`；知识库 `/kb?kb_id=` |
| F-SRCH-06 | 最近搜索 | P2 | 本地保存最近 5 个关键词，可点击重搜；不跨设备同步 |

### 业务规则

- 搜索只读，不写审计、不改任何实体状态。
- 不返回任务 `config/result` 大 JSON、报告 metrics/raw、会话消息正文、记忆正文。
- 空搜索词返回空分组，不以 422 冒充“无结果”。
- 结果数量不代表总数；本期不做“查看全部”分页。
- 私有会话、他人工作区、他人记忆不得出现在结果中；权限以服务端为准，前端不自行过滤。
- 命令面板不替代页面内筛选；它是跨页面发现入口。

### 修改代码文件与作用清单

- `backend/api/app/routers/search.py`、`app/main.py`：`GET /api/search` 与路由注册。
- `backend/api/app/schemas.py`：`SearchItemOut/SearchGroupOut/SearchResultOut`。
- `backend/api/tests/test_search.py`：八类实体、权限、类型筛选、空查询与 URL 回归。
- `frontend/src/components/search/GlobalSearch.vue`：命令面板、键盘操作、最近搜索与高亮。
- `frontend/src/layouts/MainLayout.vue`：顶栏搜索入口与 `Ctrl/Cmd+K` 注册。
- `frontend/src/views/Agent.vue`、`views/Kb.vue`：`?session_id=` 与 `?kb_id=` 直达支持。
- `frontend/src/api/types.ts`、`api/http.ts`：搜索类型与客户端。

## V1.62 用例评审工作流与版本历史（N-02 MVP，2026-11-09）

### 范围

用例集从「AI 打一次分」升级为可留痕的人工评审：发起评审、指派负责人、整体/行级评论、通过或要求修改；AI 评审每次单独保留；重要节点生成不可变版本，可查看字段级 diff 并回滚为新草稿。

本期不改变 `case_sets.status` 三态、72h 确认、任务联动与确认入库流程；评审状态是独立字段，不阻塞确认。回滚只新建草稿，不修改当前集合或历史快照。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-REV-01 | 发起评审 | P0 | 草稿用例集可发起；指定负责人与截止时间；同时只允许一个 pending 请求 |
| F-REV-02 | 评审结论 | P0 | 通过 / 要求修改；要求修改必须填原因；结论写入评审请求与审计 |
| F-REV-03 | 评论 | P0 | 整体评论或关联单条用例；按时间倒序展示；已废弃用例集不可新增 |
| F-REV-04 | AI 评审历史 | P0 | 每次 `/ai-review` 追加一行，保留分数、结论、四维、问题清单、模型与时间；`checks` 仍保留最新一份兼容旧页面 |
| F-REV-05 | 版本快照 | P0 | 确认入库、评审通过、手动存版均生成不可变版本；版本号在用例集内递增 |
| F-REV-06 | 版本 diff | P1 | 以用例 ID 匹配，输出新增/删除/字段变更；默认对比上一版，第一版对比空快照；单次明细上限 500 |
| F-REV-07 | 回滚 | P1 | 以历史版本创建新草稿（新用例集 ID），复制用例与扩展字段；不覆盖当前集合 |
| F-REV-08 | 评审工作台 | P0 | 抽屉聚合状态、请求、评论、AI 历史与版本；支持发起/决策/评论/存版/对比/回滚 |
| F-REV-09 | 审计 | P0 | 发起、决策、评论、存版、回滚写 AuditLog；只记录 ID、数量与结论，不记录评论正文 |

### 业务规则

- 评审状态仅 `draft/reviewing/approved/changes_requested`，与 `status` 独立；确认后 `review_state=approved`。
- 已确认用例集只读：不再接受新的评审请求或手动存版；评论仍可作为审计备注追加，历史可查看。
- 评审请求同一时间只允许一个 `pending`；重复发起返回 `CONCURRENCY`。
- 评审结论不要求必须与 AI 评分一致；AI 评分是证据之一，不是门禁。
- 版本快照不可变；确认/评审通过自动生成，手动存版也生成新版本。
- 回滚生成的新草稿保留需求基线绑定、扩展列定义与自检结果；用例 ID 重新生成。
- 字段 diff 忽略排序变化；空字符串与 `null` 视为等价；扩展字段按 JSON 比较。
- 评论不修改用例内容，也不推进 `revision`；评论正文只存库，不进入模型上下文。

### 数据与接口

新增表：`case_review_requests`、`case_review_comments`、`case_review_runs`、`case_set_versions`；`case_sets` 增量 `review_state` 与 `review_assignee_id`。接口见 API.md V2.53。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/app/models.py`：评审请求/评论/AI 历史/版本表与用例集评审字段。
- `backend/api/migrations/versions/c1e7f3a9d2b4_用例评审与版本历史.py`：新表、索引与绑定列。
- `backend/shared/case_review.py`：用例快照归一、字段级 diff、截断与计数。
- `backend/api/app/case_review_service.py`：版本号、快照生成、批量用户名投影。
- `backend/api/app/routers/case_reviews.py`：评审工作台、请求/决策/评论、版本列表/详情/diff/回滚。
- `backend/api/app/routers/cases.py`：`/ai-review` 追加历史；确认入库前生成版本。
- `backend/api/tests/test_case_review.py`、`test_case_review_route.py`：diff 纯函数与路由回归。
- `frontend/src/components/drawers/CaseReviewFlowDrawer.vue`、`views/Cases.vue`、`api/types.ts`、`api/http.ts`：评审工作台抽屉、评论、AI 历史、版本对比与回滚。

## V1.63 用例质量看板（N-03 MVP，2026-11-09）

### 范围

新增 `/case-quality` 页面，按 7/30/90 天聚合用例生成运行与质量：

- 运行数、成功/失败/取消/待确认；
- 生成用例数、确认入库数、采纳率、任务成功率；
- 最新 AI 评审分的均值与已评分用例集数；
- 按天趋势、按模型/协议档、按状态、按模块分布；
- 最近 50 条运行明细，可直达任务与用例集。

本期只读现有 `tasks` / `case_sets` / `case_review_runs` / `case_items`，不新增生成链路、不改 Worker 生成逻辑（仅在任务结果补充模型 ID/名称用于归因）。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-QLT-01 | 时间窗切换 | P0 | 7/30/90 天；默认 30 天；切换重新聚合 |
| F-QLT-02 | 核心指标 | P0 | 运行数、生成数、确认数、采纳率、成功率、AI 评分均值、评审通过数 |
| F-QLT-03 | 按天趋势 | P1 | 每日运行/生成/确认；柱高按生成数归一，深色为确认部分 |
| F-QLT-04 | 模型归因 | P1 | 按协议档/模型聚合运行、生成、确认、采纳率、AI 均分 |
| F-QLT-05 | 状态与模块分布 | P1 | 任务状态计数；模块用例数 Top 20 |
| F-QLT-06 | 最近运行 | P0 | 最多 50 条；显示目标/生成、确认、采纳率、AI 分、模型、耗时、错误码 |
| F-QLT-07 | 直达 | P1 | 用例集跳 `/cases?set_id=`；任务信息保留 `task_id` 供后续深链 |

### 业务规则

- 成功率 = `succeeded / 时间窗内运行总数`；待确认、运行中不并入成功或失败。
- 采纳率 = `confirmed_count / generated_count`；分母为 0 时显示 0，不伪造百分比。
- 模型归因缺失时显示“未记录”，不按协议档猜模型。
- AI 均分只统计有 `case_review_runs` 的用例集，取每个集合最新一次；没有评分显示“—”。
- 时间窗按任务 `created_at` 统计；运行耗时为 `started_at → finished_at`，缺失不推算。
- 看板只读，不修改任务、用例集或评审状态；覆盖率与 AI 分不等于功能正确或已执行验证。
- 单次最多扫描 1000 条任务；超过时只统计最近 1000 条并在页面说明。

### 修改代码文件与作用清单

- `backend/api/app/routers/metrics.py`、`app/main.py`、`app/schemas.py`：`GET /api/metrics/casegen` 与聚合契约。
- `backend/worker/app/testcase.py`：成功任务结果补充 `profile_id/profile_name/model_name`，供模型归因。
- `backend/api/tests/test_casegen_metrics.py`：聚合、单日窗口与参数边界回归。
- `frontend/src/views/CasegenQuality.vue`：质量看板页面。
- `frontend/src/router/index.ts`、`layouts/MainLayout.vue`：`/case-quality` 路由与「用例质量」入口。
- `frontend/src/api/types.ts`、`api/http.ts`：指标类型与客户端。

## V1.64 需求变更分析（N-04 MVP，2026-11-09）

### 范围

需求覆盖抽屉新增「需求变更分析」：从当前已确认基线派生一个新版本草稿，解析新需求原文，展示新增/删除/修改条目，以及旧基线绑定的用例集中受影响的用例。

本期只做**分析**：不自动创建、修改或废弃用例，不改变用例集绑定，不自动确认新版本。用户核对差异后可确认新版本，再按影响清单人工处理。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-CHG-01 | 派生新版本 | P0 | 只能从已确认基线派生；保留 `parent_id`，新版本为草稿，需人工确认 |
| F-CHG-02 | 版本差异 | P0 | 按需求编号匹配，输出新增/删除/字段修改；字段含标题、优先级、模块、描述 |
| F-CHG-03 | 影响分析 | P0 | 找出旧基线绑定的用例集与关联用例；标注“需求已修改/需求已删除” |
| F-CHG-04 | 页面展示 | P0 | 在需求覆盖抽屉中展示差异计数、明细（各 20 条）、影响用例集与用例（前 50 条） |
| F-CHG-05 | 确认新版本 | P0 | 核对后可确认草稿；确认沿用 N-01 规则，确认后只读 |
| F-CHG-06 | 链接直达 | P1 | 影响用例集可跳转 `/cases?set_id=` |

### 业务规则

- 新版本必须从已确认基线派生；草稿不能作为父版本，避免版本链越过人工确认。
- 版本差异以需求编号为主键；编号变化视为“删除 + 新增”，不做模糊匹配。
- 空字符串与缺失值视为等价；排序变化不算修改。
- 影响分析只查旧基线的绑定与关联，不修改任何用例；未关联用例不出现。
- 新版本草稿可以预览差异（确认前），但不能被用例集绑定。
- 明细各限 500 条，页面展示各 20 条/前 50 条；超出明确提示截断。
- 不自动创建变更草稿；批量处理留到后续批次，避免“分析即改库”。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/app/models.py`：`requirement_baselines.parent_id`。
- `backend/api/migrations/versions/e2a6b9c4d7f1_需求基线版本链.py`：版本链字段、索引与外键。
- `backend/shared/requirements.py`：`diff_requirements` 纯函数。
- `backend/api/app/requirement_change_service.py`：版本派生、差异、影响分析。
- `backend/api/app/routers/requirements.py`、`app/schemas.py`：版本/差异/影响接口与契约。
- `backend/api/tests/test_requirements.py`、`test_requirements_route.py`：差异与改版链路回归。
- `frontend/src/components/drawers/RequirementCoverageDrawer.vue`、`api/types.ts`、`api/http.ts`：改版分析交互与客户端。

## V1.65 用例资产库（N-05 MVP，2026-11-09）

### 范围

用例集确认入库时，把用例物化为跨用例集的只读资产快照，形成 `/case-assets` 资产库：

- 按关键词、模块、策略、优先级、标签检索；
- 查看完整前置/步骤/预期，维护人工标签；
- 用名称/预期/步骤对最近 500 条资产做文本查重提示；
- 为历史已确认用例集回填资产（幂等）。

本期不做语义向量去重、自动合并、跨集合复制/引用；这些留到下一批。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-AST-01 | 确认物化 | P0 | 用例集确认入库时写入资产；同一源用例重复物化幂等，不覆盖已有标签 |
| F-AST-02 | 资产检索 | P0 | 关键词命中名称/功能点/预期/前置/步骤；支持模块、策略、优先级、标签筛选与分页 |
| F-AST-03 | 资产详情 | P0 | 展示完整字段、来源用例集与版本；来源删除后仍保留快照 |
| F-AST-04 | 标签维护 | P0 | 最多 10 个、单标签 20 字；去重、去空白；覆盖式保存并审计 |
| F-AST-05 | 文本查重 | P1 | 名称 65%、预期 25%、步骤 10% 加权；只返回候选，不自动合并 |
| F-AST-06 | 历史回填 | P1 | 最近 100 个已确认用例集补齐资产；幂等 |
| F-AST-07 | 概览 | P1 | 总数、来源集合数、模块 Top 15、标签 Top 30 |

### 业务规则

- 资产是确认时点的快照，后续改用例集不影响资产；重新确认不会覆盖标签。
- 资产不因来源用例集删除而消失；来源 ID 置空，页面显示“来源已删除”。
- 标签是人工元数据，不改变用例正文与用例集 revision。
- 查重只做提示，不自动合并、不自动删除；分数低于 0.2 不返回。
- 资产检索全员可读；标签修改记录操作者与前后值。
- 历史回填只处理 `status=confirmed` 的用例集；不回填草稿/已废弃集。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/app/models.py`：`case_assets` 表与索引。
- `backend/api/migrations/versions/f5c1d8a3b6e2_用例资产库.py`：迁移。
- `backend/api/app/case_asset_service.py`：物化、回填、检索、标签、统计、查重。
- `backend/api/app/routers/case_assets.py`、`routers/cases.py`、`app/schemas.py`：接口与确认物化接线。
- `backend/api/tests/test_case_assets.py`：物化、检索、标签、查重、回填回归。
- `frontend/src/views/CaseAssets.vue`、`router/index.ts`、`layouts/MainLayout.vue`：资产库页面、路由与导航。
- `frontend/src/api/types.ts`、`api/http.ts`：资产类型与客户端。

## V1.66 站内通知中心（N-08 MVP，2026-11-09）

### 范围

新增站内通知：

- 用例生成完成（待确认）与生成失败；
- 评审指派给他人、评审通过/要求修改；
- 顶栏铃铛未读徽标、最近 8 条下拉、`/notifications` 全部/未读列表；
- 单条已读、全部已读、点击跳转任务或用例集。

本期不做邮件、企业微信、Webhook 外发，也不做通知模板配置；外发渠道留到后续。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-NOT-01 | 任务通知 | P0 | 用例生成进入待确认/失败时通知任务创建者；链接直达用例集或任务 |
| F-NOT-02 | 评审通知 | P0 | 指派给他人时通知负责人；评审结论通知请求发起人（自己操作自己不发） |
| F-NOT-03 | 顶栏徽标 | P0 | 未读数每 30 秒轮询；页面隐藏时暂停，恢复可见时刷新 |
| F-NOT-04 | 通知列表 | P0 | 全部/未读筛选、分页、单条已读、全部已读 |
| F-NOT-05 | 去重 | P0 | 同一用户同一事件只保留一条，Worker 重试不刷屏 |
| F-NOT-06 | 权限隔离 | P0 | 只能读/标记自己的通知；他人通知返回 404 |

### 业务规则

- 通知只是提醒，不是状态事实源；任务状态以任务页为准。
- 通知正文只含安全文案、任务/用例集名称与 ID，不复制上游原文、密钥或完整提示词。
- `dedupe_key` 唯一；重复写入直接跳过，不报错。
- 指派给自己不产生通知；自己评审自己的请求不产生结论通知。
- 读/未读不回写业务实体，也不进模型上下文。
- 保留 90 天；清理任务留到数据生命周期批次。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/app/models.py`：`notifications` 表。
- `backend/api/migrations/versions/b8e4d2f7c1a3_通知中心.py`：迁移。
- `backend/api/app/notification_service.py`：追加、去重、列表、未读、已读。
- `backend/api/app/routers/notifications.py`、`routers/case_reviews.py`、`app/main.py`：通知接口与评审接线。
- `backend/worker/app/testcase.py`、`models.py`：任务完成/失败通知。
- `backend/api/tests/test_notifications.py`、`worker/tests/conftest.py`：通知回归与测试表。
- `frontend/src/components/notifications/NotificationBell.vue`、`views/NotificationCenter.vue`、`layouts/MainLayout.vue`、`router/index.ts`：铃铛、通知页与路由。
- `frontend/src/api/types.ts`、`api/http.ts`：通知类型与客户端。

## V1.67 Agent 历史轨迹查询（N-09 MVP，2026-11-09）

### 范围

Agent 会话顶栏新增「历史轨迹」：读取已持久化的 `agent_events`，按回合聚合展示：

- 每轮开始/结束时间、状态、事件数、工具调用数、模型尝试数；
- 每轮 prompt/completion/total token 汇总；
- 事件级时间线：模型、工具、审批、问题、运行时错误等类型与状态；
- 工具耗时、错误码、token 片段。

本期只读查询，不新增结构化轨迹表，不返回消息正文、工具参数/结果、提示词或凭据；`harness_turns/spans/diagnostics` 的正式落库仍属后续批次。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-TRC-01 | 回合列表 | P0 | 最近 30 轮，按回合号倒序；显示状态/时间/事件数/工具数/token |
| F-TRC-02 | 回合详情 | P0 | 按 seq 正序返回事件元数据；最多 500 条 |
| F-TRC-03 | 脱敏 | P0 | 只返回 type/seq/ts/name/status/duration/error_code/token；不含正文、参数、结果、提示词 |
| F-TRC-04 | 权限 | P0 | 私有会话仅属主/管理员可见；他人会话统一 404 |
| F-TRC-05 | 长会话窗口 | P1 | 最多读取最近 5000 条事件，避免超大会话拖垮接口 |
| F-TRC-06 | 页面入口 | P0 | Agent 会话顶栏「历史轨迹」打开抽屉；左侧回合、右侧事件时间线 |

### 业务规则

- 轨迹是诊断辅助，不替代审计；事件事实以 `agent_events` 为准。
- 事件名称与状态只做白名单式投影；未知字段一律不返回。
- 没有 turn 号的事件不进入回合聚合。
- 工具失败只展示错误码/状态，不展示上游原文。
- 轨迹查询只读，不写库、不改会话状态。

### 修改代码文件与作用清单

- `backend/api/app/routers/traces.py`、`app/schemas.py`、`app/main.py`：轨迹摘要/详情接口与路由。
- `backend/api/tests/test_traces.py`：回合聚合、脱敏与权限回归。
- `frontend/src/components/drawers/TraceHistoryDrawer.vue`、`views/Agent.vue`：历史轨迹抽屉与入口。
- `frontend/src/api/types.ts`、`api/http.ts`：轨迹类型与客户端。

## V1.68 Token 用量中心（N-10 MVP，2026-11-09）

### 范围

新增 `/usage` 页面，按 7/30/90 天聚合 assistant 消息的 `turn_stats.usage`：

- 模型调用次数、会话数、成员数；
- 输入/输出/总 token；
- 按天趋势、按模型/协议档、按会话属主；
- 最近 50 次调用（会话、模型、token），可直达历史会话。

本期**不做费用估算**：平台尚未配置可信的逐模型单价；页面明确提示，不用单一价格冒充全部模型成本。预算阈值、单价维护与告警留到后续批次。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-USE-01 | 时间窗 | P0 | 7/30/90 天；默认 30 天 |
| F-USE-02 | 核心指标 | P0 | 调用、会话、成员、输入/输出/总 token |
| F-USE-03 | 按天趋势 | P1 | 每日调用与 token；柱高按当日总 token 归一 |
| F-USE-04 | 模型归因 | P1 | 模型/协议档、调用、会话、输入/输出/总量、占比 |
| F-USE-05 | 成员归因 | P1 | 按会话属主聚合调用与 token；共享会话归创建者 |
| F-USE-06 | 最近调用 | P0 | 时间、会话、模型、输入/输出/总量；最多 50 条 |
| F-USE-07 | 费用口径 | P0 | 未配置单价时只展示 token，不展示费用 |

### 业务规则

- 只统计 `role=assistant` 且 `turn_stats` 非空的消息；用户消息不计。
- `usage` 缺失时用 prompt+completion 兜底；全缺失不计入调用数。
- 时间窗按消息 `created_at`；最多扫描 5000 条，超出只统计最近窗口。
- 共享会话的用量归会话创建者；成员名缺失显示“未记录”。
- 只读聚合，不写库、不修改会话或消息。
- 不返回消息正文、提示词、工具结果或凭据。

### 修改代码文件与作用清单

- `backend/api/app/routers/usage.py`、`app/schemas.py`、`app/main.py`：用量聚合接口与路由。
- `backend/api/tests/test_usage.py`：聚合、兜底、权限与参数边界回归。
- `frontend/src/views/UsageCenter.vue`、`router/index.ts`、`layouts/MainLayout.vue`：用量页、路由与导航。
- `frontend/src/api/types.ts`、`api/http.ts`：用量类型与客户端。

## V1.69 用量费用估算（N-10b MVP，2026-11-09）

### 范围

用量中心新增按模型的 USD/百万 token 单价配置与费用估算：

- 读取/批量保存模型单价；
- 用量汇总、按模型、最近调用展示费用；
- 未配置单价的调用明确标记“未计价”，不计入总费用；
- 价格只支持 USD，避免多币种直接相加。

费用是估算值，不作为财务结算依据；预算阈值与告警仍留后续。

### 功能需求

| 编号 | 功能 | 优先级 | 说明 |
| --- | --- | --- | --- |
| F-USE-08 | 单价配置 | P0 | 按模型名 upsert 输入/输出单价，单位 USD/1M token |
| F-USE-09 | 费用估算 | P0 | `(prompt*input + completion*output)/1_000_000`，保留 6 位小数 |
| F-USE-10 | 未计价标记 | P0 | 无单价的调用显示“未计价”，总费用不把它们算作 0 |
| F-USE-11 | 归因 | P1 | 按模型与最近调用展示费用；已计价/未计价调用数 |
| F-USE-12 | 审计 | P0 | 批量保存记录模型名列表，不记录金额以外的敏感信息 |

### 业务规则

- 单价按模型名唯一；模型改名视为新模型，需重新配置。
- 未配置单价的模型 `cost_usd=null`，总费用只累加已计价调用。
- 所有单价统一 USD；人民币换算后续做，不在本期混算。
- 保存单价只影响之后的展示，不重算历史账单；历史聚合仍按当前单价估算，页面标注“估算”。
- 单价为 0 视为已配置但免费，仍计为 priced；与未配置区分。
- 只读汇总与价格配置均不返回消息正文/提示词。

### 修改代码文件与作用清单

- `backend/shared/models.py`、`backend/api/app/models.py`：`model_prices` 表。
- `backend/api/migrations/versions/d3f7a1c9e6b2_模型价格.py`：迁移。
- `backend/api/app/routers/usage.py`、`app/schemas.py`：费用聚合与单价接口。
- `backend/api/tests/test_usage.py`：费用、未计价与单价保存回归。
- `frontend/src/views/UsageCenter.vue`、`api/types.ts`、`api/http.ts`：费用 KPI/列与价格配置弹窗。
