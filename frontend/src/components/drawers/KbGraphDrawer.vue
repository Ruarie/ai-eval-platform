<template>
  <n-drawer :show="show" width="min(1240px, 97vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`知识图谱 · ${kbName || '当前知识库'}`" closable>
      <div v-if="loading" class="graph-state">正在读取实体关系…</div>

      <div v-else-if="error" class="graph-state">
        <div class="graph-error">{{ error }}</div>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>

      <template v-else>
        <div class="graph-meta">
          <span class="small muted">
            {{ viewGraph?.nodes.length || 0 }} 个实体 · {{ viewGraph?.edges.length || 0 }} 条关系
            <template
              v-if="graph?.truncated || (graph && graph.nodes.length > (viewGraph?.nodes.length || 0))"
            >
              （已按关联度截断，仅展示最强的一批）
            </template>
          </span>
          <div class="row" style="gap: 8px">
            <span v-for="item in legend" :key="item.type" class="legend-item small">
              <i :style="{ background: item.color }"></i>{{ item.label }}
              <b class="legend-count">{{ item.count }}</b>
            </span>
            <button
              v-if="graph && graph.nodes.length > VISIBLE_LIMIT"
              class="btn btn-secondary btn-sm"
              @click="showAll = !showAll; resetView()"
            >
              {{ showAll ? '只看核心' : `显示全部 ${graph.nodes.length}` }}
            </button>
            <button class="btn btn-secondary btn-sm" @click="resetView">重置视图</button>
            <button class="btn btn-secondary btn-sm" @click="load">刷新</button>
          </div>
        </div>

        <div v-if="!graph?.nodes.length" class="graph-state">
          <div>当前库还没有抽出实体：先上传文档，等索引状态变为 indexed 后图谱才会出现。</div>
          <button class="btn btn-secondary btn-sm" @click="emit('upload')">↑ 上传文档</button>
        </div>

        <div v-else class="graph-body">
          <svg
            class="graph-canvas"
            :class="{ dragging }"
            :viewBox="`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="知识图谱实体关系图"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <defs>
              <marker
                id="kb-graph-arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b" />
              </marker>
            </defs>
            <g :transform="layerTransform">
            <!-- 簇底色：同类型的节点落在同一片淡色区域里，读图时先看"团"再看点。 -->
            <!-- 基础关系合并成 3 条 path：1800+ 条 <line> 会让 Vue 与浏览器都很吃力。 -->
            <g class="graph-edges" :opacity="selectedId ? 0.18 : 1">
              <path
                v-for="bucket in baseEdgeBuckets"
                :key="bucket.key"
                :d="bucket.d"
                fill="none"
                stroke="#7c8798"
                :stroke-width="bucket.width"
                :opacity="bucket.opacity"
                stroke-linecap="round"
              />
            </g>
            <!-- 选中节点时才逐条画高亮，数量只有它的度数，带箭头与关系提示。 -->
            <g v-if="selectedId" class="graph-edges-highlight">
              <line
                v-for="line in highlightEdges"
                :key="line.key"
                :x1="line.x1"
                :y1="line.y1"
                :x2="line.x2"
                :y2="line.y2"
                stroke="#4a7dfc"
                stroke-width="1.4"
                opacity="0.55"
                stroke-linecap="round"
                marker-end="url(#kb-graph-arrow)"
              >
                <title>{{ line.description || '关系' }}</title>
              </line>
            </g>
            <g
              v-for="item in placed"
              :key="item.node.id"
              class="graph-node"
              :class="{ dimmed: isDimmed(item.node.id), active: item.node.id === selectedId }"
              @click="onNodeClick(item.node.id)"
              @pointerenter="hoverId = item.node.id"
              @pointerleave="hoverId = ''"
            >
              <title>{{ item.node.id }} · {{ typeLabel(item.node.entity_type) }} · {{ item.node.degree }} 条关系</title>
              <!-- 透明热区：节点圆较小，点到标签与圆之间的缝隙也该选中。 -->
              <circle :cx="item.x" :cy="item.y" :r="item.radius + 10" fill="transparent" />
              <!-- 选中态：外扩一圈细环，比改描边颜色更醒目。 -->
              <circle
                v-if="item.node.id === selectedId"
                :cx="item.x"
                :cy="item.y"
                :r="item.radius + 5"
                fill="none"
                stroke="rgba(74,125,252,0.55)"
                stroke-width="2"
              />
              <circle
                :cx="item.x"
                :cy="item.y"
                :r="item.radius"
                :fill="typeColor(item.node.entity_type)"
                stroke="#ffffff"
                stroke-width="1.6"
              />
              <text
                v-if="showLabel(item.node)"
                :x="item.labelX"
                :y="item.labelY"
                :text-anchor="item.labelAnchor"
                class="graph-label"
                :class="{ strong: item.node.id === selectedId }"
              >
                {{ shortLabel(item.node.id) }}
              </text>
            </g>
            </g>
          </svg>

          <aside class="graph-side">
            <template v-if="selected">
              <div class="side-title">{{ selected.id }}</div>
              <div class="side-row">
                <span class="small tertiary">类型</span>
                <span class="chip">{{ typeLabel(selected.entity_type) }}</span>
              </div>
              <div class="side-row">
                <span class="small tertiary">关联数</span>
                <span class="mono small">{{ selected.degree }}</span>
              </div>
              <div class="side-row" style="display: block">
                <div class="small tertiary mb8">描述</div>
                <p class="side-desc">{{ selected.description || '引擎未返回描述' }}</p>
              </div>
              <div class="side-row" style="display: block">
                <div class="small tertiary mb8">来源文档</div>
                <ul class="side-docs">
                  <li v-for="docId in selected.doc_ids" :key="docId" class="small">{{ docName(docId) }}</li>
                  <li v-if="!selected.doc_ids.length" class="small tertiary">未记录来源文档</li>
                </ul>
              </div>
              <div class="side-row" style="display: block">
                <div class="small tertiary mb8">关系（{{ selectedRelations.length }}）</div>
                <div v-for="(rel, index) in selectedRelations" :key="`rel-${index}`" class="rel-row">
                  <span class="rel-dir">{{ rel.dir }}</span>
                  <div class="rel-main">
                    <div class="rel-other">{{ rel.other }}</div>
                    <div v-if="rel.description" class="rel-desc">{{ rel.description }}</div>
                  </div>
                </div>
                <div v-if="!selectedRelations.length" class="small tertiary">该实体暂无关系</div>
              </div>
            </template>
            <div v-else class="side-hint">
              <p class="small tertiary">
                点击节点或下方实体查看类型、描述与来源文档；节点大小表示库内关联度。
              </p>
              <div class="small tertiary mb8">关联度最高的实体</div>
              <button
                v-for="node in topNodes"
                :key="node.id"
                type="button"
                class="top-chip"
                @click="selectedId = node.id"
              >
                <i :style="{ background: typeColor(node.entity_type) }"></i>
                <span>{{ node.id }}</span>
                <b>{{ node.degree }}</b>
              </button>
            </div>
          </aside>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '../../api/http'
