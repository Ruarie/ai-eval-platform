<template>
  <div class="dispatch-page" data-od-id="dispatch-page">
    <!-- ═══ 1. 调度大盘 KPI 趋势带（数字滚动 + 迷你趋势线 + 发光描边） ═══ -->
    <DispatchKpiBand
      :ready="overviewReady"
      :online="onlineDisplay"
      :total-workers="totalWorkers"
      :queue="queueDisplay"
      :running="runningDisplay"
      :cost="costDisplay"
      :assigned="assignedDisplay"
      :hist-queue="histQueue"
      :hist-running="histRunning"
      :hist-cost="histCost"
      :hist-assigned="histAssigned"
    />
    <!-- ═══ 2. 沉浸式大星图与悬浮控制坞 (Immersive Star Constellation & Floating Glass Docks) ═══ -->
    <div
      class="panel glow immersive-monitor-panel mb16"
      data-od-id="dispatch-canvas"
      style="--glow-c: var(--c-agent)"
    >
      <!-- 顶栏快速操作与视口控制条 -->
      <div class="row-between mb12" style="flex-wrap: wrap; gap: 8px">
        <div class="panel-title" style="margin: 0">
          调度编排星图
          <span class="small tertiary mono" style="font-weight: 400">内核 → 技能 Agent → Worker · 实时拓扑</span>
        </div>
        <div class="row" style="gap: 6px; align-items: center">
          <span class="tag-soft">历史任务调度</span>
          <span class="zoom-ctrl">
            <button class="zoom-btn" title="缩小" @click="zoomBy(0.85)">−</button>
            <button class="zoom-btn mono" title="重置视图（双击画布同效）" @click="resetView">{{ Math.round(view.k * 100) }}%</button>
            <button class="zoom-btn" title="放大" @click="zoomBy(1.18)">+</button>
          </span>
          <button class="btn btn-secondary btn-sm" style="font-size: 11px" @click="resetView">⊡ 居中</button>
        </div>
      </div>

      <!-- 全画幅主视口容器 -->
      <div ref="wrapRef" class="immersive-topo-wrap">
        <!-- SVG 大星图 -->
        <DispatchStarMap
          ref="starMap"
          :topo="topo"
          :cx="CX" :cy="CY" :r-skill="R_SKILL" :r-worker="R_WORKER"
          :view="view" :ripples="ripples" :live-mode="liveMode" :is-running="isRunning"
          :focused-skill="focusedSkill" :flash-task-id="flashTaskId"
          :pinned-task-id="pinnedTask?.id || null"
          :kind-color="(k: string) => kindColor(k as TaskKind)" :status-label="(v: string) => statusLabel(v)" :truncate="(t: string, n: number) => trunc(t, n)"
          :on-node-click="onNodeClick"
          :on-pointer-down="onPointerDown" :on-pointer-move="onPointerMove"
          :on-pointer-up="onPointerUp" :on-bg-click="onBgClick" :on-reset-view="resetView"
          @task-hover="(e: MouseEvent, t: any) => showTaskTip(e, t as TaskNode)" @skill-hover="(e: MouseEvent, v: any) => showSkillTip(e, v)" @worker-hover="(e: MouseEvent, v: any) => showWorkerTip(e, v as WorkerNode)"
          @tip-leave="hideTip"
          @task-click="(t: any) => pinTask(t as TaskNode)" @skill-click="(k: string) => toggleFocus(k as TaskKind)" @worker-click="(v: any) => openWorkerModal(v as WorkerNode)"
        />
        <!-- ═══ 左侧悬浮控制坞 (可收折) ═══ -->
        <DispatchControlDock
          :collapsed="isLeftDockCollapsed"
          :overview-ready="overviewReady"
          :is-running="isRunning"
          :strategy="strategy"
          :capacity="capacity"
          :scheduler-busy="schedulerBusy"
          :workers="workerPool.slice(0, 4)"
          :online-count="onlineCount"
          :total-workers="totalWorkers"
          :running-count="runningDisplay"
          :heartbeat-ms="heartbeatMs"
          :kernel-state-label="kernelStateLabel"
          :advice="currentAiAdvice"
          :state-label="(s: string) => stateLabel(s)"
          @update:collapsed="isLeftDockCollapsed = $event"
          @capacity-change="onCapacityChange"
          @strategy-change="handleStrategyChange"
          @toggle-scheduler="toggleScheduler"
          @register-worker="showRegisterModal = true"
          @open-worker="(w: any) => openWorkerModal(w as WorkerNode)"
          @next-advice="nextAiAdvice"
          @apply-advice="applyAiAdvice"
        />
        <!-- ═══ 右侧悬浮审计坞 (可收折) ═══ -->
        <DispatchAuditDock
          :collapsed="isRightDockCollapsed"
          :categories="logCats"
          :category="logCat"
          :logs="filteredLogs"
          @update:collapsed="isRightDockCollapsed = $event"
          @update:category="setLogCategory"
          @clear="logs = []"
          @flash-task="flashTask"
        />
        <!-- ═══ 底部悬浮甘特图抽屉 (可展开/收起) ═══ -->
        <DispatchGanttDrawer
          :collapsed="isBottomDockCollapsed"
          :rows="ganttRows"
          :legend="ganttLegend"
          :ticks="ganttTicks"
          :status-label="(v: string) => statusLabel(v)"
          :fmt-time="(v: number) => fmtTime(v)"
          @update:collapsed="isBottomDockCollapsed = $event"
          @open-task="goToTaskDetail"
        />
        <DispatchOverlays
          :tooltip="tooltip"
          :pinned-task="pinnedTask"
          :pinned-pos="pinnedPos"
          :kind-color="(k: string) => kindColor(k as TaskKind)"
          :status-label="(v: string) => statusLabel(v)"
          @unpin="unpinTask"
          @open-task="goToTaskDetail"
          @open-report="goToReport"
        />
        <!-- 扫描线装饰 -->
        <div class="scanline" aria-hidden="true"></div>
      </div>

      <!-- 图例 -->
      <div class="row mt12" style="gap: 14px; font-size: 11px; flex-wrap: wrap">
        <span class="row" style="gap: 5px; align-items: center"><i class="legend-line" style="background: repeating-linear-gradient(90deg, var(--text-tertiary) 0 3px, transparent 3px 7px)"></i><span class="tertiary">内核编排链路</span></span>
        <span class="row" style="gap: 5px; align-items: center"><i class="legend-line" style="background: var(--accent-ai)"></i><span class="tertiary">执行分发链路</span></span>
        <span class="row" style="gap: 5px; align-items: center"><i class="legend-dot" style="background: var(--accent-ai)"></i><span class="tertiary">数据流粒子</span></span>
        <span class="row" style="gap: 5px; align-items: center"><i class="legend-dot" style="background: var(--accent-success)"></i><span class="tertiary">完成涟漪</span></span>
        <span class="tertiary" style="margin-left: auto">滚轮缩放 · 拖拽平移 · 双击复位 · 浮窗面板可折叠</span>
      </div>
      <div v-if="liveMode && (topo.queueOverflow || topo.runningOverflow || topo.awaitingOverflow)" class="small tertiary mt8">
        星图仅展示代表任务；未显示：排队 {{ topo.queueOverflow }}、运行中 {{ topo.runningOverflow }}、待确认 {{ topo.awaitingOverflow }}。
      </div>
    </div>

    <!-- 节点治理弹窗 -->
    <n-modal
      v-model:show="showWorkerModal"
      preset="card"
      :title="`Worker 节点详情 · ${selectedWorker?.id} (${selectedWorker?.name || 'Worker Node'})`"
      style="width: 580px"
    >
      <div v-if="selectedWorker">
        <div class="form-row mb12">
          <div class="field">
            <span class="field-label">节点状态</span>
            <select v-model="selectedWorker.state" class="select">
              <option value="idle">在线空闲 (IDLE)</option>
              <option value="busy">执行中 (BUSY)</option>
              <option value="draining">排空下线 (DRAINING · 不接新单)</option>
              <option value="offline">离线维护 (OFFLINE)</option>
            </select>
          </div>
          <div class="field">
            <span class="field-label">调度权重 (Weight)</span>
            <input v-model.number="selectedWorker.weight" class="input num" type="number" min="10" max="500" />
          </div>
        </div>

        <div class="field">
          <span class="field-label">专精能力标签 (Capabilities，逗号分隔)</span>
          <input v-model="capsInput" class="input mono" />
          <span class="field-hint">可选能力: benchmark, judge, rag, vector, chunking, testcase, prd, openapi, stress, load, sse</span>
        </div>

        <div class="grid-2 mt12" style="gap: 8px; background: var(--bg-elevated); padding: 12px; border-radius: 8px">
          <div>
            <div class="small tertiary">当前执行任务</div>
            <div class="small font-bold" style="margin-top: 2px">{{ selectedWorker.task || '空闲待命中' }}</div>
          </div>
          <div>
            <div class="small tertiary">资源占用</div>
            <div class="small font-bold mono" style="margin-top: 2px">CPU {{ selectedWorker.load }}% · RAM {{ selectedWorker.ram }}</div>
          </div>
          <div style="margin-top: 6px">
            <div class="small tertiary">心跳周期</div>
            <div class="small font-bold" style="margin-top: 2px">
              <span v-if="selectedWorker.state === 'offline'" style="color: var(--accent-error)">丢失（心跳超时）</span>
              <span v-else style="color: var(--accent-success)">正常 · {{ heartbeatMs }}ms</span>
            </div>
          </div>
          <div style="margin-top: 6px">
            <div class="small tertiary">权重系数</div>
            <div class="small font-bold mono" style="margin-top: 2px">{{ selectedWorker.weight }}</div>
          </div>
        </div>
      </div>

      <template #footer>
        <div style="display: flex; justify-content: space-between; width: 100%">
          <button class="btn btn-secondary" @click="handleRebootWorker">重启节点</button>
          <div style="display: flex; gap: 8px">
            <button class="btn btn-secondary" @click="showWorkerModal = false">关闭</button>
            <button class="btn btn-sign" @click="handleSaveWorker">保存配置</button>
          </div>
        </div>
      </template>
    </n-modal>

    <!-- 注册 Worker 节点弹窗（对齐原型 dispatch.html：ID/名称/能力） -->
    <n-modal v-model:show="showRegisterModal" preset="card" title="注册 Worker 节点" style="width: 460px">
      <div class="field mb12">
        <span class="field-label">节点 ID <span style="color: var(--accent-error)">*</span></span>
        <input v-model="registerForm.id" class="input mono" placeholder="例如 worker-11" />
      </div>
      <div class="field mb12">
        <span class="field-label">节点名称</span>
        <input v-model="registerForm.name" class="input" placeholder="例如 GPU-Node-B1" />
      </div>
      <div class="field">
        <span class="field-label">专精能力标签（逗号分隔）</span>
        <input v-model="registerForm.caps" class="input mono" placeholder="benchmark, judge" />
        <span class="field-hint">可选能力: benchmark, judge, rag, vector, chunking, testcase, prd, openapi, stress, load, sse</span>
      </div>
      <template #footer>
        <div style="display: flex; gap: 8px; justify-content: flex-end">
          <button class="btn btn-secondary" @click="showRegisterModal = false">取消</button>
          <button class="btn btn-sign" @click="handleRegisterWorker">注册</button>
        </div>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/http'
