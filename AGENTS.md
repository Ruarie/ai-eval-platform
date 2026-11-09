# AI 测试与评估平台 — AI Agent 行为规范与工程指南 (AGENTS.md)

> **最高指示**：本文件是面向所有参与本项目的 **AI Agent 与开发者** 的最高行动指南。在编写或修改代码前，**必须严格遵守本文档所规定的架构边界、开发契约与行为红线**。
> 版本：V2.36 ｜ 审查日期：2026-11-09（N-08 站内通知 MVP：新增 `notifications`（迁移 `b8e4d2f7c1a3`），任务生成完成/失败与评审指派/结论写入通知；`dedupe_key` 按用户唯一，重复写入跳过；新增 `/api/notifications` 列表/未读/已读接口与 `NotificationBell`、`/notifications` 页面；通知不含密钥/上游原文，无邮件/Webhook 外发。门禁：通知 2 项 + 评审/资产/用例/需求/质量/搜索 74 项、Worker 13 项通过，ruff、前端 typecheck/build、单测 123/123。契约见 API V2.57、PRD V1.66。）
>
> 版本：V2.35 ｜ 审查日期：2026-11-09（N-05 用例资产库 MVP：新增 `case_assets`（迁移 `f5c1d8a3b6e2`），确认入库时物化、幂等且不覆盖标签；新增 `/api/case-assets` 检索/概览/详情/标签/文本查重/历史回填；来源集合删除后资产保留，标签最多 10 个；前端新增 `/case-assets` 页面与「用例资产」导航。本期不做语义向量、自动合并或跨集合复制。门禁：资产测试 3 项 + 用例/需求/评审/质量/搜索 76 项通过、ruff、前端 typecheck/build、单测 123/123。契约见 API V2.56、PRD V1.65。）
>
> 版本：V2.34 ｜ 审查日期：2026-11-09（N-04 需求变更分析 MVP：`requirement_baselines` 增量 `parent_id`（迁移 `e2a6b9c4d7f1`）；新增 `POST /api/requirement-baselines/{base_id}/versions`、`GET .../diff`、`GET .../impact`；新版本只能从已确认基线派生，保留父版本，草稿可预览差异但不能绑定；影响分析只读旧基线绑定用例集与关联用例，标注 changed/removed，不自动修改用例；前端在需求覆盖抽屉内提供「需求变更分析」。门禁：需求相关 14 项 + 质量/评审/搜索 29 项通过、ruff、前端 typecheck/build。契约见 API V2.55、PRD V1.64。）
>
> 版本：V2.33 ｜ 审查日期：2026-11-09（N-03 用例质量看板 MVP：新增 `GET /api/metrics/casegen`，按 7/30/90 天聚合运行数、生成/确认、采纳率、成功率、最新 AI 评分、按天/模型/状态/模块分布；Worker 成功任务结果补充 `profile_id/profile_name/model_name` 用于归因；前端新增 `/case-quality` 页面与「用例质量」入口。只读现有事实，缺失模型/评分显示占位，不用 0 冒充。门禁：质量看板 3 项 + 评审 8 项 + 需求/搜索 15 项通过、ruff、前端 typecheck/build。契约见 API V2.54、PRD V1.63。）
>
> 版本：V2.32 ｜ 审查日期：2026-11-09（N-02 用例评审工作流与版本历史 MVP：① 新增 `case_review_requests` / `case_review_comments` / `case_review_runs` / `case_set_versions` 四表与 `case_sets.review_state/review_assignee_id`（迁移 `c1e7f3a9d2b4`）；② `/api/case-sets/{id}/review` 聚合工作台、请求/决策/评论、AI 历史、版本列表/diff/回滚；③ `/ai-review` 改为追加历史，`checks` 保留最新一份兼容；确认入库前自动生成 `reason=confirm` 版本；④ 回滚只新建草稿，不修改当前集合或历史；⑤ 前端新增 `CaseReviewFlowDrawer` 与用例页「评审工作台」入口。门禁：评审测试 8 项与需求/搜索 15 项（合计 23 项）通过、ruff 通过、前端 typecheck/build 通过。契约见 API V2.53、PRD V1.62。）
>
> 版本：V2.31 ｜ 审查日期：2026-11-09（Phase 1 治理与 N-01/N-07 MVP：① 登录页移除模拟 SSO/社交登录，只保留本地账号；② 侧栏改为「工作台 / 资产与历史 / 协作 / 管理」四组，补齐 `/datasets`、`/model-compare`、`/admin/stress` 入口，消除孤立路由；③ 新增需求基线与用例覆盖：`requirement_baselines` / `requirement_items` / `case_requirement_links` 三表与 `case_sets.requirement_baseline_id`（迁移 `a9d4e6f2b8c1`），`shared/requirements.py` 负责编号抽取/相似度/覆盖率，新增 `/api/requirement-baselines`、`/api/case-sets/{id}/coverage`、`.../requirements/auto-link`、`.../requirements/link`；④ 新增 `/api/search` 跨实体只读搜索与前端 Cmd/Ctrl+K 命令面板，私有会话/工作区/记忆按属主过滤。自动关联只返回候选，人工确认才落库，关联不推进用例集 revision。门禁：需求与搜索测试 15 项通过、ruff 通过、前端 typecheck/build 通过。契约见 API V2.52、PRD V1.61。）
>
> 版本：V2.30 ｜ 审查日期：2026-11-09（知识图谱视觉重做：原环形布局在 100 节点/280 边时呈「外圈项链 + 中心蜘蛛网 + 四周大片留白」，标签互相压。改为**类型分簇布局**——每个实体类型一个簇，簇心均匀落在椭圆上（`CLUSTER_RX/RY = 0.7/0.74 × 可用半径`），簇内按黄金角螺旋展开（`13 + 9.2√i`），簇心放度数最高的实体；边按两端较弱的度数衰减透明度（0.05–0.29），选中时只亮一跳邻居（0.62）其余降到 0.035；节点加白色描边、选中加外扩细环；标签只标每簇簇心 + 选中及其邻居，并用白色 `paint-order: stroke` 光晕压住连线；画布改径向渐变 + `aspect-ratio: 840/600` 自适应，去掉上下黑边；右侧未选中时展示「关联度最高的实体」Top6 可点；每个节点带原生 `<title>` tooltip。实测同一份 100 实体/280 关系数据：画面铺满、六色成簇、无标签重叠，点击节点右侧显示类型/关联数/描述/来源文档。）

> 版本：V2.29 ｜ 审查日期：2026-11-06（effort 型思考模板默认档位固定为 high：`newapi-chat-effort-v1` 的 `default_effort` 由 medium 改为 high。原因是 effort 型模板的思考量由上游决定，medium 在长上下文下容易把预算花在思考上（hy4 曾出现 reasoning=8192、正文为空）；high 配合 ≥16K 输出上限更稳。实测 hy4 默认档位=高强度、五档全通过（off/low/medium/high/max），真实对话输出 865 token、无输出上限截断。另对全部 3 个协议档做真实思考探测：deepseek-v4.1-flash（off/low/high/max 全通过，2.3s）、qwen3.8-max-0902（五档全通过，6.4s）、hy4（五档全通过，6.6s），UI 三个模型各发一条真实问题均正常返回、无截断。）

> 版本：V2.28 ｜ 审查日期：2026-11-06（用例 AI 评审：新增 `POST /api/case-sets/{set_id}/ai-review`，对已落库用例集按覆盖度/可执行性/去重/策略分布四维打分并给出问题清单（每条含 type/detail/fix），结果写入 `case_sets.checks`（`kind=ai_review`，保留自检红字，不改动用例内容与状态，confirmed 快照也可评审）。`shared/casegen` 新增 `build_review_prompt` / `parse_review`：分数收敛 0–100、问题上限 20 条、verdict 非法时按分数推断、字段长度截断。前端新增 `CaseReviewDrawer`（分数 + 四维进度 + 问题清单 + 重试）与用例页「AI 评审」入口。实测同一份 66 条用例集可返回结构化评审结果。门禁：casegen 39 passed、route 注册校验通过、前端 typecheck/build 通过。）

> 版本：V2.27 ｜ 审查日期：2026-11-06（用例生成改为按需求分节分批：实测 hy4 在「一次产出 45 条 JSON」时把 max_tokens 全花在思考上、正文 0 字符（单模块 16K 预算同样为空），同一 prompt 换 qwen3.8-max 仅 1121 tokens 就出 8 条。① `shared.casegen.split_sections`：优先按「4.x」功能小节切（不拆 4.3.1 子节），无编号标题退化为任意标题、再退化为按长度切块；段数超上限贪心合并（标题保留两段），单段超 4000 字再切；② worker `run_testcase` 逐批生成：每批 6–10 条、独立预算与截断重试，单批失败不整单失败，全部失败才报错（全为截断时给 BUDGET_EXCEEDED）；③ 进度按批次推送。实测同一 PRD 切 9 段（4.1–4.8，4.8 超长拆两段）。门禁：api 2433 passed/89 skipped、worker 87 passed（1 例既有失败与本批无关）。）