import type { KbGraph, KbGraphEdge, KbGraphNode } from '../../api/types'

const props = defineProps<{
  show: boolean
  kbId: string
  kbName?: string
  docs?: Array<{ doc_id: string; filename: string }>
}>()

const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'upload'): void
}>()

const CANVAS_WIDTH = 1200
const CANVAS_HEIGHT = 800
const LEGEND_LIMIT = 6
// 与图例、节点、圆点共用一套定性色板：同类同色、跨类区分度高。
const TYPE_COLORS: Record<string, string> = {
  artifact: '#4a7dfc',
  concept: '#8b5cf6',
  content: '#0ea5a4',
  data: '#f0a13c',
  method: '#22a06b',
  event: '#e4568b',
  person: '#f97316',
  organization: '#6366f1',
  location: '#0ea5e9',
  activity: '#a3a847',
  category: '#7c8798',
  other: '#94a3b8',
}
const TYPE_FALLBACK = ['#4a7dfc', '#8b5cf6', '#0ea5a4', '#f0a13c', '#22a06b', '#e4568b']

const graph = ref<KbGraph | null>(null)
const loading = ref(false)
const error = ref('')
const selectedId = ref('')

async function load() {
  const kbId = props.kbId
  if (!kbId) return
  loading.value = true
  error.value = ''
  selectedId.value = ''
  try {
    // 不设人工上限：要多少由后端按引擎能力截断（truncated 会提示）。
    const data = await api.kb.getGraph(kbId, 2000)
    // 请求期间切换了知识库：丢弃旧响应，避免把上一个库的图写到当前库上。
    if (kbId !== props.kbId) return
    graph.value = data
  } catch (err) {
    if (kbId !== props.kbId) return
    graph.value = null
    error.value = err instanceof Error ? err.message : '图谱读取失败，请稍后重试'
  } finally {
    if (kbId === props.kbId) loading.value = false
  }
}

