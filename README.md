# AI 测试与评估平台

面向单一研发团队的内部平台，当前定位是**测试用例生成 Agent**：把需求文档转成可审核的功能测试用例，并围绕用例提供评审、版本、覆盖率、资产沉淀和质量度量。

项目不是通用聊天机器人：对话是需求拆解与工具协作的入口，耗时的用例生成统一进入任务队列执行；生成结果先存为草稿，**人工审核确认后才入库**，全程留有事件与审计记录。

> 产品范围以 [PRD](docs/AI测试与评估平台-PRD.md) 为准；接口、字段和 WebSocket 事件以 [API 文档](docs/AI测试与评估平台-API.md) 为准；工程约定见 [AGENTS.md](AGENTS.md)。

> **产品边界说明（2026-09-28 起）**：平台早期的基准评测（Benchmark）、RAG 质量评测与共享压测已**全部停用**，不再新建、领取或派生任务；历史任务、报告、数据集与知识库仅保留只读查询。下文只描述当前可用能力。

## 项目介绍

需求到测试用例的转换通常依赖人工逐条编写，覆盖是否完整、需求变更影响哪些用例、AI 生成的用例是否可用，都难以追溯和度量。本平台把这条链路收敛到一个工作台：

1. 在 Agent 对话或 `/cases` 用例工作台中提交需求，按需求分节分批生成候选用例；
2. 候选用例保存为草稿，经人工评审、修改后确认入库，并沉淀为可检索的用例资产；
3. 基于需求基线计算覆盖率、分析需求变更影响，用质量看板跟踪采纳率与 AI 评审分数。

平台支持多种上游模型协议（OpenAI Chat Completions、Anthropic Messages 等），调用细节收敛在协议档中；平台模型由管理端维护，成员也可配置仅自己可见的个人模型。AgentLoop 提供会话、专家技能、受控工具、工作区文件和人工交互卡片，所有动作仍由服务端校验权限、会话和工作区范围。

## 架构

```text
浏览器（Vue 3 + Naive UI）
  ├── REST /api/* ───────────────────────────────────┐
  └── WebSocket /ws/agent/v2?ticket=... ─────────────┤   （web 容器 Nginx 同源反代；HTTPS 入口 8443）
                                                       ▼
FastAPI API / AgentLoop Host
  ├── 认证、协议档、用例与评审、需求基线、资产、通知、工作区、审计
  ├── WebSocket 事件持久化、断线补发、受控工具与交互卡片
  └── AgentLoop：专家技能、模型调用、工具编排与会话状态
            │                     │                      │
            │                     ├── Runner 沙箱（bash 唯一执行通道）
            │                     └── media-mcp / LightRAG（Compose 内网）
            ▼
PostgreSQL + pgvector  ◄──── Redis（短期状态、短票与审批共享）
            │
            ▼
Worker 任务队列（SELECT … FOR UPDATE SKIP LOCKED）
  └── testcase：按需求分节分批生成用例 → 草稿 → 人工确认（72h 超时扫描）
```

| 层级 | 主要组件 | 职责 |
| --- | --- | --- |
| 前端工作台 | Vue 3、TypeScript、Naive UI、Pinia | 智能体对话、用例工作台、评审与资产、能力中心、管理后台 |
| API 与 Agent | FastAPI、WebSocket、AgentLoop | 短请求、权限、会话、流式事件、专家技能、工具与人工交互 |
| 异步执行 | Worker | 领取用例生成任务、分批调用模型、写入草稿与通知 |
| 隔离执行 | Runner | 只读 rootfs + 命名空间隔离的 bash 沙箱，内部令牌鉴权、fail-closed |
| 数据与状态 | PostgreSQL、pgvector、Redis | 业务数据、事件回放、任务状态、向量能力与短期状态 |
| 运行与部署 | Docker Compose、GitHub Actions、GHCR | 服务编排、按改动构建镜像、滚动部署与服务器备用巡检 |

## 业务流程

```text
需求文档 / 对话描述
        │
        ▼
创建用例生成任务 ──► queued ──► Worker 分节分批生成 ──► 候选用例（草稿 generated）
                                     │                           │
                                     ├── 进度事件实时推送与断线回放  ▼
                                     └── 失败/完成写站内通知     人工评审（AI 评审辅助、评论、版本快照）
                                                                 │
                                                                 ▼
                                                    确认入库 confirmed ──► 用例资产库
                                                                 │
                                                                 ▼
                                          需求基线覆盖率 / 变更影响分析 / 用例质量看板
```