> 版本：V2.26 ｜ 审查日期：2026-11-06（用例生成补齐逐条需求覆盖：评审任务 2f7b889d 的 46 条用例漏掉整个功能域（报告 FR-600、运营 FR-800）。根因是 `shared/casegen.requirement_rules` 只认「1. 」「- 」列表符号，PRD 表格里的 `| FR-xxx |` 行完全没进提示词，上限又只有 12 条。修复：① 新增 FR-/NFR-/BR- 编号行识别（表格行压成「编号 描述 优先级」），上限 12→80（该 PRD 有 62 条编号需求，60 会漏尾部模块）；② 提示词明确 P0 一条用例对一条、条数不足先砍 P1/P2，六类策略都要出现且边界+反向合计 ≥40%，expected 必须含可判定信号；③ 要求输出前逐模块自检补齐。实测同一份 PRD 现在抽出 80 条规则（62 条 FR，含此前漏掉的 FR-801/802/803）。门禁：api 2430 passed/89 skipped、worker 87 passed（1 例既有失败与本批无关）。）

> 版本：V2.25 ｜ 审查日期：2026-11-06（修复推理模型把输出预算全用于思考：hy4 档出现「达到输出上限」且正文为空，事件显示 `reasoning_tokens=8192 / completion_tokens=8192 / content=""`。① `ws.py` 新增 `_output_budget`：effort 型思考模板预算 ≤16K 时翻倍、≥16K 保持原值（上限 131072），budget 型模板不变；② 前端 `max_tokens` 文案补「若正文为空多为思考占满预算」；③ 提示词加单轮最多 4 次工具调用、长文档优先定位片段；④ hy4 协议档 `max_output_tokens` 8192→32768、`context_window` 960000。）

> 版本：V2.24 ｜ 审查日期：2026-11-05（远程工作区目录浏览：新增 `POST /api/workspaces/ssh/browse` —— 创建远程工作区前用尚未落库的临时连接参数列出一层子目录（不列文件），返回 `{path, parent, entries}`；浏览阶段以 `/` 为界不限深度，`remote_root` 由用户点选回填；`auth_type=password` 时密码随请求体传入，只在本次请求内使用（不入库、不写审计、不落日志）。前端创建弹窗「远程根目录」旁加「浏览」：目录列表 + 上级导航 + 「选择当前目录」回填；密码认证提供仅用于浏览的密码输入框。实测：browse `/` 返回 /app、/bin、/config…；browse `/config` 返回 path=/config、parent=/、子目录 .ssh/logs/ssh_host_keys/sshd；无密码 400。门禁：api 2428 passed/89 skipped、e2e 130 passed、前端 lint 0 error + build 通过。）

> 版本：V2.23 ｜ 审查日期：2026-11-05（HTTPS 入口：新增 `https` 服务（公共镜像 `nginx:1.27-alpine` + 宿主 `deploy/gen-selfsigned.sh` 生成自签证书、容器只读挂载；不为几行配置单独发镜像，避免部署机 `--no-build` 时缺镜像），映射 `8443:443` 反代 `web:80`，透传 `Upgrade`/`Connection` 支持 `/ws/agent/v2`，长请求 600s、上传上限 200MB；证书落 `./data/https` 重建不换；`deploy/plan_services.py` 纳入服务列表；`HTTPS_HOST` 写进证书 CN/SAN。生产是内网 IP + 443 被占用，故用自签 + 8443；浏览器首次访问需手动信任，导入 `data/https/server.crt` 可消除告警。曾试 Caddy 内置 CA：容器内绑定宿主 IP 导致监听失败，改 `bind 0.0.0.0` 后 curl/Chrome 仍 TLS `internal error`（仅 openssl 可通），改用 nginx。实测：8443 下 `/api/health` 200、`/login` 200、`/api/kb` 401、浏览器登录跳 `/agent`、发消息建立 `wss://…/ws/agent/v2` 且无报错。）

> 版本：V2.22 ｜ 审查日期：2026-11-05（远程工作区密码认证，密码不落库：`workspaces` 增量 `auth_type`（`key_file` 默认 / `password`，迁移 `b7c3e4f5a6d7`）；password 模式不要求 `ssh_key_name`、创建时跳过连通性探测（尚无密码）；密码经请求头 `X-Workspace-SSH-Password: base64(pwd)` 随请求临时传入，服务端不落库/不写日志/不缓存，缺失 → 400、认证失败 → 502；`remote_workspace` 全部文件操作与 `exec` 透传密码，`_connect` 支持 password；前端创建弹窗加认证方式、工作区页 password 模式显示 🔑/🔓 入口，密码存 `sessionStorage`、axios 拦截器按工作区 ID 附加 header、保存后立即拉目录树。实测：create 201 → 无密码 400 → 错密码 502 → 正确密码 200 列目录 → exec 两阶段 exit=0。门禁：api 2428 passed/89 skipped、e2e 128 passed、前端 lint 0 error + build 通过。）

> 版本：V2.21 ｜ 审查日期：2026-11-05（远程命令两阶段审批：`POST /api/workspaces/{id}/exec` 改为只登记待确认请求（202 + `approval_id` + 预览 host/root/命令/有效期），新增 `confirm`/`reject` 端点；审批单在 `app/workspace_exec_approval.py` 内存保存 300s、容量 200、按 `workspace_id`+`user_id` 双匹配，`pop` 保证一次性消费，重启即全部失效（等价拒绝）；前端工作区页新增「⌘ 远程命令」入口，输入 → 请求执行 → 展示目标与完整命令 → 确认/取消 → 输出回显。实测：request 202 pending → confirm 200 exit=0 `approved-run`；重复 confirm 400；reject 200 后 confirm 400。门禁：api 2424 passed/89 skipped、e2e 126 passed、前端 lint 0 error。另：`WORKSPACE_SSH_ALLOWED_HOSTS` 语义上一版已改为「留空不限制、填写即收紧」。）

> 版本：V2.20 ｜ 审查日期：2026-11-05（工作区支持远程 SSH：工作区表增量 `kind/ssh_host/ssh_port/ssh_user/ssh_key_name/remote_root`（迁移 `9c1f4b7d2e30`，接在 `b5e2d7c94a10` 后）；新增 `backend/api/app/remote_workspace.py`（paramiko）——私钥**只按文件名**引用（`WORKSPACE_SSH_KEY_DIR` 只读挂载、不入库不回显）、主机默认不限制（凭据即边界：能否连上由目标机 authorized_keys 是否接受私钥决定），`WORKSPACE_SSH_ALLOWED_HOSTS` 非空时作为可选收紧、路径以 `remote_root` 为边界拒绝 `..`/越界、命令执行只跑非交互单条并带超时与 20000 字符输出上限。端点：`POST /api/workspaces` 支持 `kind=ssh`（创建即做连通性探测），`GET /files`、`/files/tree`、`/files/content`、`PUT /files/content`、`DELETE /files` 按类型分派 SFTP，新增 `POST /{id}/exec`（审计 `workspace_remote_exec`）；`upload`、建目录/文件、`rename`、`files/raw` 对远程返回 `VALIDATION`。前端新建弹窗支持类型与 SSH 字段、远程显示连接目标并隐藏上传入口。实测：容器内 sshd + 私钥联调通过（create 201 → list/write/read/exec 全成功，exec `pwd`=/config、`cat hello.txt` 回显正确）；工作区与远程契约测试 24 项通过；前端 eslint 0 error + build 通过。生产 `WORKSPACE_SSH_ALLOWED_HOSTS` 默认空 = 功能关闭，需显式配置后启用。评审整改：`tree` 改单连接递归（原先每层重连）、`exec` 给 channel 设读超时（命令挂住会占满线程，超时返回 `exit_code=-1`/`timeout=true`）、`cd` 改 `shlex.quote`、新增 `WORKSPACE_SSH_KNOWN_HOSTS` 严格校验主机指纹（缺失时 AutoAdd 并告警）。）

> 版本：V2.19 ｜ 审查日期：2026-11-05（用例页滚动修复：`.cases-workbench` 原先写死 `height: calc(100vh - var(--topbar-h) - 20px)`，而外层 `.content` 有 24px padding，工作台比可用高度多出约 28px；同时 `.nordic-layout` 未约束 grid 行高，行被内容撑开导致 `.table-container` 的 `height:100%` 失效、`overflow:auto` 不生效——表格溢出到工作台外被 `overflow:hidden` 裁掉，长列表既看不到底部也无法滚动（用户反馈 `/cases?task_id=…` 无法下拉）。改为 `height:100%` + `grid-template-rows: minmax(0,1fr)`，实测表格 scrollHeight 1696 / clientHeight 439，可滚到 1257 见分页条；新增 e2e 回归（40 条用例断言容器可滚且能滚到底）。）