watch(
  () => props.show,
  (visible) => {
    if (visible) void load()
  },
  { immediate: true },
)
watch(
  () => props.kbId,
  () => {
    if (props.show) void load()
  },
)

interface PlacedNode {
  node: KbGraphNode
  x: number
  y: number
  radius: number
  /** 节点在环上的极角，用于把外圈标签甩到圆外侧。 */
  angle: number
  ring: number
  labelX: number
  labelY: number
  labelAnchor: 'start' | 'middle' | 'end'
}

// ─── 力导向布局（参考 HKUDS/LightRAG 的 ForceAtlas2 用法）──────────────
// LightRAG 的做法：一图只跑一次力导向、按时间预算收敛、节点数大时用空间网格
// 近似斥力（等价 Barnes-Hut 的效果）。这里用同样思路自实现，避免引入 sigma/graphology。
const LAYOUT_BUDGET_MS = 420
const REPULSION = 12000
const SPRING = 0.006
const GRAVITY = 0.0002
// 同类实体的向心引力：形成可分瓣的"社区"，避免 1000 节点糊成一个球。
const TYPE_GRAVITY = 0.02
const CELL = 80

/** 度数 → 半径：对数压缩；节点越多整体越小，避免糊成一片。 */
function nodeRadius(degree: number, total: number) {
  const shrink = Math.max(0.55, Math.min(1, Math.sqrt(260 / Math.max(1, total))))
  return Math.min(13, (3 + Math.log2(1 + Math.max(0, degree)) * 2.6) * shrink)
}

/**
 * 力导向布局：斥力（空间网格近似）+ 边弹簧 + 向心引力，按时间预算迭代。
 *
 * 网格分簇虽然整齐，但节点像"珠子串"、边跨簇全挤在中间；力导向更接近
 * LightRAG 的观感：同类实体自然聚成团，长尾散在外围。
 */