import { usePollingLoop } from '../composables/usePollingLoop'
import { buildGanttRows, buildGanttTicks } from '../utils/dispatchGantt'
import {
  applyAssignLoad,
  applyReleaseLoad,
  computeProgress,
  createMockTask,
  isIdleLoad,
  pickTemplate,
} from '../utils/dispatchSimulation'
import {
  buildLogEntry,
  eventCategory,
  mapWorkerRow,
  mergeActiveTasks,
  pushBoundedHistory,
} from '../utils/dispatchFeed'
import { truncate } from '../utils/dispatchLayout'
import { buildTopo } from '../utils/dispatchTopo'
import DispatchKpiBand from '../components/dispatch/DispatchKpiBand.vue'
import DispatchOverlays from '../components/dispatch/DispatchOverlays.vue'
import DispatchControlDock from '../components/dispatch/DispatchControlDock.vue'
import DispatchAuditDock from '../components/dispatch/DispatchAuditDock.vue'
import DispatchStarMap from '../components/dispatch/DispatchStarMap.vue'
import type { DispatchOverview, DispatchWorker, Task, TaskKind, TaskStatus } from '../api/types'

const message = useMessage()
const router = useRouter()
const route = useRoute()
// live 模式接真实调度 API（§3.13）；mock 模式保留本地仿真演示
const liveMode = !api.isMock()

// 沉浸式大星图悬浮控制坞展开/收折状态；移动端默认收折左右浮坞，避免遮住星图
const isMobileViewport = typeof window !== 'undefined' && window.innerWidth <= 700
const isLeftDockCollapsed = ref(isMobileViewport)
const isRightDockCollapsed = ref(isMobileViewport)
const isBottomDockCollapsed = ref(isMobileViewport)

const isRunning = ref(true)
const schedulerBusy = ref(false)
const strategy = ref('负载均衡')
const capacity = ref(4)
// mock 演示计数只在演示模式预置；live 模式等 overview 返回后再展示。
const assignedToday = ref(liveMode ? 0 : 126)
const assignCosts = ref([72, 85, 94, 68, 88])
// live 模式大盘快照：KPI 与策略/容量以服务端返回为准
const overviewData = ref<DispatchOverview | null>(null)
const heartbeatMs = computed(() => overviewData.value?.heartbeat_interval_ms ?? 500)
const avgDispatchCost = computed(() => {
  if (liveMode) return overviewData.value?.avg_dispatch_cost_ms ?? 0
  if (!assignCosts.value.length) return 81
  return Math.round(assignCosts.value.reduce((a, b) => a + b, 0) / assignCosts.value.length)
})

/* ─── KPI 数字滚动（count-up）与迷你趋势线 ─── */
function useCountUp(source: { value: number }) {
  const display = ref(source.value)
  let raf = 0
  watch(
    () => source.value,
    (to) => {
      const from = display.value
      const t0 = performance.now()
      cancelAnimationFrame(raf)
      const step = (t: number) => {
        const p = Math.min(1, (t - t0) / 350)
        display.value = Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3)))
        if (p < 1) raf = requestAnimationFrame(step)
      }
      raf = requestAnimationFrame(step)
    },
  )
  // 组件卸载时取消未完成的滚动动画，避免回调写入已销毁组件的 ref。
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return display
}

// 各 KPI 历史序列（每次全量刷新追加，保留最近 24 点）
const histQueue = ref<number[]>([])
const histRunning = ref<number[]>([])
const histCost = ref<number[]>([])
const histAssigned = ref<number[]>([])

function pushHist(hist: number[], v: number) {
  pushBoundedHistory(hist, v)
}

/* ─── 星图数据模型 ─── */
interface WorkerNode {
  id: string
  name: string
  caps: string[]
  state: 'idle' | 'busy' | 'offline' | 'draining' | 'restarting'
  load: number
  ram: string
  task: string | null
  weight: number
}

