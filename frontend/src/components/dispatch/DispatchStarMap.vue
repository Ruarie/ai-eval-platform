<template>
  <svg
    ref="svgEl"
    class="topo-svg"
            viewBox="0 0 1200 760"
            preserveAspectRatio="xMidYMid meet"
    @pointerdown="props.onPointerDown"
    @pointermove="props.onPointerMove"
    @pointerup="props.onPointerUp"
    @pointerleave="props.onPointerUp"
    @dblclick="props.onResetView"
    @click="props.onBgClick"
          >
            <defs>
              <pattern id="topo-grid" width="28" height="28" patternUnits="userSpaceOnUse">
                <path d="M 28 0 L 0 0 0 28" class="grid-line" />
              </pattern>
              <radialGradient id="core-glow">
                <stop offset="0%" stop-color="var(--accent-ai)" stop-opacity="0.25" />
                <stop offset="100%" stop-color="var(--accent-ai)" stop-opacity="0" />
              </radialGradient>
              <linearGradient id="sweep-grad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stop-color="var(--accent-ai)" stop-opacity="0.35" />
                <stop offset="100%" stop-color="var(--accent-ai)" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- 可拖拽背景 -->
            <rect x="-2000" y="-2000" width="5200" height="5200" fill="url(#topo-grid)" class="topo-bg" />

            <g :transform="`translate(${props.view.x} ${props.view.y}) scale(${props.view.k})`">
              <!-- 业务扇区底色楔块 -->
              <path
                v-for="s in topo.sectors"
                :key="'wedge-' + s.kind"
                class="sector-wedge"
                :class="{ dim: focusedSkill && focusedSkill !== s.kind }"
                :d="s.wedge"
                :fill="s.color"
              />

              <!-- 轨道参考线 -->
              <circle :cx="props.cx" :cy="props.cy" :r="props.rSkill" class="orbit-guide" />
              <circle :cx="props.cx" :cy="props.cy" :r="props.rWorker" class="orbit-guide outer" />

              <!-- 常驻链路：内核 → 技能 -->
              <path
                v-for="s in topo.skills"
                :key="'core-' + s.kind"
                class="wire-core"
                :class="{ dim: focusedSkill && focusedSkill !== s.kind }"
                :d="`M ${props.cx} ${props.cy} L ${s.x} ${s.y}`"
              />

              <!-- 归属链路：技能 → Worker -->
              <path
                v-for="pw in topo.workers"
                :key="'mem-' + pw.w.id"
                class="wire-member"
                :class="{ dim: focusedSkill && focusedSkill !== pw.skillKind }"
                :d="`M ${pw.sx} ${pw.sy} L ${pw.x} ${pw.y}`"
              />

              <!-- 执行链路：高亮流动 + 粒子 -->
              <template v-for="w in topo.liveWires" :key="w.key">
                <path class="wire-live" :class="{ dim: focusedSkill && focusedSkill !== w.skillKind }" :d="w.d" />
                <circle class="particle" r="3">
                  <animateMotion :path="w.d" dur="1.9s" repeatCount="indefinite" />
                </circle>
                <circle class="particle" r="2" opacity="0.55">
                  <animateMotion :path="w.d" dur="1.9s" begin="-0.95s" repeatCount="indefinite" />
                </circle>
              </template>

              <!-- 任务完成涟漪 -->
              <circle v-for="r in props.ripples" :key="r.id" class="ripple-c" :cx="r.x" :cy="r.y" r="10" />

              <!-- 任务工单芯片 -->
              <g
                v-for="p in topo.tasks"
                :key="p.t.id"
                class="task-chip"
                :class="[p.t.status, { flash: flashTaskId === p.t.id || flashTaskId === p.t.shortId, dim: focusedSkill && focusedSkill !== p.t.kind, pinned: pinnedTaskId === p.t.id }]"
                :style="{ transform: `translate(${p.x}px, ${p.y}px)` }"
                @mouseenter="emit('task-hover', $event, p.t)"
                @mouseleave="emit('tip-leave')"
                @click="onNodeClick(() => emit('task-click', p.t))"
              >
                <rect x="-76" y="-19" width="152" height="38" rx="9" class="tc-box" />
                <rect x="-76" y="-19" width="3.5" height="38" class="tc-bar" :fill="props.kindColor(p.t.kind)" />
                <circle cx="-61" cy="-7" r="3" class="tc-dot" :class="p.t.status" />
                <text x="-52" y="-3.5" class="tc-id">{{ p.t.shortId }}</text>
                <text x="68" y="-3.5" class="tc-status" text-anchor="end">{{ props.statusLabel(p.t.status) }}</text>
                <text x="-66" y="10" class="tc-label">{{ props.truncate(p.t.label, 16) }}</text>
                <g v-if="p.t.status === 'running'">
                  <rect x="-66" y="13.5" width="132" height="3" rx="1.5" class="tc-progress-bg" />
                  <rect x="-66" y="13.5" :width="132 * (p.t.progress ?? 0) / 100" height="3" rx="1.5" class="tc-progress" />
                </g>
              </g>

              <!-- 技能 Agent 内环节点 -->
              <g
                v-for="s in topo.skills"
                :key="s.kind"
                class="skill-node"
                :class="{ on: s.runningCount > 0, dim: focusedSkill && focusedSkill !== s.kind }"
                :style="{ transform: `translate(${s.x}px, ${s.y}px)`, '--sk': s.color }"
                @mouseenter="emit('skill-hover', $event, s)"
                @mouseleave="emit('tip-leave')"
                @click="onNodeClick(() => emit('skill-click', s.kind))"
              >
                <circle r="30" class="sn-halo" />
                <circle r="24" class="sn-core" />
                <text y="6" class="sn-ico" text-anchor="middle">{{ s.icon }}</text>
                <text y="45" class="sn-name" text-anchor="middle">{{ s.name }}</text>
                <text y="59" class="sn-count" text-anchor="middle">
                  {{ s.activeCount > 0 ? `${s.runningCount} 运行 / ${s.activeCount} ${props.liveMode ? '可见' : '活跃'}` : '待命' }}
                </text>
              </g>

              <!-- Worker 外环节点 -->
              <g
                v-for="pw in topo.workers"
                :key="pw.w.id"
                class="worker-node"
                :class="[pw.w.state, { dim: focusedSkill && focusedSkill !== pw.skillKind }]"
                :style="{ transform: `translate(${pw.x}px, ${pw.y}px)` }"
                @mouseenter="emit('worker-hover', $event, pw.w)"
                @mouseleave="emit('tip-leave')"
                @click="onNodeClick(() => emit('worker-click', pw.w))"
              >
                <circle r="21" class="wn-ring-bg" />
                <circle
                  r="21"
                  class="wn-load"
                  :class="{ hot: pw.w.load >= 80 }"
                  :stroke-dasharray="`${(pw.w.load / 100) * 131.9} 131.9`"
                  transform="rotate(-90)"
                />
                <circle r="15" class="wn-core" />
                <text y="3.5" class="wn-pct" text-anchor="middle">{{ pw.w.load }}</text>
                <text y="37" class="wn-id" text-anchor="middle">{{ pw.w.id }}</text>
                <circle cx="13" cy="-13" r="4" class="wn-dot" :class="pw.w.state" />
              </g>

              <!-- 中心调度内核 -->
              <g class="core" :style="{ transform: `translate(${props.cx}px, ${props.cy}px)` }">
                <circle r="88" fill="url(#core-glow)" />
                <g class="spin-a"><circle r="66" class="core-ring" /></g>
                <g class="spin-b"><circle r="53" class="core-ring2" /></g>
                <g v-if="props.isRunning" class="core-sweep">
                  <path d="M 0 0 L 62 0 A 62 62 0 0 1 44 44 Z" fill="url(#sweep-grad)" />
                </g>
                <circle r="34" class="core-center" :class="{ halt: !props.isRunning }" />
                <text y="-1" class="core-ico" text-anchor="middle">🛰</text>
                <text y="14" class="core-status" text-anchor="middle">{{ props.isRunning ? 'LIVE' : 'HALT' }}</text>
                <text y="58" class="core-name" text-anchor="middle">调度内核</text>
              </g>
            </g>
          </svg>
