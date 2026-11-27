# AI 测试与评估平台 — 代码质量报告

> 版本：V1.1 ｜ 审查日期：2026-11-27 ｜ 审查基线：`main@0884772`（工作区无未提交改动）
> V1.1：P0 安全项与 README 已在分支 `fix/security-p0-hardening` 修复，见第 8 节。
> 审查方式：静态阅读 + 本地可执行门禁。范围包括 `backend/`、`frontend/`、`deploy/`、`.github/workflows/`、`docker-compose.yml` 和文档。

---

## 1. 总体结论

| 维度 | 评分（5 分制） | 一句话结论 |
| --- | :---: | --- |
| 架构与分层 | 4.0 | API、Worker、Runner、LightRAG 职责清晰；沙箱隔离做得到位；新旧两套 WS/Agent 栈并存，负担较重 |
| 代码可维护性 | 2.5 | 上帝文件多，前后端各有多个文件超过 1500 行；超长闭包函数；停用功能和死代码体量大 |
| 安全 | 3.0 | 异常不外泄、Runner 鉴权 fail-closed、路径防穿越都做到了；默认凭据没有启动校验，Cookie 和 nginx 安全头缺失 |
| 可靠性与并发 | 3.0 | 任务领取用 `SKIP LOCKED`，WS 事件持久化后可补发；但 async 函数里有同步 DB/行锁，进程内状态较多 |
| 测试 | 3.5 | 后端用例超过 2500 条，前端单测 168 条、e2e 27 个 spec；缺组件测试和覆盖率统计，部分子服务测试没进 CI |
| 工程化与 CI/CD | 4.0 | 增量部署、迁移单 head 守卫、PR 分流都已具备；Python 版本不统一，lint 只开了基础规则 |
| 文档 | 3.0 | 契约文档齐全，但体积过大（API.md 约 432KB）；README 与当前产品边界不一致 |

**综合：3.3 / 5。** 功能交付和工程纪律都比较扎实。主要短板是**安全默认值**、**大文件/历史包袱**、**多副本一致性**三类。建议先按第 6 节的 P0 清单处理。

---

## 2. 项目规模概览

| 项 | 数据 |
| --- | --- |
| 后端 Python 文件 | 约 560 个（`api` 486 / `worker` 39 / `shared` 17 / `runner` 5 / `lightrag` 8） |
| 数据表 / 迁移 | 61 张表（`shared/models.py`）/ 46 个 Alembic 迁移，单 head `c4d8e2a1f6b3` |
| 前端源码 | `src/` 下 153 个 `.vue/.ts`（views 25、components 79、stores 3、api 9） |
| 测试 | api 约 196 个测试文件；worker 17 个 / 80 例；runner 35 例；lightrag 46 例；media_mcp 5 例；前端单测 22 个文件 / 168 例，e2e 27 个 spec |
| 文档 | `docs/` 下 45 篇 Markdown；`AGENTS.md` 约 75KB |
| 提交数 | 1137 |

---

## 3. 本地门禁执行结果

| 检查项 | 结果 | 备注 |
| --- | --- | --- |
| 前端 `npm run lint` | 通过（0 error / **238 warning**） | warning 基本都是 `no-explicit-any` |
| 前端 `npm run typecheck` | 通过 | `strict: true` |
| 前端 `npm test` | **168 / 168 通过** | Node 原生 `node --test` |
| 迁移链守卫 `tools/check_migration_heads.py` | 通过 | 46 个迁移，唯一 head |
| 部署单测 `deploy/tests` | **39 / 39 通过** | — |
| Shell 语法 `bash -n deploy/*.sh` | 6 / 6 通过 | — |
| 后端 `ruff` / `pytest` | **未执行** | 本机是 Python 3.11，没有安装 ruff/pytest；项目要求 3.12+。AGENTS.md 记录的最近门禁为 api 2547 passed / 97 skipped |

---

## 4. 做得好的地方