// 演示节点只在 mock 模式作为初值；live 模式必须等 /api/dispatch/workers 返回，
// 避免接口失败时把 10 个虚构节点与负载当成在线集群。
const MOCK_WORKERS: WorkerNode[] = [
  { id: 'worker-01', name: 'GPU-Node-A1', caps: ['benchmark', 'judge'], state: 'busy', load: 62, ram: '4.8GB/16GB', task: 'a1f3c2 · smoke-20 v3 (shard 2/5)', weight: 100 },
  { id: 'worker-02', name: 'Vec-Node-V1', caps: ['rag', 'vector'], state: 'idle', load: 8, ram: '2.1GB/16GB', task: null, weight: 100 },
  { id: 'worker-03', name: 'Gen-Node-G1', caps: ['testcase', 'prd'], state: 'busy', load: 45, ram: '3.4GB/16GB', task: 'd4c1a9 · PRD-支付 生成用例', weight: 80 },
  { id: 'worker-04', name: 'Stress-Node-S1', caps: ['stress', 'load'], state: 'idle', load: 12, ram: '1.8GB/16GB', task: null, weight: 120 },
  { id: 'worker-05', name: 'Judge-Node-J1', caps: ['benchmark', 'prompt'], state: 'offline', load: 0, ram: '0GB/16GB', task: null, weight: 100 },
  { id: 'worker-06', name: 'Chunk-Node-C1', caps: ['rag', 'chunking'], state: 'idle', load: 5, ram: '1.2GB/16GB', task: null, weight: 80 },
  { id: 'worker-07', name: 'Stress-Node-S2', caps: ['stress', 'sse'], state: 'busy', load: 88, ram: '7.2GB/16GB', task: 'g7b3d5 · 118 QPS 流式发压', weight: 150 },
  { id: 'worker-08', name: 'Eval-Node-E1', caps: ['benchmark', 'judge'], state: 'idle', load: 18, ram: '2.6GB/16GB', task: null, weight: 100 },
  { id: 'worker-09', name: 'RAG-Node-R1', caps: ['rag', 'lightrag'], state: 'offline', load: 0, ram: '0GB/16GB', task: null, weight: 100 },
  { id: 'worker-10', name: 'Case-Node-C2', caps: ['testcase', 'openapi'], state: 'idle', load: 9, ram: '1.5GB/16GB', task: null, weight: 90 },
]
const workerPool = ref<WorkerNode[]>(liveMode ? [] : MOCK_WORKERS.map(w => ({ ...w })))

// 任务工单：统一 mock 仿真项与 live 任务的星图展示模型
interface TaskNode {
  id: string
  shortId: string
  kind: TaskKind
  label: string
  status: TaskStatus
  progress: number | null
  workerId: string | null
  parentId: string | null
}

// mock 队列项扩展：分配后携带 workerId / 进度 / 开始时间，驱动飞行连线与甘特
interface QueueItem {
  qid: string
  kind: TaskKind
  label: string
  prio: string
  workerId?: string | null
  progress?: number
  startedAt?: number
  parentId?: string | null
}

// live 模式队列由 /api/tasks 分页结果驱动，初始不得预置演示工单。
const MOCK_QUEUE: QueueItem[] = [
  { qid: 'q-101', kind: 'benchmark', label: '2 模型 × 数据集 smoke-20 v3 · shard 3/5', prio: 'P0' },
  { qid: 'q-102', kind: 'rag', label: '知识库 default · 黄金 QA qa-v1 · hybrid 回归', prio: 'P1' },
  { qid: 'q-103', kind: 'stress', label: '派生压测 · env=test · 10 QPS', prio: 'P2', parentId: 'q-101' },
]
const queue = ref<QueueItem[]>(liveMode ? [] : MOCK_QUEUE.map(q => ({ ...q })))

// live 模式：活跃任务（queued/running/awaiting_case_confirm）与近期任务（甘特）
const liveActiveTasks = ref<Task[]>([])
const liveRecentTasks = ref<Task[]>([])
const liveRunningTotal = ref(0)
const liveAwaitingTotal = ref(0)
// live 模式任务→节点映射：由 assigned 事件维护，终态事件解除
const taskWorkerMap = ref<Record<string, string>>({})

/** 任务业务上下文标签：基准=模型×数据集；RAG=知识库×黄金QA×模式；用例=PRD 来源；压测=父任务+env/QPS */
function taskLabel(t: Task): string {
  const cfg = t.config || {}
  if (t.kind === 'benchmark') {
    const models = cfg.profile_ids?.length ? `${cfg.profile_ids.length} 模型` : ''
    const ds = cfg.dataset_id ? `数据集 ${cfg.dataset_id}` : ''
    return [models, ds].filter(Boolean).join(' × ') || 'Benchmark 基准评测'
  }
  if (t.kind === 'rag') {
    const kb = cfg.kb_id ? `知识库 ${cfg.kb_id}` : 'RAG 质量评测'
    const qa = cfg.gold_qa_id ? `黄金 QA ${cfg.gold_qa_id}` : ''
    const modes = cfg.rag_mode?.length ? cfg.rag_mode.join('/') : ''
    return [kb, qa, modes].filter(Boolean).join(' · ')
  }
  if (t.kind === 'testcase') {
    if (cfg.case_source?.text) return 'PRD 文本生成用例（6 大策略配比）'
    if (cfg.case_source?.file_id) return `文件 ${cfg.case_source.file_id} 生成用例`
    return 'PRD 用例生成'
  }
  const parent = cfg.parent_task_id || t.parent_task_id ? `派生自 ${String(cfg.parent_task_id || t.parent_task_id).substring(0, 8)}` : ''
  const env = cfg.stress?.env ? `env=${cfg.stress.env}` : ''
  const qps = cfg.stress?.qps ? `${cfg.stress.qps} QPS` : ''
  return [parent, env, qps].filter(Boolean).join(' · ') || '共享压测'
}

/** live 任务 → 星图工单；workerId 优先取事件映射，兜底用节点 current_task 短号前缀匹配 */
function mapLiveTask(t: Task): TaskNode {
  const short = t.id.substring(0, 6)
  let workerId = taskWorkerMap.value[t.id] || null
  if (!workerId && t.status === 'running') {
    const w = workerPool.value.find(x => x.task && x.task.includes(short))
    workerId = w?.id || null
  }
  const pct = t.progress
    ? Math.round(t.progress.percent ?? (t.progress.total ? (t.progress.done / t.progress.total) * 100 : 0))
    : null
  return {
    id: t.id,
    shortId: t.id.substring(0, 8),
    kind: t.kind,
    label: taskLabel(t),
    status: t.status,
    progress: pct,
    workerId,
    parentId: t.parent_task_id || t.config?.parent_task_id || null,
  }
}

// 统一任务工单：live 取服务端活跃任务；mock 由仿真队列合成
const taskNodes = computed<TaskNode[]>(() => {
  if (liveMode) return liveActiveTasks.value.map(mapLiveTask)
  return queue.value.map(q => ({
    id: q.qid,
    shortId: q.qid,
    kind: q.kind,
    label: q.label,
    status: q.workerId ? 'running' as TaskStatus : 'queued' as TaskStatus,
    progress: q.workerId ? Math.round(q.progress ?? 0) : null,
    workerId: q.workerId || null,
    parentId: q.parentId || null,
  }))
})

/* ─── 星图几何：中心内核 + 技能内环 + Worker 业务扇区外环 ─── */
const VB_W = 1200
const VB_H = 680
const CX = 600
const CY = 330
const R_QUEUE = 96    // 排队工单环绕内核的轨道半径
const R_SKILL = 152   // 技能 Agent 内环半径
const R_WORKER = 258  // Worker 外环半径
const MAX_QUEUE_CHIPS = 8 // 队列轨道最多平铺的工单数，溢出以 +N 提示