> 版本：V2.18 ｜ 审查日期：2026-11-04（只读工具与巡检收尾Ⅱ：① `task.list` 复用 `task.status` 的口径返回 `case_set_id` 与 `report_id`，模型可直接给 `/cases?set_id=...`，少一轮工具调用；实测 10 条任务里 testcase 成功项的用例集 ID 正确（`b78a6f40` 等）；② `agent-quality-check.sh` 对比 `history.tsv` 末两行，通过率下降 >10pp 时写 `alerts.log`；题库复跑 10/10。）

> 版本：V2.17 ｜ 审查日期：2026-11-04（只读工具与质量巡检收尾：① `kb.list` / `task.list` 加入 `permission_tier._ALWAYS_AUTO`——纯 SELECT 查询不再逐次弹确认卡（此前模型调用后卡在「等待交互参数」，题目全部超时）；② 工具名由 `platform.kb.list` 收敛为 `kb.list`/`task.list`（wire 名 `platform_kb_list`），避免双前缀；③ 质量题库完成判定改为「消息区出现本轮问题后连续 4s 文本不变，且不在生成/等待确认状态」，修复多步工具调用间隙被误判结束、抓到空回答；④ 断言随能力更新：知识库文档数不再要求「不编造数字」（有工具后应给真实值），任务 ID 题改为必须体现「去查」。实测题库 10/10（阈值 80%），巡检脚本 exit=0 并写入 `data/agent-quality/history.tsv`，已安装 crontab（每天 09:00）。）

> 版本：V2.16 ｜ 审查日期：2026-11-04（Agent 可查性与可审性：① 新增 `platform.kb.list` / `platform.task.list` 两个只读工具（仅 SELECT、脱敏摘要：名称/类型/文档数/任务状态），通用助手回答「几个知识库」「有哪些任务」不再退化成 `bash`+`glob` 探索并卡在确认卡；注册表集合断言与工具总数同步更新（18→20）；② 工具确认卡新增「意图」行：优先展示模型给的工具 `description`，其次命令摘要，最后参数名列表，避免只展示原始 JSON；③ 新增 `deploy/agent-quality-check.sh`，每天跑题库并把 `SUMMARY` 追加到 `data/agent-quality/history.tsv`，低于阈值以非 0 退出；④ 提示词改为优先用只读工具查平台数据。实测三条「查数据」题目从超时/阻塞变为 3/3 通过（13.7s、4.7s、22.9s）。）

> 版本：V2.15 ｜ 审查日期：2026-11-04（UI 自动化深化与 Agent 质量题库：① e2e 新增 `networkResilience` 2 条——慢响应下检索按钮进入「检索中…」且连点只发一次请求、图谱抽屉先显示加载态再渲染，全量 e2e 123 passed；② 新增 Agent 质量题库 10 条（`npm run test:agent-quality`，真实登录 + 真实模型），断言能力边界、流程完整性、不编造 UUID/密钥、不承诺已完成任务、评测停用口径，阈值 80% 判定；③ 提示词加硬约束：禁止用 `bash`/`glob`/`grep` 探索工作区，平台数据没有对应工具时直接说明并给页面入口；`bash` 工具描述同步该约束。当前基线 8–9/10，失败集中在「需要查平台数据」的题目——模型会发起工具调用并等待确认卡，属交互待优化项。）

> 版本：V2.14 ｜ 审查日期：2026-11-04（UI 自动化与 Agent 质量：① 新增 8 条 e2e——登录流程 4 条（未登录跳转、空表单字段校验、凭证错误横幅、登录成功跳转）与知识图谱抽屉 4 条（实体/边渲染、中文类型详情、空态、引擎失败重试、截断提示），全量 e2e 121 passed；② 修复图谱交互缺陷：`pointerdown` 即 `setPointerCapture` 会把后续事件重定向到 svg，节点 click 收不到（表现为「点节点没反应」），改为拖动超过阈值才 capture，并给节点加透明热区；③ 通用助手 `SYSTEM_PROMPT` 从一句话扩为结构化提示（能力边界、中文与结构、`queued`≠完成、不编造任务/用例集 ID、澄清优先、不泄露内部信息）；④ 修复 Agent 全部请求 `UPSTREAM 认证失败`：协议档的 `AI_PROFILE_*` 端点/密钥从未写入 `PROFILE_ENV_FILE`，Agent 读环境文件拿到空 key；已用 `write_profile_env` 补齐两个协议档并切到新网关（`qwen3.8-max-0902` / `deepseek-v4.1-flash-1017`），实测真实对话恢复且回答结构化。门禁：e2e 121 passed、api 2409 passed/89 skipped、前端 eslint 0 error + typecheck/build 通过。）

> 版本：V2.13 ｜ 审查日期：2026-11-04（代码审查与全量测试整改：① 检索扩窗条件从「不足 K 条」改为「不足一半」，避免少 1 条也触发整轮重查（关键词抽取 + 向量检索）导致成本翻倍；② 同一 `doc_id` 重复受理直接返回 `indexing`，不再排第二个 `ainsert`（两次串行写同一文档会被内容哈希判重而报错）；③ `_stale_since` 在引擎无记录时清理，避免长期残留；④ `/query` 纯空白检索词返回 422（原会白跑一次关键词抽取）；⑤ 前端图谱加载加 `kbId` 竞态保护（切库丢弃旧响应）、缩放/平移加边界 clamp。门禁：api 2409 passed/89 skipped、适配层 38 passed、worker 87 passed（1 例既有失败与本批无关）、部署 25 passed、前端 eslint 0 error + typecheck/build 通过。已知未修：worker 既有失败、文档链接 41 处历史失效引用（工具已标历史文档）、ruff 存量 I001。）

> 版本：V2.12 ｜ 审查日期：2026-11-03（知识图谱可读性：① 抽取 prompt 追加语言约束，中文语料不再被翻译成英文实体（`Room`/`房间` 并存的碎片化），只对新索引生效，存量需重建；② 前端图谱布局由力导向改为分层环形（按度数三层同心椭圆），修复 150 节点时斥力把节点压到画布边界形成「边框一圈球」的问题；③ 实体类型中文化、标签上限 14 个且长名截断、新增滚轮缩放与拖拽平移、重置视图。实测新索引一篇退款说明抽出 9 个中文实体（退款申请/退款进度/客服/用户…）。）

> 版本：V2.11 ｜ 审查日期：2026-11-03（RAG 检索优化，不新增平台路径与字段：① 同一文档在 Top-K 中默认最多占 3 席（`LIGHTRAG_MAX_CHUNKS_PER_DOC`），先配额再补齐——平台指标是文档级的，长文档的相邻切块会挤满结果让其它文档永远进不了 Top-K；② 按库过滤后不足 K 条时把 `chunk_top_k` 扩大 3 倍（上限 200）重取一次，且只在结果更多时替换，避免重取让召回倒退；③ 文本前缀相同的重叠切块按重复内容去重；④ 返回前用与索引一致的 embedding 模型补算 query↔chunk 余弦填入 `similarity`（0–1，补算失败为 null），分数只展示不重排，避免破坏图检索排序语义；`shared.kb` 透传分数并拒绝非数值/布尔脏数据。实测 3 篇用例库：naive/hybrid 三个问题均 rank=1，最高分 0.54–0.67，单次检索 0–3s。门禁：适配层 35 passed、api kb 相关 38 passed、Ruff 通过。）

> 版本：V2.10 ｜ 审查日期：2026-11-03（知识库只读知识图谱视图（PRD V1.56 F-RAG-07 / API V2.47）：新增 `GET /api/kb/{id}/graph`，适配层新增 `POST /graph`，从 LightRAG 图存储读取 `get_knowledge_graph("*")` 的最高度数子图，按实体/关系属性里 `file_path` 的前缀 `{kb_id}__` 过滤（单实例多库共享同一图谱，过滤只能发生在召回之后，候选窗口取 `min(max(limit*5,200),1000)`），节点按库内度数降序截断到 `limit`（≤500）并丢弃两端不全的悬空边；`doc_ids` 由 `<SEP>` 拼接的多来源字段解析回填。只读，不提供实体合并或关系编辑；`external_chat` 库返回 `VALIDATION`；引擎不可用返回 `UPSTREAM`，**不得**用空图掩盖引擎故障。前端新增 `KbGraphDrawer`（自实现力导向布局，不引入图表库）与 Kb 页「知识图谱」入口，并在侧边栏恢复 PRD 5.8 的 `/kb` 菜单项（此前页面只能手输地址进入）。门禁：api 2408 passed/89 skipped、适配层 29 passed、部署 25 passed、worker 87 passed（1 例既有失败与本批无关）、Ruff 未新增问题、前端 eslint 0 error + typecheck/build 通过；容器内以假 LLM 实测 `/graph` 返回 2 节点 1 边且 `doc_ids` 正确，跨库 `kb-2` 返回空图。）