1. **异常契约执行到位**：没有裸 `except:`；全局 500 处理器不回显详情（`api/app/errors.py:118-125`）；没发现 traceback 或 SQL 返回给浏览器。
2. **沙箱边界清晰**：bash 统一经 Runner 执行，Runner 不可达时直接拒绝（`harness/execution/sandbox.py:126-128`）；Runner 未配置令牌时 fail-closed，令牌用 `compare_digest` 校验（`runner/main.py:319-324`）；Runner 只读 rootfs，网络与 postgres/redis 结构性隔离（`docker-compose.yml:186-234, 358-363`）。
3. **没有 SQL 注入面**：应用代码里没有 `text(f"...")` 拼接，也没有 `shell=True` / `os.system`。
4. **本地文件路径防穿越**：realpath 加前缀逐段校验（`dispatch.py:115-141`），上传文件只取 basename（`files.py:53`）。
5. **前端工程化**：TS strict；路由全部懒加载；manualChunks 分包；定时器和监听器都成对清理；生产环境默认关闭 Mock（`http.ts:116`）；用 Cookie 会话，本地不存 token。
6. **部署链路成熟**：按 Dockerfile 输入增量构建（`deploy/plan_services.py`）；迁移单 head 守卫同时接入 CI、部署 preflight 和单测；有备用巡检和部署互斥锁。

---

## 5. 问题清单

严重程度：**高**（安全或数据风险，应尽快修）、**中**（影响稳定性或可维护性）、**低**（规范和体验）。

### 5.1 安全

| # | 严重 | 问题 | 证据 | 建议 |
| --- | :---: | --- | --- | --- |
| S1 | 高 | 默认密钥和口令启动时**不做校验**：`SECRET_KEY=dev-secret-change-me`、`admin123`、`aieval_pass`、`dev-lightrag-internal`；引导管理员 `must_change_password=False` | `api/app/config.py:9-13`；`main.py:67-90`；`docker-compose.yml:13,52,54,108`；`deploy/server-setup.sh:107`；`.env.example:21` | 在 lifespan 里加生产启动守卫：检测到默认值或空 KEK 时拒绝启动（可用 `APP_ENV=dev` 豁免）；`server-setup.sh` 改为随机生成管理员口令；引导管理员首次登录强制改密，或至少在 UI 上告警 |
| S2 | 高 | `KEY_ENCRYPTION_KEY` 默认为空时，Fernet 密钥由 `secret_key.ljust(32)` 派生，不是正规 KDF；再叠加 S1，协议档密文实际等于用公开默认值加密 | `api/app/security.py:63-69`；`worker/app/crypto.py:20` | 生产环境强制要求 KEK；派生改用 HKDF/PBKDF2；api 与 worker 的加解密收敛到 `shared` 共用一份 |
| S3 | 高 | 生产 Cookie 默认**不带 Secure**，compose 也没有覆盖 | `config.py:38`；`routers/auth.py:97-104` | compose 注入 `COOKIE_SECURE`，HTTPS 入口下置 true；`.env.example` 补上该项与 `CORS_ORIGINS` |
| S4 | 高 | 前端 SSH 密码只做 base64 就存进 sessionStorage，并随每个工作区请求带上 | `UserWorkspaces.vue:891`；`http.ts:156-165` | 改为服务端短期会话令牌（TTL，只存内存或 Redis），前端只持有不透明 token；至少改成只放在内存变量里，不落 Storage |
| S5 | 中 | nginx **没有任何安全响应头**（CSP、X-Frame-Options、X-Content-Type-Options、Referrer-Policy、HSTS），也没有 `server_tokens off` | `frontend/nginx.conf:22-78`；`deploy/https/nginx.conf` | 补齐安全头；HTTPS 入口加 HSTS；CSP 先用 Report-Only 模式观察 |
| S6 | 中 | 渲染 Markdown 和高亮靠手写转义，**没用 DOMPurify**，ESLint 也关闭了 `vue/no-v-html`；`escapeHtml` 有 3 份实现；Dispatch 页插值未转义 | `MarkdownView.vue:15,225-243`；`eslint.config.js:47-48`；`Dispatch.vue:854,883,1109`；`utils/render.ts:35` | `renderedHtml` 输出前过一遍 DOMPurify；统一用 `utils/render.ts` 的 `escapeHtml`；恢复 lint 规则，对白名单处逐行 disable |
| S7 | 中 | SSH 远程工作区边界弱：known_hosts 缺失时退回 `AutoAddPolicy`；主机白名单默认不限制（可被用来探测内网）；远端路径只做 normpath，`root="/"` 时不受限 | `remote_workspace.py:140-146,228-239`；`config.py:98-104`；`docker-compose.yml:60` | 生产强制配置 known_hosts 和主机白名单；禁止 `remote_root="/"`；远端路径用 `realpath` 校验 |
| S8 | 中 | 反代后取不到真实客户端 IP：`request.client.host` 恒为网关地址，登录限流和审计 IP 都失真 | `routers/_common.py:19-21`；`api/entrypoint.sh:98` | uvicorn 加 `--proxy-headers --forwarded-allow-ips=<web 网段>` |
| S9 | 低 | `AGENTS.md` 写明了生产公网 IP、SSH 用户 root 和默认管理员口令 | `AGENTS.md:106-114,325-328` | 敏感运维信息移到私有运维文档；仓库里只保留占位符 |
| S10 | 低 | 没有 CSRF token 或 Origin 校验，只靠 `SameSite=lax` | `main.py:235-241` | 对写操作加 Origin/Referer 校验，或用双提交 Cookie |
| S11 | 低 | LightRAG 的 `fastapi==0.115.6` 会连带 starlette<0.42，正好落在 api 依赖注释里点名要避开的漏洞区间 | `backend/lightrag/requirements.txt`；`api/requirements.txt:1-2` | 升级 LightRAG 服务的 fastapi/starlette，或在 `constraints.txt` 里钉住安全版本 |