// 四大业务技能域（PRD §5.5.2）：角度采用屏幕坐标系（y 轴向下，90° 为正下方）
const SKILL_DEFS = [
  { kind: 'benchmark' as TaskKind, name: 'Benchmark', fullName: 'Benchmark 基准评测', icon: '📊', color: 'var(--c-datasets)', angle: -90, desc: '模型评测 · 数据集 · 先评后压' },
  { kind: 'rag' as TaskKind, name: 'RAG', fullName: 'RAG 质量评估', icon: '🔍', color: 'var(--c-kb)', angle: 0, desc: '知识库 · 黄金 QA · 4 模式检索' },
  { kind: 'stress' as TaskKind, name: 'Stress', fullName: '共享压测', icon: '⚡', color: 'var(--c-stress)', angle: 90, desc: '继承父任务 · SLA 拐点定位' },
  { kind: 'testcase' as TaskKind, name: 'Testcase', fullName: '用例生成', icon: '🧩', color: 'var(--c-cases)', angle: 180, desc: 'PRD/OpenAPI · 6 大策略配比' },
]

/** 业务标识色（工单芯片左侧色条） */
function kindColor(kind: TaskKind): string {
  const def = SKILL_DEFS.find(s => s.kind === kind)
  return def ? def.color : 'var(--text-tertiary)'
}

/** 文本截断：星图芯片宽度有限，超长标签省略号收尾。 */
function trunc(s: string, n: number): string {
  return truncate(s, n)
}

// 星图布局：技能节点坐标 / Worker 扇区坐标 / 工单芯片坐标 / 执行链路路径，全部由数据驱动
const topo = computed(() => buildTopo<(typeof SKILL_DEFS)[number], WorkerNode, TaskNode>(
  {
    skills: SKILL_DEFS,
    workers: workerPool.value,
    tasks: taskNodes.value,
    liveMode,
    maxQueueChips: MAX_QUEUE_CHIPS,
    geometry: { cx: CX, cy: CY, rSkill: R_SKILL, rWorker: R_WORKER, rQueue: R_QUEUE },
  },
  {
    queue: queueDepth.value,
    running: liveRunningTotal.value,
    awaiting: liveAwaitingTotal.value,
  },
))

const onlineCount = computed(() =>
  liveMode && overviewData.value
    ? overviewData.value.online_workers
    : workerPool.value.filter(w => w.state !== 'offline').length,
)
const totalWorkers = computed(() =>
  liveMode && overviewData.value ? overviewData.value.total_workers : workerPool.value.length,
)
const queueDepth = computed(() =>
  liveMode && overviewData.value ? overviewData.value.queue_depth : queue.value.filter(q => !q.workerId).length,
)
const runningCount = computed(() => liveMode ? liveRunningTotal.value : taskNodes.value.filter(t => t.status === 'running').length)
const assignedTodayNum = computed(() =>
  liveMode && overviewData.value ? overviewData.value.assigned_today : assignedToday.value,
)
// live 模式在 overview 首次返回前没有任何真实大盘数据，KPI 必须显示占位符而不是 0/演示值。
const overviewReady = computed(() => !liveMode || overviewData.value !== null)
// live 模式的暂停/恢复能力未在 API 契约中定义，徽标只表达"实时接入"，不宣称可控制调度器。
const kernelStateLabel = computed(() => (isRunning.value ? (liveMode ? '实时接入' : '调度中') : '已暂停'))

// KPI 数字滚动显示值
const onlineDisplay = useCountUp(onlineCount)
const queueDisplay = useCountUp(queueDepth)
const runningDisplay = useCountUp(runningCount)
const costDisplay = useCountUp(avgDispatchCost)
const assignedDisplay = useCountUp(assignedTodayNum)

/* ─── 星图视图变换：滚轮缩放（以光标为中心）+ 拖拽平移 + 双击复位 ─── */
const starMap = ref<{ el: SVGSVGElement | null } | null>(null)
/** 星图 svg 元素由子组件暴露，滚轮缩放仍挂在真实节点上。 */
const svgRef = computed(() => starMap.value?.el ?? null)
const wrapRef = ref<HTMLDivElement | null>(null)
const view = ref({ x: 0, y: 0, k: 1 })

/** 屏幕坐标 → viewBox 坐标换算（依赖容器实际渲染尺寸） */
function toViewBox(e: { clientX: number; clientY: number }): { x: number; y: number } {
  const rect = svgRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return { x: ((e.clientX - rect.left) / rect.width) * VB_W, y: ((e.clientY - rect.top) / rect.height) * VB_H }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const s = toViewBox(e)
  const k0 = view.value.k
  const k1 = Math.min(2.2, Math.max(0.55, k0 * (e.deltaY < 0 ? 1.12 : 0.89)))
  // 保持光标下的内容点不动：p = (s - view) / k0，缩放后 view' = s - k1 * p
  const px = (s.x - view.value.x) / k0
  const py = (s.y - view.value.y) / k0
  view.value = { k: k1, x: s.x - k1 * px, y: s.y - k1 * py }
}

/** 按钮缩放：以画布中心为基准点 */
function zoomBy(factor: number) {
  const k1 = Math.min(2.2, Math.max(0.55, view.value.k * factor))
  const px = (VB_W / 2 - view.value.x) / view.value.k
  const py = (VB_H / 2 - view.value.y) / view.value.k
  view.value = { k: k1, x: VB_W / 2 - k1 * px, y: VB_H / 2 - k1 * py }
}

/** 复位视图并清除扇区聚焦 */
function resetView() {
  view.value = { x: 0, y: 0, k: 1 }
  focusedSkill.value = null
}

// 拖拽平移：位移超过 4px 判定为平移，抑制节点 click 触发
let panning = false
let panMoved = false
let panStart = { x: 0, y: 0 }
let viewStart = { x: 0, y: 0, k: 1 }

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return
  panning = true
  panMoved = false
  panStart = { x: e.clientX, y: e.clientY }
  viewStart = { ...view.value }
  hideTip()
}

function onPointerMove(e: PointerEvent) {
  if (!panning) return
  const dx = e.clientX - panStart.x
  const dy = e.clientY - panStart.y
  if (Math.abs(dx) + Math.abs(dy) > 4) panMoved = true
  const rect = svgRef.value?.getBoundingClientRect()
  if (!rect) return
  view.value = {
    k: viewStart.k,
    x: viewStart.x + dx * (VB_W / rect.width),
    y: viewStart.y + dy * (VB_H / rect.height),
  }
}

function onPointerUp() {
  panning = false
}

/** 节点点击守卫：拖拽平移后的抬起不触发节点动作 */
function onNodeClick(fn: () => void) {
  if (panMoved) return
  fn()
}

/* ─── 扇区聚焦：点击技能节点锁定查看本业务域，其余元素淡化为背景 ─── */
const focusedSkill = ref<string | null>(null)
function toggleFocus(kind: string) {
  focusedSkill.value = focusedSkill.value === kind ? null : kind
}

/* ─── 悬停 tooltip：Worker / 技能 / 工单 三类节点详情 ─── */
const tooltip = ref<{ x: number; y: number; title: string; lines: [string, string][] } | null>(null)

function placeTip(e: MouseEvent, title: string, lines: [string, string][]) {
  const wrap = wrapRef.value
  if (!wrap) return
  const r = wrap.getBoundingClientRect()
  tooltip.value = {
    x: Math.min(e.clientX - r.left + 14, r.width - 250),
    y: Math.max(e.clientY - r.top + 12, 8),
    title,
    lines,
  }
}

function hideTip() {
  tooltip.value = null
}

function stateLabel(s: string): string {
  const map: Record<string, string> = { idle: '在线空闲', busy: '执行中', draining: '排空下线', offline: '离线维护', restarting: '等待重启' }
  return map[s] || s
}