> 版本：V2.9 ｜ 审查日期：2026-11-02（知识库接入真实 LightRAG（HKUDS/LightRAG，`lightrag-hku==1.5.7` 锁 tag）：`backend/lightrag` 由「空返回 stub」升级为平台内部适配层，内部契约 `GET /health`、`POST /documents/index`、`GET /documents/status`、`POST /documents/delete`、`POST /query`，并支持 `LIGHTRAG_API_KEY` 内网鉴权。要点：① 文档来源标识改为 `{kb_id}__{doc_id}__{filename}`（LightRAG 的 `file_path` 只保留 basename，不能把 ID 放目录），检索按 `{kb_id}__` 前缀过滤并按库放大 `chunk_top_k`（4 倍、上限 60）；② 建索引异步受理 + 单锁串行（LightRAG 写入/删除共用管线），进度由 `doc_status` 回读映射 `pending/processing→indexing`、`processed→indexed`、`failed→failed`，上传响应不再乐观返回 `indexed`；③ 删除改为「先删引擎再删库」，引擎已配置但删除失败返回 `UPSTREAM`(502)；④ 降级口径收紧：只有未配置/不可达/5xx 才回退本地关键词检索，引擎可用但召回为空仍记 `lightrag`（旧口径把空召回也算降级）；⑤ 检索使用 `only_need_context=True` 只召回不生成答案，`similarity` 允许为 `null`（前端显示占位符，不用 0 冒充）；⑥ 评审整改：检索/受理/状态/删除四类超时改为独立变量（旧 `LIGHTRAG_TIMEOUT_SECONDS` 只作检索回退，避免把删除窗口从 120s 缩短到 60s）、删除按 50 篇/批与状态回读按 200 篇/批提交、`indexing`/`failed` 文档删除不强制引擎成功（否则引擎不可用时用户无法清理）、状态回读加 3 秒进程内缓存、`list_docs` 与上传响应用局部变量+`UPDATE` 避免 commit 后逐行回表拉 20MB 正文、待索引队列上限 64（超限 429 落 `failed`）、停机 30 秒宽限后取消、引擎残留 `processing` 且本进程无任务时判 `failed`（中断自愈）、删除前按 `file_path` 校验知识库归属、失败表限 1000 条。不新增平台 REST/WS 路径与字段；API.md V2.46、方案《AI测试与评估平台-LightRAG接入技术方案》V1.0 登记。适配服务必须单容器单 uvicorn worker、单写入者持有 `./data/lightrag`；传递依赖由 `backend/lightrag/constraints.txt` 锁定。门禁：api 2405 passed/89 skipped（`tests/test_loop_ws_handler.py` 在本机环境挂起，为本机既有现象，已单独排除）、适配层契约与引擎行为 22 passed、部署单测 25 passed、worker 87 passed（`test_worker_only_claims_testcase_even_before_legacy_cleanup` 为既有失败，与未改动版本一致）、Ruff 未新增问题（存量 I001 不在本批范围）、前端 typecheck/build 通过；容器内以假 LLM/Embedding 跑通 `ainsert→indexed→检索→跨库删除拦截→删除` 全链路，队列上限实测返回 429。）
> 版本：V2.8 ｜ 审查日期：2026-09-28（产品定位改为测试用例生成 Agent；新增任务仅限 testcase，候选用例先存草稿再审核确认；benchmark、RAG 评测和压测停止新建、领取及派生，历史任务与报告只读。下文旧评测实现描述仅供历史维护，当前范围以 PRD V1.51 / API V2.34 为准。）
> 版本：V2.7 ｜ 审查日期：2026-09-16（专家协作 P1 审查修复：关闭开关同步过滤工具白名单；整组取消与 spawn 共用协作行锁且保留旧请求回执；分批调度原子恢复 running；主回合资源收尾持久化最终调用预算。API V2.7、PRD V1.29、专家协作方案 V0.7；API 1607 passed/78 skipped、Worker 50 passed，Ruff 与前端 typecheck/build 通过。未新增后台恢复能力。）
> 版本：V2.6 ｜ 审查日期：2026-09-16（专家协作 P1 前台闭环：主 `general` Agent 接入 `agent.list/spawn/status/wait/result/cancel`；新增协作/实例/运行/独立事件/命令回执五类持久表与迁移 `f70e5a53bd54`；子运行复用原生 AgentLoop，独立 `.subagents/<run_id>` 工作目录，共享 80 次调用/3 并发/单运行 20 次硬调用次数账本；Agent 页新增持久协作、成果和单个/整组停止面板。P1 仍为同进程前台执行；主流 outbox、信箱/工作项/续跑及跨进程租约恢复未交付，不得宣称后台协作。）
> 版本：V2.5 ｜ 审查日期：2026-09-14（纯说明文档提交不构建、不触发 CI/CD；部署计划统一由 `deploy/plan_services.py` 按 Dockerfile 输入计算，MCP 工具自动发现，取消 runner 常驻构建；部署脚本变更复用已有镜像，Compose 构建参数变更保守全量处理）。
> 版本：V2.4 ｜ 审查日期：2026-09-14（V2.4 GitHub Actions 额度治理：取消 `pull_request` 触发，功能分支与 PR 不运行 GitHub Actions；仅 `push main` 运行 CI/CD。PR 仍可用于人工审查，但合入前的构建、自检和测试须在本地完成）。
> 版本：V2.3 ｜ 审查日期：2026-09-12（V2.3 部署文档校正（按生产实测同步）：§4 链路更正为 GitHub Runner 构建并推送 GHCR、生产机受限并发拉取（`DEPLOY_PULL_PARALLEL` 默认 2）后滚动替换，服务器本地逐服务串行构建仅作回退路径（web `NODE_BUILD_MEMORY` 默认 1536）；`SSH_USER`/`SSH_PRIVATE_KEY` 与 §4.2 SOP 命令由 `deploy` 改为 `root`（服务器无 `deploy` 用户，仓库/密钥/部署均以 root 运行；Actions 部署入口从目标提交提取 `deploy/deploy.sh` 执行）；新增 §4.3 服务器侧备用巡检（root crontab 每 5 分钟 `auto-deploy-watch.sh`，`.deploy-mode` 切换 actions/local，与 Actions 共用 `.deploy.lock`））。版本：V2.2 ｜ 审查日期：2026-09-09（V2.2 废除「首次登录强制改密」（产品决策）：后端开户/重置密码/引导成员一律不再置 `must_change_password=true`（`shared/models.py` 列默认改 False、`schemas.UserCreate` 默认 False 且开户忽略请求字段、`users.reset_password` 与 `auth.change_password` 不再维护标记、bootstrap 恒 False，列/响应字段保留兼容）；前端删除 Login.vue 强制改密弹窗与登录拦截、MainLayout 改密弹窗收敛普通形态（可关闭、恒显示原密码与取消）、auth store 移除 mustChangePassword getter；API.md V1.84、PRD V1.19 登记；qa-test 等测试账号登录不再弹改密提示）。版本：V2.1 ｜ 审查日期：2026-09-09（V2.1 管理端工作区下线 + 智能体新建工作区：**产品决策**移除管理端「工作区管理」——`/api/admin/workspaces` 五个接口（列表/磁盘统计/文件展开/沙箱清理/孤儿清理）整文件删除（`backend/api/app/routers/workspaces.py` 下线、`main.py` 注册移除、`workspace_service.orphan_direct_children` 删除、`test_admin_workspaces.py` 删除，孤儿/管理端定位相关测试同步裁剪）；前端 `AdminWorkspaces.vue`/路由/侧边栏「工作区」菜单/`api.admin.*` 封装与专属类型全删，用户域「我的工作区」不受影响（API.md V1.82：§3.12.2 整节移除、原 §3.12.3 重编号为 §3.12.2）；**智能体页草稿会话绑定面板新增「新建工作区」即建即绑**（`Agent.vue createDraftWorkspace`，创建后自动选中绑定，无需跳「我的工作区」）；新增跑测账号 `qa-test`（生产，`must_change_password=false`，凭据仅线下交付，跑测数据一律落该账号，harness-ws-probe 跑测传 `--user qa-test`，禁止用 admin 跑测污染业务数据）。版本：V2.0 ｜ 审查日期：2026-09-07（V2.0 沙箱档位化与会话绑定（主稿 A《工作区与沙箱设计方案》V0.5 / 关联稿 B V0.6.1；分支 `feat/sandbox-g4-policy`→G4、`feat/sandbox-g5-binding`→G5）：**G4 = F2** 删除四处 bash 命令词表与静态裁决（`feedback/rules.py` gate 分支、`sandbox_kernel` 词表、`dispatch` `bash_approval_reason`/`bash_block_reason`、runner 黑名单，含 sudo 残余项——S3/G2 部署后按 PoC 定稿形态删除，理由见 B 稿 D1 勘误），bash 直通受控沙箱；runner 契约改 `policy{mode, workspace_root}`（mode ∈ workspace-write/read-only，缺省/非法 VALIDATION 双向 fail-closed），kernel bind 按 mode 化，`config.sandbox_bash_default_mode`（默认 workspace-write=行为不变）；runner 校验 `is_valid_session_workspace` → `resolve_workspace_path`（前缀+realpath 逐段、接受嵌套 scope、拒符号链接、bind canonical）；API.md V1.75 相关工具描述同步。**G5 = F3** 会话-工作区绑定接线：`POST /api/sessions` 增量 `workspace_id/scope_path`（创建固化、仅 private、属主校验+目录就绪、AuditLog `session_workspace_bind`）；`resolve_session_sandbox` 唯一沙箱解析入口（ws 注入替换，绑定失效 fail-closed 不回落 legacy）；已绑定会话转 team 拒绝（BLK-4）；`SessionOut` 增绑定字段与 `workspace_name`；前端草稿会话「绑定工作区」预选 + 会话列表/顶栏绑定展示；API.md V1.76（§3.4/§3.12.3）。全量门禁：api 894 passed/20 skipped、runner 17、worker 50、前端 typecheck/build 通过。F4（read-only 档灰度）与 G6/F5（workspace-write 档+升档审批+契约组）未交付：放行依赖 S3 空转观察（≥7 天至 ~2026-09-14）与部署决策；图级 tool_approval 端到端用例随 F5 升档卡接入恢复；附件 staging 仍 legacy（归属迁移留评审）。V1.9 用户工作区实体 F1/G1（《工作区与沙箱设计方案》V0.4.1；历史）：新增 `workspaces` 表（软删 `deleted_at`、每属主活跃唯一）与 `sessions.workspace_id(FK ON DELETE RESTRICT)/scope_path` 列（迁移 `e8f1a2b3c4d5`）；用户域 `GET/POST/PUT/DELETE /api/workspaces`——注销=软删，purge=行锁内显式解绑 + FK RESTRICT 兜底（禁 SET NULL），写 AuditLog；`GET/POST /api/workspaces/{id}/files` 一层浏览/建夹（`app/workspace_service.py` 段级 + realpath 防穿越单一实现）；孤儿判定与 `delete_orphan` 排除活跃 `workspaces.id`（B2 行态守卫）；前端「我的工作区」页 + 导航 + PRD 5.8 增补登记；API.md V1.75（§3.12.3）。全量门禁：api 880 passed/20 skipped、worker 50 passed、前端 typecheck/build 通过。会话绑定接线（F3）与 legacy 复活（F3）未交付，本期会话不产生绑定。V1.8 dsh 借鉴五项改进交付：护栏 #4 事件词汇表版本化（`backend/shared/event_vocab.py` 单一事实源，当前 `event.v4`；api/worker 落库带 `event_version` 保留字段、`_forward_loop` 按 `event_vocab_strict` 默认告警跳过/fail-closed 拒收）→ #1 clarify 问答恢复（API.md V1.72 转正：`ask_user_question` 中断落澄清卡，三类卡共用 `pending_confirm` 单行互斥、meta `schema_version=2`、回执 `clarify_ack`；`worker.general` 视野含 `ask_user_question`；前端 ClarifyCard）→ #3 审批终态（API.md V1.73：`approval_terminal` expired/cancelled、TTL `agent_approval_ttl_seconds` 幂等判龄、api 后台扫描、`/stop` 清悬挂审批卡；ApprovalCard 失效态）→ #2 上下文压缩事件化首期（API.md V1.74：`NativeToolResultStore` 超长结果先裁剪带标注、窗口裁剪留痕 `context_trim` 仅元信息）→ #5 执行选择显式化（`harness/security/exec_policy.py` 收敛沙箱/演练决策，默认行为不变）；全量门禁：api 854 passed / 20 skipped / 0 failed、worker 50 passed、前端 typecheck/build 通过；H5 批次 2 未完成项延续：`AGENT_CHECKPOINTER=postgres` 生产切换、网关粘性路由落地、重启恢复演练、`worker.sandbox` 安全评审（#1/#3 跨重启寻址价值仍依赖此前置，本批按单副本/memory 语义交付））