### 5.2 可靠性与并发

| # | 严重 | 问题 | 证据 | 建议 |
| --- | :---: | --- | --- | --- |
| R1 | 高 | async 函数里直接执行同步 DB 操作，包括 `SELECT ... FOR UPDATE` 和 commit；等行锁时会**阻塞整个事件循环** | `routers/ws.py:405,502,686,845-899,1454-1535`；`agent/ws_connection.py:25`；`files.py:77-120`；`sessions.py:660-704` | 改成 `asyncio.to_thread`/`run_in_threadpool` 包裹（`kb.py` 已有范例），或把这些路由改为同步 `def` 交给线程池 |
| R2 | 中 | 进程内全局状态多，多副本下语义失效：登录限流、WS 短票回退、远程命令审批单、回合互斥 / abort、默认内存 Checkpointer | `auth.py:35`；`ws_tickets.py:17`；`workspace_exec_approval.py:46-47`；`ws.py:107-135`；`checkpoint.py:558`；compose `AGENT_CHECKPOINTER=memory` | 登录限流和审批统一放 Redis；推进 `AGENT_CHECKPOINTER=postgres` 切换（AGENTS.md 已列为 H5 未完成项）；在文档里明确“当前只支持单副本” |
| R3 | 中 | 每次建立 WS 连接都**新建一个 Redis 连接池**，同步调用，Redis 故障时每次阻塞约 0.8s | `ws_tickets.py:52-71` | 用模块级单例连接池，改为异步客户端 |
| R4 | 中 | 附件鉴权每次都遍历所有可见会话的消息附件，是 O(N) 全表扫描 | `routers/files.py:158-172` | 给附件建索引表或 `file_id → session_id` 映射 |
| R5 | 低 | 5 处 `except Exception: pass` 没有任何日志 | `session_connections.py:177`；`profile_probe.py:95`；`profile_tool_probe.py:60`；`profile_check.py:39`；`agent/graph.py:378` | 至少记一条 debug 日志和异常类型名 |
| R6 | 低 | 部分接口把 `str(exc)` 直接透传给前端；按中文子串区分 400/502 | `lightrag/app.py:167-228`；`user_workspaces.py:151-162`；`media_mcp/app/server.py:84-118` | 统一改成 `{code,message}` 固定文案；用异常子类区分错误类型 |