function layout(nodes: KbGraphNode[], edges: KbGraphEdge[]): PlacedNode[] {
  const total = nodes.length
  if (!total) return []

  const index = new Map<string, number>()
  nodes.forEach((node, i) => index.set(node.id, i))

  const px = new Float64Array(total)
  const py = new Float64Array(total)
  const vx = new Float64Array(total)
  const vy = new Float64Array(total)
  const radius = new Float64Array(total)

  // 初始位置：黄金角螺旋 + 按 id 的稳定抖动，保证每次打开布局一致。
  nodes.forEach((node, i) => {
    const angle = i * 2.399963229728653
    const spread = 26 * Math.sqrt(i + 1)
    px[i] = Math.cos(angle) * spread
    py[i] = Math.sin(angle) * spread * 0.86
    radius[i] = nodeRadius(node.degree, total)
  })

  const links: Array<[number, number]> = []
  for (const edge of edges) {
    const a = index.get(edge.source)
    const b = index.get(edge.target)
    if (a === undefined || b === undefined || a === b) continue
    links.push([a, b])
  }

  const started = performance.now()
  let alpha = 1
  for (let iter = 0; iter < 600; iter += 1) {
    // 空间网格：只和相邻 9 个格子里的节点算斥力。
    const grid = new Map<string, number[]>()
    for (let i = 0; i < total; i += 1) {
      const key = `${Math.floor(px[i] / CELL)}:${Math.floor(py[i] / CELL)}`
      const bucket = grid.get(key)
      if (bucket) bucket.push(i)
      else grid.set(key, [i])
    }

    for (let i = 0; i < total; i += 1) {
      const cx = Math.floor(px[i] / CELL)
      const cy = Math.floor(py[i] / CELL)
      for (let gx = cx - 1; gx <= cx + 1; gx += 1) {
        for (let gy = cy - 1; gy <= cy + 1; gy += 1) {
          const bucket = grid.get(`${gx}:${gy}`)
          if (!bucket) continue
          for (const j of bucket) {
            if (j <= i) continue
            let dx = px[i] - px[j]
            let dy = py[i] - py[j]
            let dist2 = dx * dx + dy * dy
            if (dist2 < 1) {
              dx = (i - j) * 0.01
              dy = 0.01
              dist2 = dx * dx + dy * dy
            }
            const minGap = radius[i] + radius[j] + 10
            const dist = Math.sqrt(dist2)
            // 斥力：近距离时退化为碰撞分离，远距离按 k^2/d 衰减。
            const strength = dist < minGap ? (minGap - dist) * 6 : REPULSION / dist2
            const fx = (dx / dist) * strength * alpha
            const fy = (dy / dist) * strength * alpha
            vx[i] += fx
            vy[i] += fy
            vx[j] -= fx
            vy[j] -= fy
          }
        }
      }
    }

    for (const [a, b] of links) {
      const dx = px[b] - px[a]
      const dy = py[b] - py[a]
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = (dist - 90) * SPRING * alpha
      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      vx[a] += fx
      vy[a] += fy
      vx[b] -= fx
      vy[b] -= fy
    }

    // 每轮重算各类型质心，把所有节点往自己类型的质心拉一点。
    const centroids = new Map<string, { x: number; y: number; n: number }>()
    for (let i = 0; i < total; i += 1) {
      const key = (nodes[i].entity_type || 'other').toLowerCase()
      const item = centroids.get(key) ?? { x: 0, y: 0, n: 0 }
      item.x += px[i]
      item.y += py[i]
      item.n += 1
      centroids.set(key, item)
    }
    for (let i = 0; i < total; i += 1) {
      const key = (nodes[i].entity_type || 'other').toLowerCase()
      const item = centroids.get(key)
      if (!item || item.n < 2) continue
      vx[i] += (item.x / item.n - px[i]) * TYPE_GRAVITY * alpha
      vy[i] += (item.y / item.n - py[i]) * TYPE_GRAVITY * alpha
    }

    for (let i = 0; i < total; i += 1) {
      vx[i] -= px[i] * GRAVITY * alpha
      vy[i] -= py[i] * GRAVITY * alpha
      px[i] += vx[i] * 0.55
      py[i] += vy[i] * 0.55
      vx[i] *= 0.35
      vy[i] *= 0.35
    }

    alpha *= 0.985
    if (performance.now() - started > LAYOUT_BUDGET_MS) break
  }

  // 归一化到画布：算包围盒后等比缩放，留 60px 边距。
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (let i = 0; i < total; i += 1) {
    minX = Math.min(minX, px[i] - radius[i])
    maxX = Math.max(maxX, px[i] + radius[i])
    minY = Math.min(minY, py[i] - radius[i])
    maxY = Math.max(maxY, py[i] + radius[i])
  }
  const spanX = Math.max(1, maxX - minX)
  const spanY = Math.max(1, maxY - minY)
  const scale = Math.min((CANVAS_WIDTH - 120) / spanX, (CANVAS_HEIGHT - 120) / spanY)
  const offsetX = (CANVAS_WIDTH - spanX * scale) / 2 - minX * scale
  const offsetY = (CANVAS_HEIGHT - spanY * scale) / 2 - minY * scale

  return nodes.map((node, i) => {
    const x = px[i] * scale + offsetX
    const y = py[i] * scale + offsetY
    const r = Math.max(3, Math.min(16, radius[i] * Math.max(0.75, scale)))
    return {
      node,
      x,
      y,
      radius: r,
      angle: Math.atan2(py[i], px[i]),
      ring: 0,
      labelX: x,
      labelY: y - r - 7,
      labelAnchor: 'middle' as const,
    }
  })
}

// 大图默认只渲染关联度最高的一批：1000 节点/3300 边在抽屉里会糊成噪点，
// LightRAG 也是靠"按规模降级 + 用户主动放大"来处理这种情况。
const VISIBLE_LIMIT = 400
const showAll = ref(false)