function showWorkerTip(e: MouseEvent, w: WorkerNode) {
  placeTip(e, `${w.id} · ${w.name}`, [
    ['状态', stateLabel(w.state)],
    ['负载', `CPU ${w.load}% · RAM ${w.ram}`],
    ['能力', w.caps.join(', ') || '—'],
    ['当前任务', w.task || '空闲待命中'],
    ['权重', String(w.weight)],
  ])
}

function showSkillTip(e: MouseEvent, s: { fullName: string; desc: string; runningCount: number; activeCount: number }) {
  placeTip(e, s.fullName, [
    ['职责', s.desc],
    [liveMode ? '可见运行中' : '运行中', `${s.runningCount} 个任务`],
    [liveMode ? '可见工单' : '活跃工单', `${s.activeCount} 个`],
    ['操作', '点击聚焦 / 取消聚焦本业务扇区'],
  ])
}

function showTaskTip(e: MouseEvent, t: TaskNode) {
  placeTip(e, `工单 ${t.shortId}`, [
    ['业务', t.label],
    ['状态', statusLabel(t.status) + (t.progress != null ? ` · ${t.progress}%` : '')],
    ['执行节点', t.workerId || '排队待分发'],
    ['操作', '点击锁定详情卡'],
  ])
}

/* ─── 工单锁定详情卡：点击芯片驻留，跟随视图变换，Esc / 点击空白解锁 ─── */
const pinnedTask = ref<TaskNode | null>(null)
// 容器渲染尺寸：SVG 坐标 → 屏幕像素换算依赖实际宽高，随窗口 resize 更新
const wrapSize = ref({ w: 0, h: 0 })

function pinTask(t: TaskNode) {
  pinnedTask.value = t
  hideTip()
}

function unpinTask() {
  pinnedTask.value = null
}

/** 背景点击解锁：仅在命中网格背景（非任何节点）且非拖拽平移后触发 */
function onBgClick(e: MouseEvent) {
  if (panMoved) return
  if ((e.target as Element)?.classList?.contains('topo-bg')) unpinTask()
}

// 锁定卡屏幕坐标：星图 SVG 坐标经 view 变换后按容器比例换算，锚定在芯片右下方
const pinnedPos = computed(() => {
  const t = pinnedTask.value
  if (!t || !wrapSize.value.w) return null
  const p = topo.value.tasks.find(x => x.t.id === t.id)
  if (!p) return null
  const sx = (view.value.x + view.value.k * p.x) * (wrapSize.value.w / VB_W)
  const sy = (view.value.y + view.value.k * p.y) * (wrapSize.value.h / VB_H)
  return {
    x: Math.max(8, Math.min(sx + 88 * view.value.k, wrapSize.value.w - 240)),
    y: Math.max(8, Math.min(sy - 10, wrapSize.value.h - 190)),
  }
})

// 锁定的工单完成/消失（离开活跃列表）时自动解锁
watch(taskNodes, (list) => {
  if (pinnedTask.value && !list.some(t => t.id === pinnedTask.value!.id)) unpinTask()
})

/** Esc 解锁锁定卡 */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') unpinTask()
}

/* ─── 调度事件流（分类过滤 + 点击定位星图工单） ─── */
interface LogItem {
  time: string
  kind: string
  cat: 'assign' | 'done' | 'error' | 'node'
  html: string
  tid?: string
}

// 演示日志只在 mock 模式出现；live 模式日志只允许来自 /api/dispatch/events。
const MOCK_LOGS: LogItem[] = [
  { time: new Date().toTimeString().slice(0, 8), kind: 'ENQUEUE', cat: 'assign', html: '<span class="la">q-101</span> 2 模型 × smoke-20 v3 · shard 3/5 (P0)', tid: 'q-101' },
  { time: new Date().toTimeString().slice(0, 8), kind: 'ASSIGN', cat: 'assign', html: '<span class="la">q-100</span> → worker-01 · 耗时 82ms', tid: 'q-100' },
]
const logs = ref<LogItem[]>(liveMode ? [] : MOCK_LOGS.map(l => ({ ...l })))

const logCat = ref<'all' | LogItem['cat']>('all')
const logCats = [
  { key: 'all' as const, label: '全部' },
  { key: 'assign' as const, label: '分配' },
  { key: 'done' as const, label: '完成' },
  { key: 'error' as const, label: '异常' },
  { key: 'node' as const, label: '节点' },
]
const filteredLogs = computed(() => (logCat.value === 'all' ? logs.value : logs.value.filter(l => l.cat === logCat.value)))

/** 事件类型归一化为展示分类 */
function eventCat(kind: string): LogItem['cat'] {
  return eventCategory(kind)
}

/** 统一日志入口：prepend 并截断至 50 条，与原型 log() 语义一致。 */
function addLog(kind: string, html: string, tid?: string) {
  logs.value.unshift(buildLogEntry(kind, html, tid))
  if (logs.value.length > 50) logs.value.pop()
}

// 点击日志定位：闪烁星图中对应任务工单
const flashTaskId = ref('')
let flashTimer = 0
/** 审计坞上报的筛选 key 是字符串，这里收敛回页面的联合类型。 */
function setLogCategory(value: string) {
  logCat.value = value as typeof logCat.value
}

function flashTask(tid: string) {
  flashTaskId.value = tid
  window.clearTimeout(flashTimer)
  flashTimer = window.setTimeout(() => { flashTaskId.value = '' }, 1600)
}

/** 前往任务中心并自动打开指定任务详情抽屉 */
function goToTaskDetail(taskId?: string) {
  if (taskId) {
    router.push({ path: '/tasks', query: { id: taskId } })
  } else {
    router.push('/tasks')
  }
}

/** 前往报告中心查看评测结果 */
function goToReport(taskId?: string) {
  if (!taskId) {
    router.push('/reports')
    return
  }
  const fullTask = liveRecentTasks.value.find(t => t.id === taskId) || liveActiveTasks.value.find(t => t.id === taskId)
  if (fullTask?.report_id) {
    router.push(`/reports/${fullTask.report_id}`)
  } else {
    // 若尚未生成 report_id，先前往任务详情抽屉查看实时进展
    router.push({ path: '/tasks', query: { id: taskId } })
  }
}

/** 处理从外部（如任务中心）传入的任务高亮聚焦参数 */
function handleRouteTaskFocus() {
  const tid = (route.query.task_id || route.query.highlight_task) as string | undefined
  if (tid) {
    const match = taskNodes.value.find(t => t.id === tid || t.shortId === tid || t.id.startsWith(tid))
    if (match) {
      pinTask(match)
      flashTask(match.id)
      focusedSkill.value = match.kind
      message.info(`已聚焦任务 ${match.shortId} 调度拓扑链路`)
    } else {
      flashTask(tid)
    }
  }
}

/* AI 建议结构化：携带建议动作（策略切换/容量调整），采纳时按内容生效（对齐原型 dispatch.html） */
interface AiAdvice {
  text: string
  strategy?: string
  cap?: number
}

const aiAdvices: AiAdvice[] = [
  { text: '当前 GPU-Node-A1 负载偏高（62%），建议切换「负载均衡」策略分流 judge 任务。', strategy: '负载均衡' },
  { text: '排队深度上升，建议将并发容量提升至 6 以消化积压任务。', cap: 6 },
  { text: '亲和性策略下 RAG 评测排队时间缩短 34%，建议持续保持该模式。', strategy: '亲和性' },
]
const aiAdviceIdx = ref(0)
const currentAiAdvice = computed(() => aiAdvices[aiAdviceIdx.value].text)

function nextAiAdvice() {
  aiAdviceIdx.value = (aiAdviceIdx.value + 1) % aiAdvices.length
}