### 5.3 可维护性

| # | 严重 | 问题 | 证据 | 建议 |
| --- | :---: | --- | --- | --- |
| M1 | 中 | 后端上帝文件：`ws.py` 1547 行、`models.py` 约 1529 行（61 张表）、`cases.py` 1288 行、`dispatch.py` 1142 行；`agent/` 下约 103 处 `ws_router.X` 反向引用（为了保留测试打桩点） | `agent/ws_connection.py:20-23` | `models.py` 按领域拆包后在 `__init__` 中 re-export；`cases.py` 拆成 CRUD、AI、导入导出三块；测试改为依赖注入，消除反向引用 |
| M2 | 中 | 超长函数：`build_agent` 约 690 行，其中内嵌的 `call_model` 约 448 行；`_build_dependencies` 约 354 行；`make_orchestrator_node` 约 332 行 | `agent/loop.py:259-774`；`loop_wiring.py:276-630`；`taor_nodes.py:215-547` | 把闭包拆成类或独立函数，逐段补单测 |
| M3 | 中 | 前端上帝组件：`UserWorkspaces.vue` 2694 行、`Cases.vue` 2678 行（82 个函数）、`Datasets.vue` 2304 行、`AgentWorkspace.vue` 1784 行；`http.ts` 2201 行，含 153 处 Mock 分支 | — | 按功能抽 composable 和子组件；`http.ts` 按领域拆模块，Mock 改用 MSW 或按需动态 import |
| M4 | 中 | 停用功能残留：worker 中的 benchmark/rag/stress 执行器约 2068 行仍在分派；旧版 LangGraph WS 栈超过 5000 行；`backend/stress` Go 服务；worker 测试中约 42% 测的是停用功能 | `worker/app/main.py:16,27-28,110-138` | 归档到 `legacy/` 或单独的历史分支；worker 只保留 testcase；制定旧会话迁移到 v2 后下线旧 WS 栈的计划 |
| M5 | 中 | 前端死代码：`components/workflow/` 整个目录约 3.8k 行没有被引用；`ShareModal.vue`、`ErrorStrip.vue` 也没有被引用；vite 里配置了 katex 分包，但源码并没有 import katex | `WorkflowDesigner.vue` 等；`vite.config.js:68` | 直接删除；启用 `knip`/`ts-prune` 之类的未使用代码检测 |
| M6 | 中 | Mock 数据和仿真引擎打进生产包：`mockData.ts` 951 行被静态 import，并在模块顶层初始化 | `http.ts:97-112,225`；`Dispatch.vue:937-1019` | 改为 `if (import.meta.env.DEV) await import('./mockData')` |
| M7 | 低 | 重复实现：`formatTime/formatBytes` 至少 12 份、`highlightMatch` 2 份、树宽拖拽逻辑 2 份；Fernet 解密前后端各一份；`profile_env` 三份 | 见前端 `utils/format.ts:40-90` | 统一收敛到 utils 或 shared |
| M8 | 低 | 类型债：前端约 194 处显式 `any`（lint 只告警）；后端 54 处 `# type: ignore`；约 76 处 `noqa` 引用了 ruff 没启用的规则 | `eslint.config.js:43-44`；`api/pyproject.toml:21-23` | `catch (err: any)` 改成 `unknown` 加类型守卫；按目录逐步把 `no-explicit-any` 升级为 error |
| M9 | 低 | 死代码：`sandbox.probe_sandbox` 没有调用方，而且请求不带鉴权头，必然失败；`sandbox_bash_default_mode` 已废弃；Login 页“记住我”复选框不起作用 | `sandbox.py:173-195`；`config.py:67-69`；`Login.vue:444` | 删除，或补上实现 |

### 5.4 测试