const viewGraph = computed(() => {
  const g = graph.value
  if (!g) return null
  if (showAll.value || g.nodes.length <= VISIBLE_LIMIT) return g
  const nodes = [...g.nodes]
    .sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
    .slice(0, VISIBLE_LIMIT)
  const keep = new Set(nodes.map((node) => node.id))
  return { ...g, nodes, edges: g.edges.filter((e) => keep.has(e.source) && keep.has(e.target)) }
})

const placed = computed(() => layout(viewGraph.value?.nodes ?? [], viewGraph.value?.edges ?? []))

const positions = computed(() => new Map(placed.value.map((item) => [item.node.id, item])))
/** 基础关系：按权重平方根分三档合并成 path（参考 LightRAG 的边宽策略）。 */
const baseEdgeBuckets = computed(() => {
  const buckets = [
    { key: 'thin', d: [] as string[], width: 0.7, opacity: 0.09 },
    { key: 'mid', d: [] as string[], width: 1.1, opacity: 0.16 },
    { key: 'thick', d: [] as string[], width: 1.6, opacity: 0.26 },
  ]
  for (const edge of viewGraph.value?.edges ?? []) {
    const from = positions.value.get(edge.source)
    const to = positions.value.get(edge.target)
    if (!from || !to) continue
    const weight = Math.max(0, Number(edge.weight ?? 1))
    const bucket = weight >= 4 ? buckets[2] : weight >= 1.5 ? buckets[1] : buckets[0]
    bucket.d.push(`M${from.x.toFixed(1)} ${from.y.toFixed(1)}L${to.x.toFixed(1)} ${to.y.toFixed(1)}`)
  }
  return buckets.map((bucket) => ({ ...bucket, d: bucket.d.join('') }))
})

const highlightEdges = computed(() => {
  const focus = selectedId.value
  if (!focus) return []
  const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number; description: string }> = []
  for (const edge of viewGraph.value?.edges ?? []) {
    if (edge.source !== focus && edge.target !== focus) continue
    const from = positions.value.get(edge.source)
    const to = positions.value.get(edge.target)
    if (!from || !to) continue
    lines.push({
      key: `${edge.source}->${edge.target}`,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      description: (edge.description || '').trim(),
    })
  }
  return lines
})

const selected = computed(() => (viewGraph.value?.nodes ?? []).find((node) => node.id === selectedId.value) ?? null)

const selectedRelations = computed(() => {
  const node = selected.value
  if (!node) return []
  const rows: Array<{ dir: string; other: string; description: string }> = []
  for (const edge of viewGraph.value?.edges ?? []) {
    if (edge.source === node.id) {
      rows.push({ dir: '→', other: edge.target, description: (edge.description || '').trim() })
    } else if (edge.target === node.id) {
      rows.push({ dir: '←', other: edge.source, description: (edge.description || '').trim() })
    }
  }
  return rows.slice(0, 10)
})

const topNodes = computed(() =>
  [...(viewGraph.value?.nodes ?? [])]
    .sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
    .slice(0, 6),
)

const hoverId = ref('')
/** 悬停优先于选中：LightRAG 是 hover 即聚焦、点击才持久选中。 */
const focusId = computed(() => hoverId.value || selectedId.value)

const neighbours = computed(() => {
  const ids = new Set<string>()
  const id = focusId.value
  if (!id) return ids
  for (const edge of viewGraph.value?.edges ?? []) {
    if (edge.source === id) ids.add(edge.target)
    else if (edge.target === id) ids.add(edge.source)
  }
  return ids
})

const legend = computed(() => {
  const counts = new Map<string, number>()
  for (const node of viewGraph.value?.nodes ?? []) {
    const type = (node.entity_type || 'other').toLowerCase()
    counts.set(type, (counts.get(type) ?? 0) + 1)
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, LEGEND_LIMIT)
    .map(([type, count]) => ({ type, count, label: typeLabel(type), color: typeColor(type) }))
})

// ─── 视图缩放 / 平移：用 transform 作用在内容组上 ───
// 之前改 viewBox，每帧都会触发整棵 SVG 重算；改 transform 后拖拽/滚轮只动一个属性，
// 500 节点 / 1800 边的场景下差别非常明显。
const view = ref({ scale: 1, x: 0, y: 0 })
const layerTransform = computed(
  () => `translate(${view.value.x.toFixed(2)} ${view.value.y.toFixed(2)}) scale(${view.value.scale.toFixed(3)})`,
)
const dragging = ref(false)
let dragOrigin: { x: number; y: number; vx: number; vy: number } | null = null
let moved = false
let frame = 0
let pendingView: { scale: number; x: number; y: number } | null = null