在 AgentLoop 中，用户先选择专家与模型，再通过对话使用已授权的技能和工具。需要补充信息、确认任务或批准高风险操作时，系统展示交互卡片；确认后的动作仍由服务端校验。长耗时任务不会阻塞 WebSocket 收包循环。

## 功能

| 模块 | 功能概览 |
| --- | --- |
| 智能体 | 会话管理、流式回复、专家技能、专家协作、提示词查看编辑、受控工具、人工问答与审批卡片、历史轨迹 |
| 用例工作台 | 需求分节分批生成、草稿编辑、确认入库、导入导出、用例集软删除 |
| 用例评审与版本 | 评审请求与结论、评论、AI 四维评审、版本快照 / diff / 回滚为新草稿 |
| 需求覆盖 | 需求基线与编号抽取、用例关联与覆盖率、基线版本链与变更影响分析 |
| 用例资产与质量 | 确认用例物化为资产、跨集合检索与标签、文本查重；采纳率 / 成功率 / AI 评分看板 |
| 能力中心 | Agent / Skills / Scripts / Rules / RAG 资源与资源广场，MCP 工具只读中心 |
| 模型管理 | 平台模型（管理端维护）与个人模型（仅属主可用），连通性与思考档位探测；API Key 只写不回显 |
| 工作区 | 本地工作区与远程 SSH 工作区（只读浏览、两阶段审批的远程命令）；会话绑定与文件预览 |
| 协作与治理 | 站内通知、Token 用量中心、全局搜索（Cmd/Ctrl+K）、管理后台概览 / 审计日志 / 资源治理 |
| 历史数据（只读） | 历史评测任务、报告、数据集与知识库（含知识图谱视图）的查询 |

## 项目亮点

- **人工把关的生成闭环**：AI 只产出草稿，确认入库必须人工完成；评审状态、版本快照与审计贯穿全程。
- **需求可追溯**：需求基线、覆盖率与变更影响分析把「需求改了哪些用例要动」变成可查询的事实。
- **可控的 Agent 协作**：专家技能和提示词可管理，工具权限、工作区范围和人工确认由服务端统一校验；bash 只经 Runner 沙箱执行。
- **可恢复的实时体验**：WebSocket 事件持久化，断线后按事件游标补发；流式文本与持久业务事件分层处理。
- **按实际改动部署**：部署计划读取 Dockerfile 输入并自动发现 MCP 工具服务，只构建相关镜像；迁移链单 head 守卫在 CI 与部署前双重把关。
- **安全默认**：浏览器不接触模型密钥或宿主命令；敏感配置加密存储；生产环境（`APP_ENV=production`）检测到默认签名密钥或弱引导口令时拒绝启动。

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Naive UI、Pinia
- API：Python 3.12、FastAPI、SQLAlchemy、Alembic、WebSocket
- Agent：AgentLoop、模型协议适配层、受控工具与 MCP 服务
- 数据与任务：PostgreSQL 16、pgvector、Redis、异步 Worker
- 运行与隔离：Runner 沙箱、LightRAG（知识库检索）、Docker Compose
- 工程化：GitHub Actions、GHCR、按差异构建与服务器备用自动部署

## 目录结构

```text
.
├── frontend/                 Vue 前端工作台
├── backend/
│   ├── api/                  FastAPI、REST、WebSocket、AgentLoop 与认证
│   ├── worker/               用例生成任务执行器（停用评测执行器仅保留历史代码）
│   ├── runner/               受控 bash 沙箱执行服务
│   ├── shared/               API 与 Worker 共用模型、事件与公共能力
│   ├── media_mcp/            媒体生成 MCP 工具服务（Compose 内网）
│   ├── lightrag/             知识库检索引擎适配服务
│   └── stress/               压测服务（已下线，仅保留代码）
├── deploy/                   初始化、增量部署、备用巡检与部署测试
├── tools/                    迁移链守卫、Agent 评测与联调工具
├── docs/                     PRD、API 契约、架构设计与实施记录
├── Web-Prototype/            原型参考
├── .github/workflows/        CI 与 main 分支部署工作流
└── docker-compose.yml        本地与生产服务编排
```