---

## 1. 项目简介与架构 (Overview & Architecture)

- **定位**：面向单一研发团队的测试用例生成平台，利用 AI Agent 将需求转为可审核的功能测试用例。
- **核心逻辑**：Agent 或 `/cases` AI 对话框生成用例候选 → 保存为草稿 → 人工审核确认入库。旧评测与压测只保留历史查询。

### 1.1 服务拓扑与网络端点
| 服务名称 | 容器标识 | 端口 | 访问方式 / 说明 |
| :--- | :--- | :--- | :--- |
| **Web 前端** | `web` | `80` | `http://47.119.132.83/`（Nginx 反代 `/api` 与 `/ws`） |
| **API 服务** | `api` | `8000` | `http://47.119.132.83:8000/docs`（FastAPI + Swagger + 短 MCP） |
| **Worker 引擎** | `worker` | - | 容器内部网络通信，只领取测试用例生成任务 |
| **数据库** | `postgres` | `5432` | PostgreSQL 16 关系数据库（pgvector 镜像，含向量扩展；持久卷 `pgdata`） |
| **缓存/记忆** | `redis` | - | 容器内部网络通信；Harness 记忆层短期回合状态与幂等键（持久卷 `redisdata`） |
| **RAG 引擎** | `lightrag` | `9621` | LightRAG 混合检索与图谱评测服务 |
| **压测引擎** | `stress` | `19090` | go-stress-testing 发压引擎，暴露 `/metrics` |

> 初始管理员：`admin / admin123`（由 `.env` 中 `BOOTSTRAP_ADMIN_PASSWORD` 注入）。

### 1.2 核心架构流
```text
浏览器 Vue 3 (Naive UI)
  │── WS: /ws/agent?ticket= ──► FastAPI Agent Host (纯对话流式生成 + 任务事件桥接)
  │── REST: /api/* ───────────► FastAPI REST API (认证 / 协议档 / 数据集 / 报告)
                                        │
                                        ▼
                                  PostgreSQL 16 (tasks 状态机 / task_events / 数据集)
                                        │
                                        ▼
                                  Python Worker (异步执行：三协议评测 / LightRAG / 派生压测)
```

> 骨架化说明（V1.6.0）：Agent 图已收敛为单节点纯对话
> `START → chat_stream → END`；多范式路由（direct/chat/react/plan_solve）、
> ReAct 思考链、reflect 反思、思考流、澄清卡、确认卡、短工具调用与斜杠命令
> 已全部移除，仅保留消息 → LLM 直接生成回复 → `assistant_message` +
> `response.completed` 的最小链路。
>
> 混合引擎增量（V1.5 实施状态地图）：`hybrid_engine_enabled=true` 时图为
> `START → router → direct | chat | workflow(八节点 DAG) | agent(TAOR 子图)`；
> Workflow 链为 W0 select_skill → W1 prepare_slots → W2 load_skill → W3 validate_gates
> → W4 build_task_spec → W5 await_confirm → W6 enqueue → W7 summarize。W5 首次到达
> 时发确认卡并收尾本轮，用户确认后经 `pending_confirm` 行锁事务清卡，再以
> `workflow_confirm` 注入重放回合——**入队唯一经 W6**；W0/W2/W3/W6 失败统一补
> `response.completed(error)`，确保每轮恰有一个终态事件。
> Agent 链为 plan → discover → orchestrator ⇄ tools，orchestrator 停止或守卫截断后
> **一律进 reflect 判决**：pass/clarify/reject 收尾（reject 的
> `finish_reason="error"`），repair 回 orchestrator、retry 回 plan——两档均为**回合级**
> 硬上限（`MAX_REPAIRS=1` / `MAX_REPLANS=2`，常量唯一来源 `feedback/review.py`）。
> 默认关闭时行为不变。

### 1.3 权威文档与冲突裁决
1. **L0 产品权威**：[`docs/AI测试与评估平台-PRD.md`](docs/AI测试与评估平台-PRD.md)（功能范围、状态机、确认卡字段唯一真理）；
2. **L1 接口契约**：[`docs/AI测试与评估平台-API.md`](docs/AI测试与评估平台-API.md) **V1.4+**（REST/WS 路径、JSON 契约唯一真理）；
3. **Agent 子系统**：[`docs/AI测试与评估平台-Agent开发文档.md`](docs/AI测试与评估平台-Agent开发文档.md)（骨架化纯对话、上下文算法、长任务门禁）；**JSON 字段名与路径仍以 API.md 为准**；
4. **裁决铁律**：代码/计划与 PRD 冲突以 PRD 为准；接口与 API.md 冲突以 API.md 为准。禁止私自扩充产品范围（Agent 说明书新增路径必须先回写 API.md）。

### 1.4 文档命名与更新规范 (Documentation Conventions)
1. **统一文件命名**：所有设计、契约与技术方案文档统一归档于 `docs/` 目录，格式严格遵循 `docs/AI测试与评估平台-<模块或主题>.md`（如 `docs/AI测试与评估平台-Agent大模型接入与耗时技术方案.md`），严禁无前缀或随意自创命名；
2. **文档闭环更新**：功能迭代或契约演进后，必须在对应技术文档末尾同步追加「修改代码文件与作用清单」，并在文档头部更新版本号（如 `V1.1`、`V1.2`）与审查日期；
3. **提交与分支规范**：纯文档变更使用 `docs(<scope>): <中文描述>` 格式提交，重要文档改造建议拉出 `docs/<scope>-简述` 分支。

### 1.5 运行时数据流与实现状态地图