function resetView() {
  view.value = { scale: 1, x: 0, y: 0 }
}

/** 合并同一帧内的多次缩放/平移，指针事件密集时不再逐条触发渲染。 */
function scheduleView(next: { scale: number; x: number; y: number }) {
  pendingView = next
  if (frame) return
  frame = requestAnimationFrame(() => {
    frame = 0
    if (pendingView) view.value = pendingView
    pendingView = null
  })
}

function onWheel(event: WheelEvent) {
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  const factor = event.deltaY > 0 ? 1.12 : 0.89
  const nextScale = Math.min(5, Math.max(0.5, view.value.scale * factor))
  // 以光标为锚点缩放：光标下的内容保持不动。
  const ratioX = (event.clientX - rect.left) / rect.width
  const ratioY = (event.clientY - rect.top) / rect.height
  const anchorX = ratioX * CANVAS_WIDTH
  const anchorY = ratioY * CANVAS_HEIGHT
  const k = nextScale / view.value.scale
  scheduleView({
    scale: nextScale,
    x: anchorX - (anchorX - view.value.x) * k,
    y: anchorY - (anchorY - view.value.y) * k,
  })
}

function onPointerDown(event: PointerEvent) {
  dragging.value = true
  moved = false
  dragOrigin = {
    x: event.clientX,
    y: event.clientY,
    vx: view.value.x,
    vy: view.value.y,
  }
  // 不在这里 capture：pointer capture 会把后续事件重定向到 svg，
  // 节点上的 click 就收不到了（表现为「点节点没反应」）。拖动超过阈值再 capture。
}

function onPointerMove(event: PointerEvent) {
  if (!dragOrigin) return
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  if (!moved) {
    if (Math.abs(event.clientX - dragOrigin.x) + Math.abs(event.clientY - dragOrigin.y) <= 3) {
      return
    }
    moved = true
    ;(event.currentTarget as SVGSVGElement).setPointerCapture?.(event.pointerId)
  }
  scheduleView({
    scale: view.value.scale,
    x: dragOrigin.vx + ((event.clientX - dragOrigin.x) * CANVAS_WIDTH) / rect.width,
    y: dragOrigin.vy + ((event.clientY - dragOrigin.y) * CANVAS_HEIGHT) / rect.height,
  })
}

function onPointerUp() {
  dragging.value = false
  dragOrigin = null
}

/** 拖拽结束时不要顺带把节点选中，避免平移后误触详情。 */
function onNodeClick(nodeId: string) {
  if (moved) {
    moved = false
    return
  }
  selectedId.value = selectedId.value === nodeId ? '' : nodeId
}

const LABEL_LIMIT = 12

/** 参考 LightRAG：大图硬性限制标签数量，只标度数最高的一批，聚焦时补邻居。 */
const labelIds = computed(() => {
  const ids = new Set<string>()
  const ranked = [...placed.value].sort((a, b) => b.node.degree - a.node.degree)
  for (const item of ranked) {
    if (ids.size >= LABEL_LIMIT) break
    ids.add(item.node.id)
  }
  for (const id of neighbours.value) ids.add(id)
  if (focusId.value) ids.add(focusId.value)
  return ids
})

function showLabel(node: KbGraphNode) {
  return labelIds.value.has(node.id)
}

/** 长实体名截断显示，完整名称在右侧详情里看。 */
function shortLabel(name: string) {
  return name.length > 12 ? `${name.slice(0, 11)}…` : name
}

function isDimmed(nodeId: string) {
  const focus = focusId.value
  if (!focus) return false
  return nodeId !== focus && !neighbours.value.has(nodeId)
}

// LightRAG 的实体类型枚举是英文，界面上给出中文名，避免中英混排。
const TYPE_LABELS: Record<string, string> = {
  other: '其他',
  concept: '概念',
  content: '内容',
  artifact: '产物',
  method: '方法',
  data: '数据',
  event: '事件',
  person: '人物',
  organization: '组织',
  activity: '活动',
  creature: '生物',
  naturalobject: '自然对象',
  location: '地点',
  category: '类别',
}