| # | 严重 | 问题 | 建议 |
| --- | :---: | --- | --- |
| T1 | 中 | 前端**组件测试为零**，也没有覆盖率工具；`http.ts`、`MarkdownView.vue`（XSS 防线）、stores、`ModelCompare.vue`、`MyModels.vue` 都没有测试 | 引入 Vitest + @vue/test-utils；优先给 `MarkdownView` 补 XSS 用例，给 `http.ts` 的拦截器补测试 |
| T2 | 中 | 27 个 e2e spec 全部 `page.route` 模拟后端，没有任何真实联调冒烟测试 | 增加 1 到 3 条基于 docker compose 的真实端到端冒烟测试（登录 → 建会话 → 生成用例） |
| T3 | 中 | `lightrag`、`media_mcp` 的测试**没进 CI**；`runner`、`worker` 作业只在 push main 时运行，PR 阶段不跑 | `ci.yml` 补这两个作业，并按 `classify_changes.py` 的分流规则在 PR 阶段触发 |
| T4 | 中 | 核心模块缺测试：`requirement_change_service.py`（268 行）、`worker/app/case_ai.py`（297 行）、`dataset_catalog.py`（928 行）、`adapters.py` | 补单测；引入 `pytest-cov` 并在 CI 输出覆盖率 |
| T5 | 低 | 沙箱集成测试在 unshare 不可用时会静默 skip；e2e 有 4 处 `waitForTimeout` 硬等待 | CI 里断言 unshare 可用；把硬等待改为等待具体条件 |

### 5.5 工程化与依赖

| # | 严重 | 问题 | 证据 | 建议 |
| --- | :---: | --- | --- | --- |
| E1 | 中 | Python 版本混用：api/runner 用 3.12，**worker 镜像用 3.13 而 CI 用 3.12 测**，lightrag 用 3.11；没有 `requires-python` | `worker/Dockerfile:1`；`lightrag/Dockerfile:1`；`ci.yml:207` | 统一到 3.12；各服务的 pyproject 声明 `requires-python` |
| E2 | 中 | ruff 只开了 `E,F,I,UP`，只检查 api 和 shared；worker、lightrag、media_mcp 没有 lint；没有 mypy | `api/pyproject.toml:21-23`；`ci.yml:125` | 根目录建统一的 ruff 配置，逐步启用 `B`、`S`、`BLE`、`ASYNC`（ASYNC 正好能查出 R1）；CI 覆盖全部 Python 服务 |
| E3 | 低 | Python 依赖只锁直接依赖，没有传递依赖锁和哈希；CI 里的 `pip install pytest` 没锁版本 | `ci.yml:163,211` | 引入 `uv`/`pip-tools` 生成锁文件 |
| E4 | 低 | 前端没有 Prettier、`.editorconfig`、`.nvmrc`；CI 用 Node 20，Dockerfile 用 node:22，版本不一致 | `ci.yml:235`；`frontend/Dockerfile` | 统一 Node 版本并加 `.nvmrc` |
| E5 | 低 | 前端 Dockerfile 没有 `HEALTHCHECK`；`https` 服务镜像没有锁到小版本 | `docker-compose.yml:295` | 补健康检查；镜像锁到 `nginx:1.27.x-alpine` |
| E6 | 低 | 迁移问题：`01b89a06eb4b` 在迁移里 import 应用代码并改写宿主机 `.env`；`d9f4a6c2e801` 在事务性 DDL 里吞异常；有 5 个修订号是手工编造的（如 `a1b2c3d4e5f6`） | `migrations/versions/` | 今后禁止迁移产生文件副作用；修订号一律由 Alembic 自动生成 |

### 5.6 文档与仓库卫生