</template>

<script setup lang="ts">
import { ref } from 'vue'

/**
 * 调度星图 SVG 层：坐标与链路全部来自 buildTopo 的结果，交互只上报事件，
 * 选中态/拖拽抑制/浮层定位仍由页面持有。
 */
const props = defineProps<{
  topo: {
    skills: any[]
    sectors: any[]
    workers: any[]
    tasks: any[]
    liveWires: any[]
  }
  cx: number
  cy: number
  rSkill: number
  rWorker: number
  focusedSkill: string | null
  flashTaskId: string | null
  pinnedTaskId: string | null
  kindColor: (kind: string) => string
  statusLabel: (status: string) => string
  truncate: (text: string, max: number) => string
  /** 页面注入的点击节流（拖拽后不触发选中）。 */
  onNodeClick: (action: () => void) => void
  /** 视口拖拽/复位仍由页面统一处理（与其他坞块共享同一套平移量）。 */
  onPointerDown: (event: PointerEvent) => void
  onPointerMove: (event: PointerEvent) => void
  onPointerUp: (event: PointerEvent) => void
  onBgClick: (event: MouseEvent) => void
  onResetView: () => void
  /** 星图平移/缩放：与页面其他坞块共享同一套视口变换。 */
  view: { x: number; y: number; k: number }
  /** 任务完成涟漪（坐标由页面在派发完成时写入）。 */
  ripples: { id: number; x: number; y: number }[]
  liveMode: boolean
  /** 调度内核是否处于运行态（核心脉冲动画与文案）。 */
  isRunning: boolean
}>()