/** 采纳建议：按建议内容切换策略/调整容量，并写入调度日志 */
function applyAiAdvice() {
  const advice = aiAdvices[aiAdviceIdx.value]
  const actions: string[] = []
  if (advice.strategy) {
    strategy.value = advice.strategy
    actions.push(`策略切换为「${advice.strategy}」`)
  }
  if (advice.cap) {
    capacity.value = advice.cap
    actions.push(`并发容量调整为 ${advice.cap}`)
  }
  if (!actions.length) actions.push('无参数变更')
  addLog('AI', `采纳调度建议：${actions.join('；')}`)
  message.success(`已采纳 AI 优化建议（${actions.join('；')}）`)
}

// 节点治理弹窗
const showWorkerModal = ref(false)
const selectedWorker = ref<WorkerNode | null>(null)
const capsInput = ref('')

function openWorkerModal(w: WorkerNode) {
  selectedWorker.value = { ...w }
  capsInput.value = (w.caps || []).join(', ')
  showWorkerModal.value = true
}

async function handleRebootWorker() {
  if (!selectedWorker.value) return
  if (liveMode) {
    try {
      await api.dispatch.restartWorker(selectedWorker.value.id)
      message.success('已请求重启。当前任务会先跑完，然后进程退出并由容器重新拉起。')
      showWorkerModal.value = false
      await loadLiveAll()
    } catch (err: any) {
      message.error(err.message || '重启请求失败')
    }
    return
  }
  const target = workerPool.value.find(w => w.id === selectedWorker.value?.id)
  if (target) {
    target.state = 'idle'
    target.load = 4
    target.task = null
  }
  addLog('NODE', `管理员重启了节点 <span class="la">${selectedWorker.value.id}</span>`)
  message.success(`节点 ${selectedWorker.value.id} 已重启完毕`)
  showWorkerModal.value = false
}

async function handleSaveWorker() {
  if (!selectedWorker.value) return
  const caps = capsInput.value.split(',').map(s => s.trim()).filter(Boolean)
  if (liveMode) {
    try {
      await api.dispatch.updateWorker(selectedWorker.value.id, {
        state: selectedWorker.value.state,
        weight: selectedWorker.value.weight,
        caps,
      })
      message.success(`已保存 ${selectedWorker.value.id} 节点配置`)
      showWorkerModal.value = false
      await loadLiveAll()
    } catch (err: any) {
      message.error(err.message || '节点配置保存失败')
    }
    return
  }
  const target = workerPool.value.find(w => w.id === selectedWorker.value?.id)
  if (target) {
    target.state = selectedWorker.value.state
    target.weight = selectedWorker.value.weight
    target.caps = caps
  }
  addLog('CONFIG', `更新节点 <span class="la">${selectedWorker.value.id}</span> 配置 · 状态=${selectedWorker.value.state} · 权重=${selectedWorker.value.weight}`)
  message.success(`已保存 ${selectedWorker.value.id} 节点配置`)
  showWorkerModal.value = false
}

/* ─── 完成涟漪：任务终态时在 Worker 节点位置扩散一圈（SVG 坐标系直取布局坐标） ─── */
const ripples = ref<{ id: number; x: number; y: number }[]>([])
let rippleSeq = 0
function addRippleAtWorker(workerId: string | null | undefined) {
  if (!workerId) return
  const pw = topo.value.workers.find(x => x.w.id === workerId)
  if (!pw) return
  const id = ++rippleSeq
  ripples.value.push({ id, x: pw.x, y: pw.y })
  // 涟漪句柄统一登记，组件卸载时清理，避免定时器继续修改已销毁状态。
  const timer = window.setTimeout(() => {
    assignTimers.delete(timer)
    ripples.value = ripples.value.filter(p => p.id !== id)
  }, 1200)
  assignTimers.add(timer)
}

/* ─── mock 调度分发循环：按策略选节点 → 工单飞向节点 → 进度推进 → 完成涟漪 + 甘特沉淀 ─── */
let enqueueSeq = 200
const QUEUE_TPL: { kind: TaskKind; label: string; prio: string; parentId?: string }[] = [
  { kind: 'benchmark', label: '2 模型 × 数据集 smoke-20 v3 · 规则评分', prio: 'P1' },
  { kind: 'rag', label: '知识库 default · 黄金 QA qa-v1 · naive/local 对比', prio: 'P1' },
  { kind: 'testcase', label: 'PRD-支付链路 用例生成（40/25/15/10/5/5）', prio: 'P2' },
  { kind: 'stress', label: '派生压测 · env=test · 10 QPS', prio: 'P2', parentId: 'q-101' },
]

// mock 甘特历史：完成的编排段沉淀于此（最近 12 条）
interface GanttRow {
  id: string
  shortId: string
  kind: TaskKind
  label: string
  status: TaskStatus
  start: number
  end: number
  parentId: string | null
  isChild: boolean
  left: number
  width: number
}
const mockGanttDone = ref<GanttRow[]>([])
// 甘特「当前时刻」游标：运行中条形随时间延展
const nowTs = ref(Date.now())

/** 按当前策略挑选可接单节点：离线/排空节点与满载（≥92%）节点不参与。 */
function pickAgent(): WorkerNode | null {
  const candidates = workerPool.value.filter(w => w.state !== 'offline' && w.state !== 'draining' && w.state !== 'restarting' && w.state !== 'busy' && w.load < 92)
  if (!candidates.length) return null
  if (strategy.value === '负载均衡') return candidates.sort((x, y) => x.load - y.load)[0]
  if (strategy.value === '优先级抢占') return candidates[Math.floor(Math.random() * candidates.length)]
  return candidates.sort((x, y) => (y.caps.length - x.caps.length) || (x.load - y.load))[0] // 亲和性
}

function enqueueMockTask() {
  const tpl = pickTemplate(QUEUE_TPL, Math.random())
  const q: QueueItem = createMockTask(enqueueSeq++, tpl) as unknown as QueueItem
  queue.value.push(q)
  addLog('ENQUEUE', `<span class="la">${q.qid}</span> ${tpl.label} (${q.prio})`, q.qid)
  const t = window.setTimeout(() => {
    assignTimers.delete(t)
    tryAssign()
  }, 600)
  assignTimers.add(t)
}

function tryAssign() {
  const waiting = queue.value.filter(q => !q.workerId)
  if (!waiting.length) return
  const busyCount = workerPool.value.filter(w => w.state === 'busy').length
  if (busyCount >= capacity.value) {
    if (Math.random() < 0.3) addLog('HOLD', `并发已满（${busyCount}/${capacity.value}），<span class="la">${waiting[0].qid}</span> 保持排队`, waiting[0].qid)
    return
  }
  const q = waiting[0]
  const agent = pickAgent()
  if (!agent) return
  const cost = 55 + Math.round(Math.random() * 70)
  assignCosts.value.push(cost)
  if (assignCosts.value.length > 12) assignCosts.value.shift()
  // 工单状态置为运行并绑定节点：星图位置由 computed 驱动，CSS transition 自动播放飞行动效
  q.workerId = agent.id
  q.progress = 0
  q.startedAt = Date.now()
  agent.state = 'busy'
  agent.load = applyAssignLoad(agent.load, Math.random())
  agent.task = q.qid + ' · ' + q.label
  assignedToday.value++
  addLog('ASSIGN', `<span class="la">${q.qid}</span> → ${agent.id} · 策略=${strategy.value} · 耗时 ${cost}ms`, q.qid)

  // 执行 4~8.5s：期间按节拍推进进度，完成后释放槽位、触发涟漪并沉淀甘特历史
  const duration = 4000 + Math.random() * 4500
  const progressTimer = window.setInterval(() => {
    if (q.startedAt) q.progress = computeProgress(q.startedAt, Date.now(), duration)
  }, 400)
  assignTimers.add(progressTimer)
  const doneTimer = window.setTimeout(() => {
    assignTimers.delete(doneTimer)
    window.clearInterval(progressTimer)
    assignTimers.delete(progressTimer)
    queue.value = queue.value.filter(x => x.qid !== q.qid)
    agent.load = applyReleaseLoad(agent.load, Math.random())
    if (isIdleLoad(agent.load)) {
      agent.state = 'idle'
      agent.task = null
    }
    addRippleAtWorker(agent.id)
    mockGanttDone.value.unshift({
      id: q.qid, shortId: q.qid, kind: q.kind, label: q.label, status: 'succeeded',
      start: q.startedAt || Date.now() - duration, end: Date.now(),
      parentId: q.parentId || null, isChild: !!q.parentId, left: 0, width: 0,
    })
    if (mockGanttDone.value.length > 12) mockGanttDone.value.pop()
    addLog('DONE', `${agent.id} 执行完成 <span class="la">${q.qid}</span>，释放并发槽位 · 负载回落至 ${agent.load}%`, q.qid)
  }, duration)
  assignTimers.add(doneTimer)
}