| # | 严重 | 问题 | 建议 |
| --- | :---: | --- | --- |
| D1 | 中 | **README 与当前产品边界冲突**：README 把基准评测、RAG 评测、共享压测写成核心功能和亮点，而 PRD 和 AGENTS.md 已声明 2026-09-28 起这些功能全部停用、产品转向测试用例生成 Agent；README 里的 WS 路径还是 `/ws/agent?ticket`，实际已改为 `/ws/agent/v2`；目录结构缺 `media_mcp`、`tools` | 按当前定位重写 README 的“功能/亮点/架构”三节 |
| D2 | 中 | 文档体积失控：`API.md` 约 432KB，`PRD.md` 约 146KB；`AGENTS.md` 头部堆了 50 多条版本变更记录（约 75KB），AI Agent 和新人都难以快速获取有效规范 | 版本历史移到 `CHANGELOG.md`；AGENTS.md 只保留当前规范；API.md 按模块拆分，或由 OpenAPI 自动生成 |
| D3 | 低 | AGENTS.md 内部有自相矛盾的描述，例如 §1.2 写“Python Worker 执行三协议评测 / LightRAG / 派生压测”，§2 写“全栈六件套”，与当前服务拓扑不符；版本号 V2.49 重复出现两次 | 一次性校对 |
| D4 | 低 | 仓库根目录有临时文件入库：`.git-pr-body.txt`、`design-qa.md` | 删除或移入 `docs/` |
| D5 | 低 | README 的本地命令混用 PowerShell 写法（`$env:PYTHONPATH`），与 AGENTS.md 的 Bash 写法不一致 | 统一给出 Bash 和 PowerShell 两种写法 |

---

## 6. 改进路线建议

### P0（建议 1 周内）
1. **S1/S2**：生产启动守卫（默认密钥、口令、空 KEK 时拒绝启动）+ `server-setup.sh` 随机生成管理员口令。
2. **S3/S5**：`COOKIE_SECURE` 接入 compose；nginx 补安全响应头。
3. **S4**：SSH 密码不再落 sessionStorage。
4. **S8**：uvicorn 开启 `--proxy-headers`，修正限流和审计 IP。
5. **D1**：README 对齐当前产品边界。

### P1（建议 2 到 4 周）
1. **R1**：消除 async 路由里的同步 DB/行锁；ruff 启用 `ASYNC` 规则做持续防护。
2. **S6**：MarkdownView 接入 DOMPurify，补 XSS 单测。
3. **T3/E1/E2**：lightrag、media_mcp 测试纳入 CI；统一 Python 3.12；ruff 规则扩展到全部服务。
4. **M5/M6**：删除前端死代码；Mock 改为按需加载。
5. **R2/R3**：登录限流和审批单迁到 Redis；Redis 连接池改单例。

### P2（持续治理）
1. **M1–M4**：拆分上帝文件和超长函数；归档 benchmark/rag/stress 与旧 WS 栈。
2. **T1/T2/T4**：引入 Vitest 组件测试和覆盖率；补真实联调冒烟测试；给核心模块补测试。
3. **D2**：精简 AGENTS.md，拆分 API.md。
4. **M7/M8**：收敛重复工具函数；按目录清理 `any`。

---

## 7. 附：审查限制

- 后端 `ruff`/`pytest` 因本机 Python 3.11 且没有安装依赖而未执行，相关结论来自静态分析和 AGENTS.md 记录的门禁数据。
- 行号以基线提交 `0884772` 为准，后续改动可能导致偏移。
- 本报告不涉及运行时性能压测和渗透测试。

---

## 8. 修复记录（V1.1，分支 `fix/security-p0-hardening`）

### 8.1 处理状态

| 编号 | 状态 | 处理方式 |
| --- | --- | --- |
| S1 | 已修复 | 新增启动安全守卫：`APP_ENV=production`（Compose 默认）时，默认或短于 32 位的 `SECRET_KEY`、全新部署的弱引导口令直接阻止启动；存量管理员仍用默认口令时只告警。`server-setup.sh` 改为随机生成引导口令 |
| S2 | 部分处理 | KEK 为空时启动告警。派生算法**未改**：存量协议档密文由当前派生密钥加密，改算法前需要先有一套重新加密的迁移方案 |
| S3 | 部分处理 | `COOKIE_SECURE` 接入 Compose（此前宿主 `.env` 中的值根本传不进容器），生产未开启时启动告警。默认仍为 false：生产同时保留 HTTP(80) 入口，强制 Secure 会导致 HTTP 下无法登录 |
| S4 | 已修复 | SSH 密码改存页面内存（`utils/sshPasswordVault.ts`），不再写入 sessionStorage；登出时清空；升级时清理旧残留 |
| S5 | 已修复 | web Nginx 新增安全响应头片段与 `server_tokens off`；HTTPS 入口同样关闭版本号。未加 HSTS（生产保留 HTTP 入口，443 被占用） |
| S8 | 已修复 | 配置 `FORWARDED_ALLOW_IPS`（默认本机加私有网段），uvicorn 显式开启 `--proxy-headers`；`API_BIND_HOST` 真正接入端口映射 |
| D1 | 已修复 | README 按当前产品边界重写（定位为用例生成 Agent；评测、压测已停用；WS 路径改为 `/ws/agent/v2`；目录结构补齐） |