// 视口滚轮缩放挂在 svg 上（passive:false），由页面通过组件 ref 取真实元素。
const svgEl = ref<SVGSVGElement | null>(null)
defineExpose({ el: svgEl })

const emit = defineEmits<{
  (event: 'task-hover', payload: MouseEvent, task: unknown): void
  (event: 'skill-hover', payload: MouseEvent, skill: unknown): void
  (event: 'worker-hover', payload: MouseEvent, worker: unknown): void
  (event: 'tip-leave'): void
  (event: 'task-click', task: unknown): void
  (event: 'skill-click', kind: string): void
  (event: 'worker-click', worker: unknown): void
}>()
</script>

<style scoped>
.topo-svg {
  width: 100%;
  height: 100%;
  display: block;
  user-select: none;
  touch-action: none;
  cursor: grab;
}
.topo-svg:active {
  cursor: grabbing;
}
.topo-bg {
  fill: url(#topo-grid);
}
.grid-line {
  fill: none;
  stroke: var(--text-tertiary);
  stroke-width: 0.5;
  opacity: 0.14;
}
.sector-wedge {
  opacity: 0.05;
  transition: opacity 0.3s ease;
}
.sector-wedge.dim {
  opacity: 0.015;
}
.orbit-guide {
  fill: none;
  stroke: var(--text-tertiary);
  stroke-width: 0.8;
  stroke-dasharray: 2 7;
  opacity: 0.28;
}
.orbit-guide.outer {
  opacity: 0.18;
}
.wire-core {
  fill: none;
  stroke: var(--text-tertiary);
  stroke-width: 1.4;
  stroke-dasharray: 4 6;
  opacity: 0.5;
  animation: dash-flow 2.6s linear infinite;
  transition: opacity 0.3s ease;
}
.wire-member {
  fill: none;
  stroke: var(--text-tertiary);
  stroke-width: 0.9;
  opacity: 0.3;
  transition: opacity 0.3s ease;
}
.wire-live {
  fill: none;
  stroke: var(--accent-ai);
  stroke-width: 1.8;
  stroke-dasharray: 6 5;
  opacity: 0.85;
  animation: dash-flow 0.9s linear infinite;
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--accent-ai) 55%, transparent));
  transition: opacity 0.3s ease;
}
.wire-core.dim,
.wire-member.dim,
.wire-live.dim {
  opacity: 0.08;
}
.particle {
  fill: var(--accent-ai);
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--accent-ai) 80%, transparent));
}
.task-chip,
.skill-node,
.worker-node {
  transition: opacity 0.3s ease;
}
.task-chip.dim,
.skill-node.dim,
.worker-node.dim {
  opacity: 0.18;
}
.task-chip {
  cursor: pointer;
  transition:
    transform 0.75s cubic-bezier(0.2, 0.9, 0.3, 1),
    opacity 0.3s ease;
}
.tc-box {
  fill: var(--bg-main);
  stroke: var(--border-subtle);
  stroke-width: 1;
  filter: drop-shadow(0 2px 5px rgba(17, 24, 39, 0.10));
  transition: stroke 0.2s ease;
}
.task-chip:hover .tc-box {
  stroke: var(--accent-ai);
}
.task-chip.queued .tc-box {
  stroke-dasharray: 4 3;
}
.task-chip.running .tc-box {
  stroke: color-mix(in srgb, var(--accent-ai) 55%, var(--border-subtle));
  filter: drop-shadow(0 0 6px color-mix(in srgb, var(--accent-ai) 30%, transparent));
}
.task-chip.flash .tc-box {
  animation: chip-flash 0.8s ease-in-out 2;
}
.task-chip.pinned .tc-box {
  stroke: var(--accent-ai);
  stroke-width: 2;
  stroke-dasharray: none;
  filter: drop-shadow(0 0 8px color-mix(in srgb, var(--accent-ai) 45%, transparent));
}
.tc-dot {
  fill: var(--text-tertiary);
}
.tc-dot.running {
  fill: var(--accent-ai);
  animation: dot-breathe 1.4s ease-in-out infinite;
}
.tc-dot.awaiting_case_confirm {
  fill: var(--accent-warning);
}
.tc-id {
  font-family: var(--font-mono);
  font-size: 10px;
  fill: var(--text-secondary);
}
.tc-status {
  font-size: 9px;
  fill: var(--text-tertiary);
}
.tc-label {
  font-size: 10.5px;
  font-weight: 500;
  fill: var(--text-primary);
}
.tc-progress-bg {
  fill: var(--bg-elevated);
}
.tc-progress {
  fill: var(--accent-ai);
  transition: width 0.4s ease;
}
.skill-node {
  cursor: pointer;
}
.sn-halo {
  fill: var(--sk, var(--accent-ai));
  opacity: 0.10;
  transition: opacity 0.25s ease, r 0.25s ease;
}
.skill-node.on .sn-halo {
  opacity: 0.22;
  animation: halo-breathe 2.2s ease-in-out infinite;
}
.sn-core {
  fill: var(--bg-main);
  stroke: var(--sk, var(--border-subtle));
  stroke-width: 1.6;
  filter: drop-shadow(0 2px 6px rgba(17, 24, 39, 0.10));
  transition: stroke-width 0.2s ease;
}
.skill-node:hover .sn-core,
.skill-node.on .sn-core {
  stroke-width: 2.4;
}
.sn-ico {
  font-size: 17px;
}
.sn-name {
  font-size: 11.5px;
  font-weight: 600;
  fill: var(--text-primary);
}
.sn-count {
  font-size: 9.5px;
  fill: var(--text-tertiary);
  font-family: var(--font-mono);
}
.worker-node {
  cursor: pointer;
}
.wn-ring-bg {
  fill: none;
  stroke: var(--border-subtle);
  stroke-width: 3;
  opacity: 0.6;
}
.wn-load {
  fill: none;
  stroke: var(--accent-ai);
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 0.6s cubic-bezier(0.2, 0.9, 0.3, 1);
}
.wn-load.hot {
  stroke: var(--accent-warning);
}
.wn-core {
  fill: var(--bg-main);
  stroke: var(--border-subtle);
  stroke-width: 1;
  transition: stroke 0.2s ease;
}
.worker-node:hover .wn-core {
  stroke: var(--accent-ai);
}
.worker-node.busy .wn-core {
  stroke: color-mix(in srgb, var(--accent-ai) 55%, var(--border-subtle));
  filter: drop-shadow(0 0 5px color-mix(in srgb, var(--accent-ai) 35%, transparent));
}
.worker-node.offline {
  opacity: 0.4;
}
.wn-pct {
  font-size: 9.5px;
  font-weight: 600;
  fill: var(--text-primary);
  font-family: var(--font-mono);
}
.wn-id {
  font-size: 9.5px;
  fill: var(--text-secondary);
  font-family: var(--font-mono);
}
.wn-dot {
  fill: var(--text-tertiary);
  stroke: var(--bg-main);
  stroke-width: 1.4;
}
.wn-dot.idle { fill: var(--accent-success); }
.wn-dot.busy { fill: var(--accent-ai); animation: dot-breathe 1.4s ease-in-out infinite; }
.wn-dot.draining { fill: var(--accent-warning); }
.core-ring {
  fill: none;
  stroke: var(--accent-ai);
  stroke-width: 1.2;
  stroke-dasharray: 10 14;
  opacity: 0.55;
}
.core-ring2 {
  fill: none;
  stroke: var(--accent-ai);
  stroke-width: 1;
  stroke-dasharray: 3 9;
  opacity: 0.4;
}
.spin-a {
  animation: core-spin 26s linear infinite;
  transform-box: fill-box;
  transform-origin: center;
}
.spin-b {
  animation: core-spin 18s linear infinite reverse;
  transform-box: fill-box;
  transform-origin: center;
}
.core-sweep {
  animation: core-spin 5s linear infinite;
  transform-box: fill-box;
  transform-origin: center;
}
.core-center {
  fill: var(--bg-main);
  stroke: var(--accent-ai);
  stroke-width: 1.8;
  filter: drop-shadow(0 0 10px color-mix(in srgb, var(--accent-ai) 40%, transparent));
}
.core-center.halt {
  stroke: var(--text-tertiary);
  filter: none;
}
.core-ico {
  font-size: 15px;
}
.core-status {
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.12em;
  fill: var(--accent-ai);
  font-family: var(--font-mono);
}
.core-name {
  font-size: 12px;
  font-weight: 600;
  fill: var(--text-primary);
}
.ripple-c {
  fill: none;
  stroke: var(--accent-success);
  stroke-width: 2.5;
  pointer-events: none;
  animation: ripple-svg 1.1s ease-out forwards;
  transform-box: fill-box;
  transform-origin: center;
}
</style>