**任务状态机与 Worker 领取**（`tasks` 表 `queued→running→succeeded/failed/cancelled`）：
- Worker 主循环（`backend/worker/app/main.py`）用 `SELECT ... FOR UPDATE SKIP LOCKED` 领取 `queued` 任务，受 `settings.max_running_tasks` 并发闸门约束（默认 3）；
- `uq_tasks_active_session` 部分唯一索引在创建侧保证**同一会话内任务串行**（防止确认卡重复提交）；
- 执行器（benchmark / testcase）自管数据库 Session，主循环只负责领取与终态兜底；**禁止跨 Session 传 ORM 对象**（会触发 `InvalidRequestError`，导致任务永久卡 `running`）。

**WS 事件机制**（`backend/api/app/routers/ws.py` + `session_connections.py`）：
- 持久事件统一写入 `ws_events` 表并带公共头 `{event, session_id, task_id, event_id, ts, payload}`；
- `_emit` 在连接锁内完成「取号 → 落库 → 发送 → 推进游标」；`_forward_loop` 后台循环按游标增量把 **Worker 进程外**写入的事件推送到当前连接；
- 断线重连按 `last_event_id` 补发；流式帧（`assistant_delta`）与心跳 `pong` 为瞬态帧，**不落库、不占事件号**（骨架化后无 `stream=think`）；
- 关闭码 `4401`=重新领票，`4404`=会话不存在/共享被收回。

**Agent Harness 并发模型**（`routers/ws.py` + `agent/graph.py`）：
- 收包循环**不得 await 整轮 Harness**，`_handle_user_message` 必须丢 `asyncio.Task` 执行；
- 会话级 abort 是进程内 dict（单副本或网关按 `session_id` 粘性路由的前提）；
- 默认关闭时 Agent 为单节点纯对话图（`graph.py` + `routing.py` 的
  `chat_stream_node`）；开启时 Router 分流至 Workflow DAG 或 Agent TAOR。`/stop`
  即时中断与 `cancel_task` 保留在收包循环。

**模型单一事实源**：`backend/shared/models.py` 由 api 与 worker 共用（`api/app/models.py` 仅为 re-export）；改表必须 `alembic revision --autogenerate`，禁止双副本漂移。

**实现状态地图（真实现 vs Mock）**：

| 模块 | 状态 | 位置 |
| :--- | :--- | :--- |
| benchmark 基准评测 | 已停用；旧执行器仅保留历史代码，活动任务取消、报告只读 | `backend/worker/app/benchmark.py` |
| testcase 用例生成 | 真实执行器（六策略 LLM 生成、72h 确认超时扫描） | `backend/worker/app/testcase.py` |
| 需求基线与覆盖 | MVP 已交付：编号抽取、基线确认、用例绑定、覆盖率与自动关联候选；不改用例正文与 revision | `backend/shared/requirements.py`、`backend/api/app/routers/requirements.py` |
| 用例评审与版本 | MVP 已交付：人工评审请求/结论/评论、AI 历史、版本快照/diff/回滚新草稿；评审状态独立于 status | `backend/api/app/routers/case_reviews.py`、`backend/shared/case_review.py` |
| 用例质量看板 | MVP 已交付：运行/生成/确认/采纳率/成功率/AI 均分与按天/模型/状态/模块分布；只读聚合 | `backend/api/app/routers/metrics.py`、`frontend/src/views/CasegenQuality.vue` |
| 需求变更分析 | MVP 已交付：基线版本链、版本 diff、受影响用例集/用例；只读分析，不自动改用例 | `backend/api/app/requirement_change_service.py`、`frontend/src/components/drawers/RequirementCoverageDrawer.vue` |
| 用例资产库 | MVP 已交付：确认物化、跨集合检索、标签、文本查重、历史回填；不做自动合并/复制 | `backend/api/app/case_asset_service.py`、`frontend/src/views/CaseAssets.vue` |
| 站内通知 | MVP 已交付：任务生成/失败、评审指派/结论通知；顶栏未读与通知页；无外发渠道 | `backend/api/app/notification_service.py`、`frontend/src/components/notifications/NotificationBell.vue` |
| 全局搜索 | MVP 已交付：八类实体只读检索，私有会话/工作区/记忆按属主过滤 | `backend/api/app/routers/search.py`、`frontend/src/components/search/GlobalSearch.vue` |
| rag 知识库评测 | 已停用；保留历史报告只读 | `backend/worker/app/rag.py`、`backend/shared/kb.py` |
| stress 压测 | 已停用；不再派生，运行中的旧任务取消并请求引擎停止 | `backend/worker/app/stress.py` |
| Agent 图 | **混合引擎灰度中**：默认关闭时为骨架化纯对话（`START → chat_stream → END`）；开启后 `START → router → direct/chat/workflow/agent`。H0–H5 批次 1（见版本行）均已交付；V1.8（dsh 借鉴五项）追加：#4 事件词汇表版本化（`shared/event_vocab.py` 单一事实源、`vocab_version` 公共头、落库 `event_version` 保留字段、`event_vocab_strict` 转发护栏，当前 `event.v4`）；#1 clarify 恢复（API.md V1.72：`ask_user_question` 澄清卡 B 路线——三类卡共用 `pending_confirm` 单行互斥、`meta.schema_version=2` 且对旧卡零影响、回执 `clarify_ack`；前端 ClarifyCard 与 Confirm/Approval 同构）；#3 审批终态（API.md V1.73：`approval_terminal` expired/cancelled、TTL 幂等判龄 + api 后台扫描、`/stop` 清悬挂审批卡，ApprovalCard 失效态）；#2 压缩事件化首期（API.md V1.74：超长工具结果 store 先裁剪带标注、窗口裁剪留痕 `context_trim` 仅元信息）；#5 执行选择显式化（`harness/security/exec_policy.py` 决策收敛，默认行为不变）。H5 批次 2 **未完成**：`AGENT_CHECKPOINTER=postgres` 生产切换、网关粘性路由落地、重启恢复演练、`worker.sandbox` 安全评审（#1/#3 跨重启寻址依赖此前置，未切换前按单副本语义交付）；`thought`/`tool_progress`/`tool_output_delta`/`plan` 无生产者，主开关默认关闭 | `backend/shared/event_vocab.py`（新）、`backend/api/app/agent/{graph,routing,router_node,workflow_nodes,taor_nodes}.py`、`backend/api/app/routers/{ws.py,main.py}`、`backend/api/app/harness/{security/exec_policy.py(新),execution/{toolnode,ask_user,native_results}.py,orchestration/agents.py,context/window.py,contracts/events.py}`、`backend/worker/app/events.py` |

---

## 2. 项目结构 (Project Structure)

```
ai-eval-platform/
├── backend/
│   ├── api/                     # FastAPI 主服务（路由、认证、数据模型、短 MCP）
│   │   ├── app/                 # 核心代码（routers/, models.py, schemas.py, errors.py, security.py, agent/）
│   │   ├── migrations/          # Alembic 数据库迁移版本脚本
│   │   └── tests/               # Pytest 自动化测试
│   ├── worker/                  # 异步任务 Worker（轮询任务队列、三协议适配、评测执行）
│   ├── lightrag/                # LightRAG 服务组件
│   └── stress/                  # go-stress-testing 压测组件
├── frontend/                    # Vue 3 前端工程（Naive UI, Pinia, Vue Router, Vite）
│   └── src/                     # 源码（api/, layouts/, router/, stores/, views/, naive-theme.ts）
├── deploy/                      # 部署脚本（server-setup.sh 服务器初始化, deploy.sh 同步部署）
├── docs/                        # PRD、API 契约、原型设计与开发计划
├── Web-Prototype/               # 静态 HTML 原型（视觉与交互参考）
└── docker-compose.yml           # 全栈六件套容器编排文件
```

### 2.1 常用开发命令（工作目录 = 命令所在目录）

后端 API（`backend/api/`）：
- 安装依赖：`pip install -r requirements.txt -r requirements-dev.txt`
- Lint：`ruff check . ../shared`（CI 会连同 `backend/shared` 一起检查）
- 全部测试：`pytest`
- 单个文件：`pytest tests/test_ws_agent.py`
- 单个用例：`pytest tests/test_ws_agent.py -k "confirm_ack"`
- 生成迁移：`alembic revision --autogenerate -m "中文描述"`
- 应用迁移：`alembic upgrade head`（api 容器启动时自动执行）

后端 Worker（`backend/worker/`）：
- 测试：`PYTHONPATH=.:.. pytest`（依赖共享包 `backend/shared`；Windows 用 `set PYTHONPATH=.;..`）

前端（`frontend/`）：
- 开发热更：`npm run dev`（http://localhost:5173，`/api` 与 `/ws` 代理到 :8000）
- 类型检查：`npm run typecheck`（`vue-tsc --noEmit`；注意 `npm run build` **不包含**类型检查）
- 构建：`npm run build`

全栈一键启动：`docker compose up -d --build`（前端 http://localhost，API http://localhost:8000/api/health，Swagger http://localhost:8000/docs）

---

## 3. Git 提交与分支规范 (Git Conventions)