/** 调度主循环节拍：45% 概率自动入队新任务，其余时间尝试分发。 */
function dispatchTick() {
  if (!isRunning.value) return
  nowTs.value = Date.now()
  pushHist(histQueue.value, queueDepth.value)
  pushHist(histRunning.value, runningCount.value)
  pushHist(histCost.value, avgDispatchCost.value)
  pushHist(histAssigned.value, assignedTodayNum.value)
  const r = Math.random()
  if (r < 0.45 && queue.value.length < 5) {
    enqueueMockTask()
  } else {
    tryAssign()
  }
}

/** 暂停/恢复调度：暂停后已有任务继续执行，只停止领取新的排队任务和导入。 */
async function toggleScheduler() {
  if (liveMode) {
    schedulerBusy.value = true
    const paused = isRunning.value
    try {
      await api.dispatch.updateConfig({ paused })
      isRunning.value = !paused
      message.success(paused ? '已暂停领取新任务，正在执行的任务会继续跑完' : '已恢复领取新任务')
    } catch (err: any) {
      message.error(err.message || '调度状态更新失败')
    } finally {
      schedulerBusy.value = false
    }
    return
  }
  isRunning.value = !isRunning.value
  addLog('CONFIG', isRunning.value ? '调度器已恢复运行' : '调度器已暂停（已有任务继续执行）')
  message.info(isRunning.value ? '调度器已恢复' : '调度器已暂停（已有任务继续执行）')
}

/** 切换分发策略：live 模式即写 PUT /api/dispatch/config */
async function handleStrategyChange(s: string) {
  strategy.value = s
  if (!liveMode) return
  try {
    await api.dispatch.updateConfig({ strategy: s as '负载均衡' | '优先级抢占' | '亲和性' })
    message.success(`分发策略已切换为「${s}」`)
  } catch (err: any) {
    message.error(err.message || '策略更新失败')
  }
}

/** 调整全局并发容量：live 模式在滑块释放时落库 */
/** 子组件上报新容量：先落本地再复用原有保存流程。 */
async function onCapacityChange(value: number) {
  capacity.value = value
  await handleCapacityChange()
}

async function handleCapacityChange() {
  if (!liveMode) return
  try {
    await api.dispatch.updateConfig({ max_running_tasks: capacity.value })
    message.success(`并发容量已调整为 ${capacity.value}`)
  } catch (err: any) {
    message.error(err.message || '并发容量更新失败')
  }
}

// 注册节点弹窗
const showRegisterModal = ref(false)
const registerForm = ref({ id: '', name: '', caps: '' })

/** 注册新 Worker 节点：live 模式走 POST /api/dispatch/workers，mock 本地入池 */
async function handleRegisterWorker() {
  const id = registerForm.value.id.trim()
  if (!id) {
    message.warning('请输入节点 ID')
    return
  }
  if (workerPool.value.some(w => w.id === id)) {
    message.error(`节点 ${id} 已存在`)
    return
  }
  const caps = registerForm.value.caps.split(',').map(s => s.trim()).filter(Boolean)
  if (liveMode) {
    try {
      await api.dispatch.createWorker({ id, name: registerForm.value.name.trim() || id, caps })
      message.success(`节点 ${id} 已注册，等待首次心跳上报`)
      registerForm.value = { id: '', name: '', caps: '' }
      showRegisterModal.value = false
      await loadLiveAll()
    } catch (err: any) {
      message.error(err.message || '节点注册失败')
    }
    return
  }
  workerPool.value.push({
    id,
    name: registerForm.value.name.trim() || id,
    caps,
    state: 'idle',
    load: 2,
    ram: '0.5GB/16GB',
    task: null,
    weight: 100,
  })
  addLog('NODE', `注册新节点 <span class="la">${id}</span>，状态 IDLE 待接单`)
  message.success(`节点 ${id} 已注册`)
  registerForm.value = { id: '', name: '', caps: '' }
  showRegisterModal.value = false
}

/* ─── live 模式数据接入：大盘/节点/任务周期拉取 + 调度事件增量轮询（§3.13） ─── */
let lastEventId = 0
let pollRound = 0