function typeLabel(type: string) {
  const key = (type || '').toLowerCase()
  return TYPE_LABELS[key] || type || '未标注'
}

/** 按实体类型取色：已知类型走固定色板，未知类型用稳定 hash 兜底。 */
function typeColor(type: string) {
  const key = (type || 'other').toLowerCase()
  if (TYPE_COLORS[key]) return TYPE_COLORS[key]
  let hash = 0
  for (const char of key) hash = (hash * 31 + char.charCodeAt(0)) % 9973
  return TYPE_FALLBACK[hash % TYPE_FALLBACK.length]
}

function docName(docId: string) {
  return (props.docs ?? []).find((doc) => doc.doc_id === docId)?.filename ?? docId
}
</script>

<style scoped>
.graph-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 56px 20px;
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: center;
}

.graph-error {
  color: var(--danger, #d9534f);
}

.graph-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-tertiary);
}

.legend-item i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;
}

.graph-body {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.graph-canvas {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
  height: auto;
  aspect-ratio: 1200 / 800;
  max-height: calc(100vh - 300px);
  /* 极浅的径向渐变把视觉重心收到中心，比纯灰底更像「图」而不是「表格」。 */
  background:
    radial-gradient(circle at 50% 46%, #ffffff 0%, #f6f8fc 62%, #eef2f8 100%);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 12px;
}

.graph-canvas.dragging {
  cursor: grabbing;
}

/* 画布内部独立成层：拖动时只重绘这一块，不牵连外层列表与侧栏。 */
.graph-canvas {
  contain: layout paint;
}

.graph-canvas > g[transform] {
  will-change: transform;
}

.graph-node {
  cursor: pointer;
  transition: opacity 0.15s ease;
}

.graph-node.active circle {
  filter: drop-shadow(0 1px 3px rgba(31, 41, 55, 0.24));
}

.graph-label.strong {
  font-weight: 600;
  fill: var(--text-primary, #1f2430);
}

.graph-node.dimmed {
  opacity: 0.32;
}

.graph-label {
  font-size: 11px;
  fill: #3d4657;
  pointer-events: none;
  /* 白色描边做光晕：标签压在连线上也能读清。 */
  paint-order: stroke;
  stroke: #f7f9fc;
  stroke-width: 3px;
  stroke-linejoin: round;
}

.legend-count {
  margin-left: 2px;
  font-weight: 500;
  color: var(--text-quaternary, #9aa3b2);
}

.graph-side {
  flex: 0 0 232px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 12px;
  padding: 14px;
  overflow-y: auto;
}

.side-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 10px;
  word-break: break-all;
}

.side-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.graph-cluster-labels .cluster-label {
  font-size: 11.5px;
  font-weight: 600;
  letter-spacing: 0.3px;
  opacity: 0.85;
  pointer-events: none;
  paint-order: stroke;
  stroke: #f8fafc;
  stroke-width: 3px;
  stroke-linejoin: round;
}

.rel-row {
  display: flex;
  gap: 6px;
  padding: 6px 0;
  border-top: 1px dashed var(--border, #eef1f5);
}

.rel-dir {
  flex: 0 0 auto;
  color: var(--text-quaternary, #9aa3b2);
  font-size: 12px;
  line-height: 1.5;
}

.rel-main {
  min-width: 0;
}

.rel-other {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  word-break: break-word;
}

.rel-desc {
  font-size: 11.5px;
  color: var(--text-tertiary, #8b94a3);
  line-height: 1.5;
  margin-top: 2px;
  word-break: break-word;
}

.top-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 6px 8px;
  margin-bottom: 6px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  text-align: left;
}

.top-chip:hover {
  border-color: var(--accent, #4a7dfc);
  color: var(--text-primary, #1f2430);
}

.top-chip i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
}

.top-chip span {
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-chip b {
  font-weight: 500;
  color: var(--text-quaternary, #9aa3b2);
}

.side-desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary, #4b5563);
  margin: 0;
  word-break: break-word;
}

.side-docs {
  margin: 0;
  padding-left: 16px;
  display: grid;
  gap: 4px;
}

.side-hint {
  line-height: 1.7;
}
</style>