采用 **[Conventional Commits](https://www.conventionalcommits.org/)** 规范。**提交描述（Subject 与 Body）必须使用中文**。  
提交作者身份由宿主机当前的 Git 配置（`git config`）或 GitHub CLI 自动决定。

### 3.1 模块开发必须开分支（强制）

`main` 只接受已审查的合并，**禁止**在 `main` 上直接开发模块功能、修缺陷或改契约。AI Agent 写代码前必须确认当前分支**不是** `main` / `master`；若在主干上，先开分支再改。

```text
main（保护，仅 PR 合入）
  └── feat/agent-harness
  └── feat/web-confirm-card
  └── fix/worker-progress
  └── docs/api-v1.4
         │
         ▼
      Pull Request → 人工审查与本地门禁 → 合并 main → 按变更触发 CI/CD（纯文档跳过）
```

**分支命名**：`<type>/<scope>-<短横线英文或拼音简述>`，type/scope 与提交规范同一套。

| 场景 | 分支示例 | 说明 |
| :--- | :--- | :--- |
| Agent 子系统 | `feat/agent-harness` | 对话、Harness、斜杠、WS |
| API / 短 MCP | `feat/api-slash-commands` | FastAPI 路由、契约落地 |
| 前端工作台 | `feat/web-context-meter` | Vue 页面与组件 |
| Worker / 压测 | `fix/worker-rag-stub` | 长任务、进度、LightRAG 占位 |
| 数据集 / 用例 | `feat/dataset-ai-generate` | 页面 AI 候选 |
| 文档 / 契约 | `docs/api-agent-prefs` | 仅文档也可开分支，避免和功能混在 main |

规则：

1. **一模块一分支**（或一 Task 一分支）。Agent、前端、Worker 不要堆在同一条长期分支上。  
2. 从最新 `origin/main` 拉出：`git fetch origin && git checkout -b feat/agent-xxx origin/main`。  
3. 推送功能分支：`git push -u origin HEAD`。合入用 **Pull Request**，禁止把功能分支 `push --force` 到 `main`。  
4. **仅 `push main` 自动触发 GitHub Actions CI/CD，纯说明文档除外**。功能分支和 Pull Request 不运行 Actions；代码提交、开 PR、合入前按 §2.1 完成本地门禁，文档按下述例外自检。
5. 允许直接在 `main` 的例外：**无代码、无迁移**的错别字级文档（仍建议开 `docs/` 分支）。契约变更（API.md / PRD / Agent 说明书）按模块开 `docs/` 分支。  
6. 合并后删除远程功能分支，不在本地长期占用 `main` 做开发。

### 3.2 提交信息

- **提交格式**：`<type>(<scope>): <中文简述>`
- **常见 Type**：`feat`（新功能）、`fix`（修缺陷）、`docs`（文档）、`style`（格式）、`refactor`（重构）、`test`（测试）、`ci`（CI/CD）、`chore`（杂项）。
- **常用 Scope**：`api`、`worker`、`web`、`mcp`、`rag`、`stress`、`auth`、`dataset`、`profile`、`task`、`report`、`agent`、`deploy`。
- **提交前强制门禁**：提交代码前**必须在本地先完成构建与自检**，确保 0 错误后方可执行 `git commit`：后端 `cd backend/api && ruff check . ../shared && pytest`、`cd backend/worker && PYTHONPATH=.:.. pytest`；前端 `cd frontend && npm run typecheck && npm run build`。
- **纯文档例外**：仅修改 `docs/**`、根目录 `*.md`、各级 `README.md` 时，无需应用构建与测试，只校验文档内容、链接与 `git diff --check`。运行时提示词（例如工具目录中的 `SKILL.md`）不属于说明文档例外。仅修改部署脚本/工作流时，运行部署单元测试、Shell 语法、工作流 YAML 和 Python 静态检查，无需构建未修改的业务应用。
- **提交标题编码检查（强制，防乱码）**：提交消息含中文时，**禁止在非 UTF-8 终端（如 Windows PowerShell）直接内联中文参数**执行 `git commit -m "中文标题"` / `gh pr create --title "中文"`——终端编码会把中文标题写成乱码并永久进入历史（曾发生：`docs: 娣峰悎寮曟搸…`）。正确做法与提交前检查：
  1. 中文提交消息一律写入临时文件后 `git commit -F <msg_file>`（`gh pr create` 同理用 `--body-file`，标题用 ASCII 或经文件传递）；
  2. 提交后立即检查标题可读：`git log -1 --format=%s` 与 `git show -s --format=%B HEAD` 输出必须为正常中文；
  3. 乱码特征速查：出现 `�`（替换符）、`娣峰悎` 类错位汉字段、`?` 替代中文、或英文与乱码混排即视为失败；
  4. 发现乱码：**未推送** → `git commit --amend` 用文件方式重写；**已推送未合入** → 分支内 amend 后 `push --force-with-lease`；**已合入 main** → 改写历史影响 CD 与协作者，须先评估（除非用户明确授权，禁止 force push main），并优先以修正提交记录说明。
- **中文示例**：
  - `feat(api): 新增 WebSocket 短票鉴权接口`
  - `fix(worker): 修复大模型裁判调用超时重试逻辑`
  - `docs(agent): 更新自动部署排查指南与提交规范`

---

## 4. 自动部署与 CI/CD (CI/CD & DevOps)

```text
功能分支 Push / Pull Request ──► 不触发 GitHub Actions（本地完成构建、自检、测试）
push main ──► CI 与 Deploy 各自按路径触发（纯说明文档跳过）
                  │ Plan：对比上次成功部署提交，计算需要重建的服务
                  │ Build：GitHub Runner 构建镜像并推送 GHCR（ghcr.io/rue1218/ai-eval-platform-<服务>:<提交>）
                  ▼
             CD（SSH 以 root 登录）──► 服务器 /opt/ai-eval-platform
                  │ 从目标提交提取 deploy/deploy.sh 执行（入口与提交严格同版本）
                  ▼
             deploy.sh：reset 到精确提交 → 仅拉取变化服务镜像（并发上限 DEPLOY_PULL_PARALLEL=2）→ 滚动替换
```

**生产只跟 `main`。** 功能分支与 Pull Request 不自动触发 GitHub Actions；`push main` 按路径过滤运行 CI/CD。Deploy 保留 `main` 上的手动触发入口。

**增量部署单一事实源**：Actions 和服务器统一调用 `deploy/plan_services.py`，对比上次成功部署与目标提交（包含失败轮次的累积改动）。按 Dockerfile 的 COPY/ADD 输入选择服务；`backend/*_mcp/Dockerfile` 自动发现工具。取消 runner 常驻构建、部署脚本改动强制构建全部 MCP。无变化服务复用上次成功镜像；首次部署/基准丢失或 Compose 构建输入变化时保守全量构建。不得把运行时 Markdown 提示词误当纯说明文档过滤。

镜像默认在 GitHub Runner 上构建并推送 GHCR，服务器只拉取；仅回退路径（手动执行 `deploy/deploy.sh` 或备用巡检 `mode=local`）会在服务器本地逐服务串行 `docker compose build`（web 受 `NODE_BUILD_MEMORY` 限制，默认 1536）。纯文档变更（`docs/**`、`*.md` 等）不触发部署。

### 4.1 Secrets 配置清单
- `SSH_HOST`：`47.119.132.83`（纯 IP，严禁带 `http://`）
- `SSH_PORT`：`22`（**必须是 22**，切勿误填 Web 的 80/8000）
- `SSH_USER`：`root`（服务器无 `deploy` 用户，仓库/密钥/部署均以 root 运行）
- `SSH_PRIVATE_KEY`：服务器 root 的完整私钥（`/root/.ssh/id_ed25519`，含首尾标记）

### 4.2 部署与构建失败排查 SOP
1. **CI 失败**：本地进入 `backend/api/` 执行 `ruff check --fix .` 与 `pytest`；进入 `frontend/` 执行 `npm run build`。
2. **CD SSH 握手失败 (`connection reset by peer`)**：检查 `SSH_PORT` 是否误填为 80/8000（必须为 22）；确认云服务器安全组 22 端口对 `0.0.0.0/0` 放行。
3. **Docker 容器残留 (`No such container`)**：`deploy.sh` 会自动调用 `docker rm -f` 强力清理并自愈拉起。手动修复命令：
   ```bash
   docker rm -f $(docker ps -a -q --filter "name=ai-eval-platform") 2>/dev/null || true
   bash /opt/ai-eval-platform/deploy/deploy.sh
   ```
   （手动执行不带 CI 环境变量，走服务器本地构建回退路径，耗时较长。）
4. **容器状态异常 / 端口占用**：在服务器执行 `netstat -tlpn | grep -E '80|8000|5432'` 排查端口占用；执行 `docker compose logs -n 100 api` 查看日志。
5. **git `HEAD.lock` / `update_ref failed`**：被取消的旧 CD 可能留下 `/opt/ai-eval-platform/.git/HEAD.lock`。确认没有正在跑的 `git`/`deploy.sh` 后删除锁文件并重跑 Deploy：
   ```bash
   rm -f /opt/ai-eval-platform/.git/HEAD.lock /opt/ai-eval-platform/.git/index.lock
   bash /opt/ai-eval-platform/deploy/deploy.sh
   ```
   `deploy.sh` 在拿到部署互斥锁后会自动清理过期 `*.lock`。
6. **紧急回滚**：本地 `git revert HEAD && git push origin main`（CI 重建并部署回滚后的镜像）；或在服务器 `/opt/ai-eval-platform` 执行 `git reset --hard <commit_id> && bash deploy/deploy.sh`（走本地构建路径；`reset --hard` 会丢弃工作区未提交改动，执行前确认无人在改）。

### 4.3 服务器侧备用巡检（GitHub Actions 不可用时的回退链路）

服务器 root crontab 每 5 分钟执行 `deploy/auto-deploy-watch.sh`，巡检 `origin/main` 是否有未部署提交；行为由未跟踪文件 `/opt/ai-eval-platform/.deploy-mode` 控制：

- `actions`（默认）：只记录「待部署」日志，由 GitHub Actions 主链路完成部署，避免双链路重复部署；
- `local`（回退）：发现新提交即在服务器本地构建并部署，不依赖 Actions。切换：`echo local > /opt/ai-eval-platform/.deploy-mode`；恢复主链路：`echo actions > /opt/ai-eval-platform/.deploy-mode`。

巡检/部署日志在 `/opt/ai-eval-platform/logs/auto-deploy.log`（cron 标准输出重定向在 `logs/auto-deploy-cron.log`）。备用巡检与 Actions 共用 `.deploy.lock` 部署互斥锁，不会并发部署；需要手动立即部署一次时执行 `bash /opt/ai-eval-platform/deploy/auto-deploy-watch.sh --force`。

---

## 5. 开发规范 (Development Standards)

### 5.1 全中文注释要求（核心铁律）
所有新增与修改的代码（Python、Vue/TypeScript、Shell），**函数/类 docstring、复杂业务分支、类型定义必须配齐中文注释**。

```python
# Python 注释范例
@router.post("/tasks", response_model=TaskOut, summary="创建评测任务")
async def create_task(payload: TaskCreateIn, db: Session = Depends(get_db)) -> Task:
    """创建评测任务并入队 (queued)。若 payload.with_stress=True，评测成功后由 Worker 派生压测。"""
```

### 5.2 后端规范 (Python 3.12 / FastAPI)
1. **10 大标准错误码**：禁止原生 422/500 直接出给浏览器，必须统一抛出 `AppError(code=ErrorCode.XXX, message="说明")`：
   `UNAUTHORIZED`(401/403), `VALIDATION`(400), `NOT_FOUND`(404), `BUDGET_EXCEEDED`(409), `CONCURRENCY`(409), `WHITELIST`(403), `NEED_APPROVAL`(403), `UPSTREAM`(502), `TIMEOUT`(504), `INTERNAL`(500)。
2. **数据库与迁移**：修改 `models.py` 后必须通过 Alembic 生成迁移脚本：`alembic revision --autogenerate -m "..."`，禁止私自手动改库。
3. **安全与鉴权**：API Key 必须用 Fernet 加密存储且只写不回显；用户鉴权用 `HttpOnly` Cookie；WebSocket 使用 5 分钟有效期的单次短票 `ws-ticket`。
4. **长短任务分离**：`api` 容器仅负责快速交互与任务入队，耗时评测与压测全部由 `worker` 异步消费并下发给 `stress` 容器执行。**禁止**在 `routers/ws.py` / `harness.py` 里 `time.sleep` 评测、同步调用 `benchmark.run` / `rag.evaluate` / `testcase.generate` / `stress.run`、或轮询等到任务终态。
5. **能力未启用**：抛 `AppError(ErrorCode.VALIDATION, ...)`，HTTP **400**。禁止用 409 表示「功能没做」。LightRAG 已接入真实引擎（V2.9，引擎不可用时文档状态记 `failed`）；`kind=rag` **不得** mock `succeeded`，真实本地关键词兜底执行允许，但报告**必须**以 `degraded`/`engine_counts` 标注引擎来源（V1.3），禁止无标注把兜底成绩当作 LightRAG 引擎结果。

### 5.2.1 异常处理与控制台追踪（冻结）

业务失败一律 `raise AppError`。外层只把 `AppError` 转成 REST JSON 或 WS `error` 事件。**禁止** `except Exception` 后把 `str(exc)`、traceback、SQL、上游原文发给浏览器。

内部函数（短工具、LLM、校验）冻结写法：

```python
from app.errors import AppError, ErrorCode
from app.agent.log import agent_trace

try:
    ...
except AppError:
    raise
except Exception as exc:
    agent_trace(f"内部异常 type={type(exc).__name__}")
    raise AppError(ErrorCode.INTERNAL, "操作失败") from exc
```

WebSocket 分发冻结写法：

```python
try:
    await _handle_user_message(...)
except AppError as exc:
    agent_trace(f"user_message AppError code={exc.code.value}")
    await _emit(
        db, ws, session_id, "error",
        {"code": exc.code.value, "message": exc.message},
        state=state,
    )
```

控制台：`agent_trace("...")` 打到 stderr（`[agent] ...`），Docker logs 可见。只打协议名、模型名、耗时、工具名、错误码，**禁止**打印 API Key、Cookie、密码、完整提示词。Worker 用 `print(..., flush=True)` 的 `[worker] start/succeeded/failed` 同样不得带密钥。

未配置 Agent 协议档、上游 4xx/5xx、超时分别归一为 `VALIDATION` / `UPSTREAM` / `TIMEOUT`，与 `llm.py` 现实现一致。

### 5.3 前端规范 (Vue 3 / TypeScript / Naive UI)
1. **统一架构**：采用 `<script setup lang="ts">` + `naive-ui`，严格遵循薄荷绿/深空蓝设计令牌 (`naive-theme.ts`)。
2. **通信与重连**：API 使用相对路径 `/api/*`；WS 使用相对路径 `/ws/agent?ticket=${ticket}`，支持断线按 `last_event_id` 自动补发事件流。关闭码 `4401` 重新领票，`4404` 视为会话不存在。
3. **确认卡默认值** 与 API.md §5 / PRD 5.2.2 同一份，禁止前端另备 sample_size=20 等第二套默认；后端侧默认值唯一来源在 `backend/api/app/agent/defaults.py`，前后端各存一份，改默认值必须双端同步（H2 批次 2 起混合引擎开启时 Workflow W5 恢复确认卡产出，默认关闭时不产出；双端同步约定持续有效）。
4. ContextMeter 只读 `GET /api/sessions/{id}/messages` 的 `context_meter`；骨架化后斜杠命令已整体移除，前端不再请求 `/api/slash-commands`。

---

## 6. AI Agent 行为准则 (AI Guardrails)

### 🔴 六大核心红线（绝对禁止）
1. **禁止私自扩充产品范围**（如外部 MCP、自定义系统提示词、多租户等）；新 REST/WS 字段必须先改 API.md；
2. **禁止破坏统一错误契约**（必须归一化为 10 大 `ErrorCode`；未启用能力用 `VALIDATION` 400，不用 409）；
3. **禁止明文暴露敏感凭据**（API Key、密码、JWT Secret 严禁打印、回显或写入 `agent_trace`）；
4. **禁止跳过 Alembic 手动改库**（改 Model 必须配 Migration）；
5. **禁止全量无意义重写**（必须局部替换，保留已有注释与架构）。
6. **禁止在 `main` 上开发模块**（必须按 §3.1 开 `feat/` `fix/` `docs/` 分支，经 PR 合入）。

额外（Agent / Worker）：
- 禁止在 WS 收包循环里 `await` 整轮 Harness；禁止在 api 进程跑完长 MCP；
- 禁止 LightRAG 未接入时把 RAG 任务 mock 成成功；真实本地关键词兜底必须经报告 `degraded`/`engine_counts` 标注后方可出报告；
- 禁止 `except Exception` 后把异常原文或堆栈发给浏览器。
- **bash 必须走 bwrap 沙箱**（`sandbox.py`），禁止降级为裸 subprocess 或绕过沙箱执行命令（V1.2 红线）。

### 🟢 推荐操作五步法
1. **先查后改、先开分支**：查阅 PRD、API.md、Agent 开发文档；从 `origin/main` 拉出 `<type>/<scope>-简述` 再写代码；
2. **中文注释**：编写规范的中文 docstring 与代码注释；
3. **本地先构建与自检**：代码提交前执行 §2.1 的门禁命令；纯说明文档与部署配置按 §3.2 的例外验证，禁止为纯说明文档运行应用构建；
4. **规范中文提交**：严格采用 `<type>(<scope>): <中文描述>` 格式在**功能分支**上原子化提交；需要评审时可开 PR，但 PR 不运行 GitHub Actions；
5. **监控部署**：`push main` 后关注 GitHub Actions CI/CD 流水线，异常时按 SOP 处置。