/** 服务端 Worker 快照映射为星图节点模型；RAM 用量契约未提供时显示占位。 */
function mapWorker(w: DispatchWorker): WorkerNode {
  return mapWorkerRow(w as unknown as Parameters<typeof mapWorkerRow>[0]) as unknown as WorkerNode
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

let liveLoadRequestId = 0

/** 刷新大盘指标、节点池与任务域；状态总量来自分页契约，星图只取有限代表任务。 */
async function loadLiveAll() {
  const requestId = ++liveLoadRequestId
  try {
    const [ov, workers, recentPage, queuedPage, runningPage, awaitingPage] = await Promise.all([
      api.dispatch.overview(),
      api.dispatch.workers(),
      api.tasks.listPage({ limit: 12, offset: 0 }),
      api.tasks.listPage({ status: 'queued', limit: 8, offset: 0 }),
      api.tasks.listPage({ status: 'running', limit: 64, offset: 0 }),
      api.tasks.listPage({ status: 'awaiting_case_confirm', limit: 8, offset: 0 }),
    ])
    if (requestId !== liveLoadRequestId) return
    if (ov) {
      overviewData.value = ov
      strategy.value = ov.strategy
      capacity.value = ov.max_running_tasks
      isRunning.value = ov.paused !== true
    }
    if (workers) workerPool.value = workers.map(mapWorker)
    liveRunningTotal.value = runningPage.total
    liveAwaitingTotal.value = awaitingPage.total
    liveActiveTasks.value = mergeActiveTasks(queuedPage.items, runningPage.items, awaitingPage.items)
    liveRecentTasks.value = recentPage.items
    nowTs.value = Date.now()
    pushHist(histQueue.value, queueDepth.value)
    pushHist(histRunning.value, runningCount.value)
    pushHist(histCost.value, avgDispatchCost.value)
    pushHist(histAssigned.value, assignedTodayNum.value)
  } catch (err: any) {
    if (requestId !== liveLoadRequestId) return
    message.error(err.message || '调度数据加载失败')
  }
}

/** 增量拉取调度事件流：维护任务→节点映射与终态涟漪；日志只能由调度器/Worker 写入，浏览器不生成不改写。 */
async function pollLiveEvents() {
  try {
    const page = await api.dispatch.events(lastEventId || undefined)
    if (!page) return
    if (page.items.length) {
      page.items.forEach(e => {
        const ev = e.event.toLowerCase()
        // assigned 事件建立任务→节点映射，终态事件解除并在节点上触发涟漪
        if (ev === 'assigned' && e.task_id && e.worker_id) taskWorkerMap.value[e.task_id] = e.worker_id
        if (['succeeded', 'failed', 'cancelled'].includes(ev) && e.task_id) {
          addRippleAtWorker(taskWorkerMap.value[e.task_id])
          delete taskWorkerMap.value[e.task_id]
        }
      })
      const mapped = page.items.map(e => ({
        time: new Date(e.ts).toTimeString().slice(0, 8),
        kind: e.event.toUpperCase(),
        cat: eventCat(e.event),
        html: escapeHtml(e.message),
        tid: e.task_id || undefined,
      }))
      logs.value = [...mapped.reverse(), ...logs.value].slice(0, 50)
    }
    lastEventId = page.next_after_id
  } catch {
    // 事件轮询失败不打断页面，等待下一轮
  }
}

async function liveTick() {
  pollRound++
  await pollLiveEvents()
  if (pollRound % 2 === 0) await loadLiveAll()
}

/* ─── 任务编排时间线（甘特）：先评后压父子关联、运行中条形随时间延展 ─── */
const ganttLegend = [
  { label: '排队', color: '#9CA3AF' },
  { label: '运行中', color: 'var(--accent-ai)' },
  { label: '待确认', color: 'var(--accent-warning)' },
  { label: '成功', color: 'var(--accent-success)' },
  { label: '失败/取消', color: 'var(--accent-error)' },
]

// 甘特行：live 取近期任务；mock 取运行中队列项 + 已完成历史
const ganttBase = computed<Omit<GanttRow, 'left' | 'width'>[]>(() => {
  if (liveMode) {
    return liveRecentTasks.value.map(t => {
      const active = ['queued', 'running', 'awaiting_case_confirm'].includes(t.status)
      return {
        id: t.id,
        shortId: t.id.substring(0, 8),
        kind: t.kind,
        label: taskLabel(t),
        status: t.status,
        start: +new Date(t.created_at),
        end: active ? nowTs.value : +new Date(t.updated_at || t.created_at),
        parentId: t.parent_task_id || t.config?.parent_task_id || null,
        isChild: !!(t.parent_task_id || t.config?.parent_task_id),
      }
    })
  }
  const running: Omit<GanttRow, 'left' | 'width'>[] = queue.value
    .filter(q => q.workerId && q.startedAt)
    .map(q => ({
      id: q.qid, shortId: q.qid, kind: q.kind, label: q.label, status: 'running' as TaskStatus,
      start: q.startedAt!, end: nowTs.value, parentId: q.parentId || null, isChild: !!q.parentId,
    }))
  return [...running, ...mockGanttDone.value].slice(0, 12)
})

// 父子分组排序：父任务在前，派生压测紧随其后
const ganttRows = computed<GanttRow[]>(() =>
  buildGanttRows(ganttBase.value, nowTs.value) as unknown as GanttRow[],
)

// 时间轴刻度（起止 + 两个中间点）
const ganttTicks = computed(() =>
  buildGanttTicks(ganttBase.value, nowTs.value, fmtTime),
)

function fmtTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    queued: '排队',
    running: '运行中',
    awaiting_case_confirm: '待确认',
    succeeded: '已成功',
    failed: '已失败',
    cancelled: '已取消',
  }
  return map[s] || s
}

// 调度心跳
// 轮询循环：可见性暂停 + 在飞去重 + 卸载清理统一交给 usePollingLoop
const nowPoll = usePollingLoop({ intervalMs: 1000, run: () => { nowTs.value = Date.now() } })
const simLoadPoll = usePollingLoop({
  intervalMs: 2000,
  enabled: () => isRunning.value,
  run: () => {
    workerPool.value.forEach(w => {
      if (w.state === 'busy') {
        w.load = Math.max(10, Math.min(96, w.load + (Math.random() < 0.5 ? -2 : 2)))
      }
    })
  },
})
const simDispatchPoll = usePollingLoop({ intervalMs: 2600, run: () => dispatchTick() })
const livePoll = usePollingLoop({ intervalMs: 3000, run: () => liveTick() })

/** 分发模拟的延时句柄登记：组件卸载时统一清理，避免回调写入已销毁状态 */
const assignTimers = new Set<number>()
/** 刷新容器尺寸缓存：锁定卡定位换算依据 */
function syncWrapSize() {
  const el = wrapRef.value
  if (el) wrapSize.value = { w: el.clientWidth, h: el.clientHeight }
}

onMounted(async () => {
  // 滚轮缩放需 preventDefault，必须以非 passive 方式注册
  svgRef.value?.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('resize', syncWrapSize)
  window.addEventListener('keydown', onKeydown)
  syncWrapSize()
  document.addEventListener('visibilitychange', onVisibilityChange)
  // 甘特时间游标：运行中条形每秒延展；后台标签页自动暂停
  nowPoll.start()
  if (liveMode) {
    // 真实模式：首屏全量加载后按 3s 节拍轮询事件，6s 全量刷新，不启动本地仿真
    await loadLiveAll()
    await pollLiveEvents()
    handleRouteTaskFocus()
    livePoll.start()
    return
  }
  handleRouteTaskFocus()
  // 仿真模式：负载抖动 + 派单节拍
  simLoadPoll.start()
  simDispatchPoll.start()
})

/**
 * 后台标签页暂停轮询：调度页有 1s/2s/2.6s/3s 多路定时器，切到后台仍全速打接口
 * 会白白占用连接与服务端资源。回到前台立即补一轮，避免数据停留在旧值。
 */
function onVisibilityChange() {
  if (document.hidden) return
  nowTs.value = Date.now()
  if (liveMode) void liveTick()
}

// 监听路由参数变化（如由任务中心跳转过来时）
watch(() => route.query.task_id || route.query.highlight_task, () => {
  handleRouteTaskFocus()
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  nowPoll.stop()
  simLoadPoll.stop()
  simDispatchPoll.stop()
  livePoll.stop()
  assignTimers.forEach(id => { window.clearTimeout(id); window.clearInterval(id) })
  assignTimers.clear()
  window.clearTimeout(flashTimer)
  svgRef.value?.removeEventListener('wheel', onWheel)
  window.removeEventListener('resize', syncWrapSize)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
/* ═══ 沉浸式调度星图画布 ═══ */
.immersive-monitor-panel {
  overflow: hidden;
  border-radius: 14px;
}
.immersive-topo-wrap {
  position: relative;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  overflow: hidden;
  height: calc(100vh - 270px);
  min-height: 740px;
  background:
    radial-gradient(60% 55% at 50% 48%, color-mix(in srgb, var(--accent-ai) 6%, transparent), transparent 70%),
    var(--bg-elevated);
}
.scanline {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 140px;
  pointer-events: none;
  background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--accent-ai) 5%, transparent), transparent);
  animation: scan-sweep 8s linear infinite;
}
@keyframes scan-sweep {
  from { transform: translateY(-160px); }
  to { transform: translateY(1100px); }
}
.legend-line {
  display: inline-block;
  width: 18px;
  height: 2px;
  border-radius: 2px;
}
.legend-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
@media (max-width: 1024px) {
  .kpi-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
}
@media (max-width: 768px) {
  .dispatch-page {
    padding-bottom: 20px;
  }
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .immersive-topo-wrap {
    height: 62vh;
    min-height: 420px;
  }
}
@media (max-width: 640px) {
  .kpi-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }
  .immersive-topo-wrap {
    height: 56vh;
    min-height: 380px;
    border-radius: 10px;
  }
  .panel-title {
    font-size: 14px;
  }
  .panel-title .small {
    display: none;
  }
  .zoom-ctrl {
    display: none;
  }
}

</style>