## 本地启动

前置条件：Docker 与 Docker Compose，或分别安装 Python 3.12+、Node.js 20+ 和 PostgreSQL。

```bash
# 复制并填写本地环境变量（至少修改 SECRET_KEY 与 BOOTSTRAP_ADMIN_PASSWORD）
cp .env.example .env

# 启动完整服务栈
docker compose up -d --build
```

> Compose 默认 `APP_ENV=production`：`SECRET_KEY` 仍为示例值或短于 32 位、或首次部署的引导管理员口令为 `admin123` 等弱口令时，API 会拒绝启动并在日志中给出检查项编码。仅本地体验时可在 `.env` 中设 `APP_ENV=development`（只告警不阻止）。

启动后可访问：

- 前端：`http://localhost`
- 健康检查：`http://localhost:8000/api/health`（存活探针，无 IO）
- 就绪检查：`http://localhost:8000/api/ready`（校验数据库，供编排层使用）
- API 文档：`http://localhost:8000/docs`

> API 端口默认只绑定回环地址（`API_BIND_HOST=127.0.0.1`），远程机器请用 SSH 隧道
> （`ssh -L 8000:127.0.0.1:8000 <host>`）或显式设置 `API_BIND_HOST=0.0.0.0`；
> 浏览器侧统一走 web 反代（`http://<host>` / `https://<host>:8443`）。
> 全站只走 HTTPS 时请设 `COOKIE_SECURE=true`，使登录 Cookie 只经加密连接传输。

首次启动会根据环境变量创建引导管理员。生产环境必须自行设置强密码与密钥，禁止使用示例值；`deploy/server-setup.sh` 初始化服务器时会随机生成这些值。

### 常用本地开发命令

```bash
# 前端热更新
cd frontend
npm install
npm run dev

# API 检查
cd backend/api
ruff check . ../shared
pytest

# Worker 检查（Windows PowerShell 用 $env:PYTHONPATH = ".;.."）
cd ../worker
PYTHONPATH=.:.. pytest

# 前端检查
cd ../../frontend
npm run lint
npm run typecheck
npm test
npm run build
```

## 部署说明

生产环境使用 Docker Compose。代码推送到 `main` 后，CI/CD 会按路径和 Dockerfile 输入决定是否构建、构建哪些镜像；纯说明文档提交会跳过构建与部署。

当 GitHub Actions 不可用时，服务器可以使用备用巡检在本地增量构建。详细配置、密钥要求、回滚和故障排查见 [备用自动部署方案](docs/AI测试与评估平台-备用自动部署方案.md) 与 [AGENTS.md](AGENTS.md)。

```bash
# 服务器上手动执行一次备用部署
cd /opt/ai-eval-platform
bash deploy/auto-deploy-watch.sh --force
```

## 文档索引

- [产品需求文档（PRD）](docs/AI测试与评估平台-PRD.md)
- [接口契约（API）](docs/AI测试与评估平台-API.md)
- [Agent 开发文档](docs/AI测试与评估平台-Agent开发文档.md)
- [AgentLoop 后端架构设计](docs/AI测试与评估平台-AgentLoop后端架构设计.md)
- [AgentLoop 前端重写与联调计划](docs/AI测试与评估平台-AgentLoop前端重写与联调计划.md)
- [LightRAG 接入技术方案](docs/AI测试与评估平台-LightRAG接入技术方案.md)
- [备用自动部署方案](docs/AI测试与评估平台-备用自动部署方案.md)
- [代码质量报告](docs/AI测试与评估平台-代码质量报告.md)
- [开发计划](https://github.com/Rue1218/ai-eval-platform/blob/45a7f49260c37b986d19c3b880e5d2d9cf1a1692/docs/AI%E6%B5%8B%E8%AF%95%E4%B8%8E%E8%AF%84%E4%BC%B0%E5%B9%B3%E5%8F%B0-%E5%BC%80%E5%8F%91%E8%AE%A1%E5%88%92.md)

## 贡献约定

提交前请遵循 [AGENTS.md](AGENTS.md) 中的分支、测试、提交信息、迁移和安全规范。数据库结构变更必须由 Alembic 迁移管理；新增 API 或 WebSocket 字段必须先同步 API 文档；禁止在日志、接口响应或提交中暴露密码、密钥、Cookie、令牌或上游原始异常。
