# agent-eval：Agent 用例生成自动化全量测试

对「需求 → 用例」这条主链路做**黑盒全量回归 + 输出质量评测**：只通过 REST API 与
容器内协议档环境文件驱动，不改业务代码，不依赖前端。

## 1. 它测什么

| 套件 | 名称 | 依赖真实模型 | 关注点 |
| :-- | :-- | :--: | :-- |
| `env` | 环境与契约 | 否 | 健康检查、鉴权、错误体一致性、专家与协议档可用性 |
| `gen` | AI 候选生成链路 | 否（本地假模型） | 正常生成、围栏/非 JSON/空数组/超配额/重复/缺字段、参数校验、prompt 契约、覆盖检查、行级补全 |
| `case` | 用例集生命周期 | 否 | 候选入库、revision 并发冲突、确认、已确认不可改、空集确认、废弃 |
| `task` | 任务端到端 | 是（Worker 侧） | 入队 → Worker 执行 → 草稿落库 + 72h 窗口 → 确认 → 任务 succeeded |
| `quality` | 输出质量评测 | 是 | 7 篇需求语料 × 七维度规则评分（覆盖/追溯/可执行/具体性/策略/去重/字段） |

失败按 P0（阻断）/ P1（严重）/ P2（一般）分级，报告输出到 `reports/<时间戳>/`。

## 2. 快速开始

```bash
cd tools/agent-eval
python3 -m venv .venv && ./.venv/bin/pip install requests   # 一次性
export AE_PASSWORD='admin 口令'

# 离线可跑（假模型，不烧额度）：环境 + 生成链路 + 生命周期
./.venv/bin/python run.py --suites env,gen,case

# 全量（含真实模型质量评测）
./.venv/bin/python run.py --suites env,gen,case,task,quality
```

产物：

```
reports/20261102-112300/
├── report.md      # 缺陷清单 + 用例明细 + 质量评分表，可直接贴 issue
└── results.json   # 机器可读，供 CI 断言
```

退出码：0 全部通过；1 存在失败/异常；2 环境不可用（登录失败、无协议档等）。

## 3. 假模型（stub）是怎么接进去的

`agent_eval/stub_model.py` 起一个 OpenAI 兼容服务（默认 `0.0.0.0:18080`），
按 prompt 里的 `[[stub:<mode>]]` 标记返回不同形态的输出：

| mode | 模拟场景 |
| :-- | :-- |
| `normal` / `fenced` | 正常 JSON / 带 ```json 围栏 |
| `malformed` / `empty` | 非 JSON / 空数组 |
| `overquota` / `duplicate` / `neardupe` | 2 倍条数 / 完全重复 / 近似重复 |
| `missing` / `noname` | 缺 expected+steps / 缺用例名称 |
| `upstream500` | 上游 5xx |
| `coverage` / `fill` / `chat` | 覆盖检查 / 行级补全 / 普通对话 |

接入方式是临时改写协议档环境变量，退出时**逐字节还原**：

```
AI_PROFILE_<PROFILE_ID>_BASE_URL=http://<宿主机容器网关>:18080/v1
AI_PROFILE_<PROFILE_ID>_MODEL=stub-model
AI_PROFILE_<PROFILE_ID>_API_KEY=stub-key
```

> **注意 Docker 单文件 bind mount 的 inode 陷阱**：容器启动时固定的是当时的
> inode。若 `.env` 之后被「写新文件 + rename」方式替换，宿主机改动对运行中的容器
> **不可见**（`docker exec cat /run/config/.env` 与宿主机 `cat .env` 内容不一致）。
> 因此默认走 `--env-container auto`（自动探测 api 容器，改容器内那份文件），
> 而不是改宿主机 `.env`。需要改宿主机文件时用 `--env-container none`。

Worker 容器的 `/run/config/.env` 是只读挂载，无法临时改写，所以 `task` 套件
始终使用 Worker 侧真实协议档——这也顺带验证了真实的 Worker 生成链路。

## 4. 质量评分（`grader.py`）

七个维度加权 100 分，低于 70 判失败：

| 维度 | 权重 | 判定口径 |
| :-- | --: | :-- |
| schema | 20% | 十字段完整度；出现 `id/case_set_id` 等保留字段扣分 |
| coverage | 20% | 夹具声明的需求点被候选覆盖的比例（中文二元组近似匹配） |
| trace | 15% | 用例文本能否在需求中找到依据（防模型编造需求规则） |
| action | 20% | steps 有编号且 ≥2 步；expected 含可观察断言（提示/返回/跳转/状态…） |
| specific | 10% | 拒绝「正常/成功」式空断言；模糊需求须标 `待澄清` 且允许 expected 留空 |
| strategy | 10% | 六策略分布与请求配比的 L1 距离 |
| dedupe | 5% | 名称+功能点近似重复对 |

硬伤封顶：追溯率 < 50% 或覆盖率 < 50% → 最高 59 分；字段完整度 < 85% → 最高 69 分。

`ambiguous` 夹具专门验证「需求没写清楚时会不会编预期结果」——正确行为是
`expected` 留空 + `test_type=待澄清`，而不是编一个「搜索成功」。

## 5. 上游直连诊断

质量套件出现 `502 模型输出无法解析为用例` 时，用诊断脚本区分「模型乱写」与
「输出被截断」：

```bash
./.venv/bin/python diagnose_upstream.py --fixture complex-batch --repeat 3
```

它用**同一套 prompt** 直连模型，打印 `finish_reason`、`content/reasoning` 字符数、
解析是否成功和 usage 明细。典型结论形如：

```
{"finish": "length", "content_chars": 0, "reasoning_chars": 8192,
 "reasoning_tokens": 8192, "text_tokens": 0, "parse_ok": false}
```

即推理模型的思维链把 `max_tokens` 全部吃掉，正文为空——这是平台侧的预算缺陷，
不是模型偶发。

## 6. 目录结构

```
tools/agent-eval/
├── run.py                  # CLI 编排：登录 → stub → 套件 → 报告
├── diagnose_upstream.py    # 上游直连诊断（定位 502/截断）
├── agent_eval/
│   ├── core.py             # Check/Recorder + Cookie REST 客户端 + 断言
│   ├── suites.py           # env / gen / case / task 四个套件
│   ├── quality.py          # 质量套件
│   ├── grader.py           # 七维度评分器
│   ├── fixtures.py         # 7 篇需求语料 + 期望覆盖点
│   ├── stub_model.py       # OpenAI 兼容假模型
│   ├── envfile.py          # 协议档环境变量临时改写/还原
│   └── report.py           # Markdown / JSON 报告
└── reports/                # 产物（不进 git）
```

## 7. 已知限制

- 鉴权使用 Cookie 登录，仅支持单账号；跨角色越权（RBAC）未覆盖。
- `quality` 的结果受模型随机性影响，建议固定夹具 + 多次取均值再卡阈值。
- 报告里的 `case` 套件会在环境中留下 `agent-eval-*` 命名的用例集（确认态不可删），
  生产环境跑测建议使用独立的 `qa-test` 账号。