### 8.2 行为变化提示

- **API 端口默认只绑 127.0.0.1**：README 和 `.env.example` 早已这样描述，但 Compose 此前从未使用 `API_BIND_HOST`，实际绑定的是 0.0.0.0。需要从其它机器直连 `:8000` 或 Swagger 的环境，请在 `.env` 中显式设置 `API_BIND_HOST=0.0.0.0`。
- **生产启动守卫**：全新部署时如果 `.env` 中仍为示例 `SECRET_KEY` 或弱引导口令，API 会拒绝启动，日志会给出检查项编码（如 `SECRET_KEY_WEAK`）。仅本地体验时可设 `APP_ENV=development`。
- **SSH 密码**：刷新页面后需要重新输入。

### 8.3 修改代码文件与作用清单

| 文件 | 作用 |
| --- | --- |
| `backend/api/app/startup_security.py`（新） | 启动安全守卫：致命项与告警项的分级判定，日志不回显密钥 |
| `backend/api/app/config.py` | 新增 `app_env` 配置 |
| `backend/api/app/main.py` | lifespan 最先执行配置检查；创建引导管理员前检查口令 |
| `backend/api/tests/test_startup_security.py`（新） | 守卫判定与 lifespan 接线，共 27 项用例 |
| `backend/api/entrypoint.sh` | uvicorn 显式 `--proxy-headers` |
| `docker-compose.yml` | 注入 `APP_ENV`、`COOKIE_SECURE`、`FORWARDED_ALLOW_IPS`；端口映射使用 `API_BIND_HOST` |
| `.env.example` | 补充上述变量说明，引导口令示例改为占位值 |
| `deploy/server-setup.sh` | 随机生成引导口令，写入 `APP_ENV=production` 与 `COOKIE_SECURE` |
| `frontend/security-headers.conf`（新）、`frontend/nginx.conf`、`frontend/Dockerfile` | 安全响应头片段，并在 server 与带 `add_header` 的 location 中引入 |
| `deploy/https/nginx.conf` | `server_tokens off` |
| `frontend/src/utils/sshPasswordVault.ts`（新） | SSH 密码页面内存保管、请求头编码、旧残留清理 |
| `frontend/src/api/http.ts`、`frontend/src/views/UserWorkspaces.vue` | 改用内存保管；登出时清空 |
| `frontend/tests/sshPasswordVault.test.mjs`（新）、`frontend/tests/e2e/workspaceSshPassword.spec.ts` | 单测 5 项；e2e 覆盖不写存储、刷新失效、旧残留清理 |
| `README.md`、`AGENTS.md` | 产品边界对齐；版本 V2.51 登记；初始管理员说明更正 |

### 8.4 门禁结果

- api：`ruff` 通过；`pytest` 2592 passed / 89 skipped（Python 3.12.14）。
- 前端：lint 0 error（238 条既有 warning，没有新增）；typecheck 和 build 通过；单测 173/173；e2e 169/169。
- 部署：单测 39 项；`bash -n` 全部通过；`docker compose config` 通过；迁移链只有一个 head。
- Nginx：用 `nginx:1.27-alpine` 执行 `nginx -t` 通过；`/`、`/assets/*`、`/api/*` 三类响应实测都带上了安全头。
- 代理 IP：用 uvicorn 0.34 中间件验证了单级反代、两级反代、客户端伪造 XFF、公网直连伪造 4 种场景，取到的都是真实客户端 IP。
- 未执行：worker 测试（本批没有改动 worker 代码）。
