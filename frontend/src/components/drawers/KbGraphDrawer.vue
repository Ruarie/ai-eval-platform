<template>
  <n-drawer :show="show" width="min(1020px, 96vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`知识图谱 · ${kbName || '当前知识库'}`" closable>
      <div v-if="loading" class="graph-state">正在读取实体关系…</div>

      <div v-else-if="error" class="graph-state">
        <div class="graph-error">{{ error }}</div>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>

      <template v-else>
        <div class="graph-meta">
          <span class="small muted">
            {{ graph?.nodes.length || 0 }} 个实体 · {{ graph?.edges.length || 0 }} 条关系
            <template v-if="graph?.truncated">（已按关联度截断，仅展示最强的节点）</template>
          </span>
          <div class="row" style="gap: 8px">
            <span v-for="item in legend" :key="item.type" class="legend-item small">
              <i :style="{ background: item.color }"></i>{{ item.label }}
              <b class="legend-count">{{ item.count }}</b>
            </span>
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
            <g class="graph-clusters">
              <ellipse
                v-for="cluster in clusters"
                :key="`cluster-${cluster.type}`"
                :cx="cluster.x"
                :cy="cluster.y"
                :rx="cluster.radius * 1.12"
                :ry="cluster.radius * 0.84"
                :fill="cluster.color"
                opacity="0.06"
              />
            </g>
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
            <g class="graph-cluster-labels">
              <text
                v-for="cluster in clusters"
                :key="`cluster-label-${cluster.type}`"
                :x="cluster.x"
                :y="cluster.labelY"
                text-anchor="middle"
                class="cluster-label"
                :style="{ fill: cluster.color }"
              >
                {{ cluster.label }} · {{ cluster.count }}
              </text>
            </g>
            <g
              v-for="item in placed"
              :key="item.node.id"
              class="graph-node"
              :class="{ dimmed: isDimmed(item.node.id), active: item.node.id === selectedId }"
              @click="onNodeClick(item.node.id)"
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
import type { KbGraph, KbGraphNode } from '../../api/types'

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

// 分簇用网格铺排：簇多、单簇节点多时，环形分布会互相重叠，网格最稳。
interface ClusterInfo {
  type: string
  label: string
  color: string
  count: number
  x: number
  y: number
  radius: number
  labelY: number
}

/**
 * 类型分簇 + 网格铺排：每个实体类型占一个格子，簇内沿黄金角螺旋展开。
 *
 * 500 节点时（概念 115 / 产物 106 …）环形簇心距离不够，大簇必然互相压；
 * 改成网格后每个簇有独立空间，簇内步长按格子大小自适应，重叠问题消失。
 */
function layout(nodes: KbGraphNode[]): { nodes: PlacedNode[]; clusters: ClusterInfo[] } {
  const total = nodes.length
  if (!total) return { nodes: [], clusters: [] }

  const byType = new Map<string, KbGraphNode[]>()
  for (const node of nodes) {
    const key = (node.entity_type || 'other').toLowerCase()
    const bucket = byType.get(key) ?? []
    bucket.push(node)
    byType.set(key, bucket)
  }
  const groups = [...byType.entries()].sort(
    (a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]),
  )

  const cols = Math.ceil(Math.sqrt(groups.length))
  const rows = Math.ceil(groups.length / cols)
  const cellW = CANVAS_WIDTH / cols
  const cellH = CANVAS_HEIGHT / rows

  const placedNodes: PlacedNode[] = []
  const clusters: ClusterInfo[] = []
  const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

  groups.forEach(([type, bucket], groupIndex) => {
    bucket.sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
    const col = groupIndex % cols
    const row = Math.floor(groupIndex / cols)
    const cellX = col * cellW
    const cellY = row * cellH
    const cx = cellX + cellW / 2
    const cy = cellY + cellH / 2 + 10
    const n = bucket.length
    // 步长同时受簇规模与格子尺寸约束，保证不越出本格。
    const step = n <= 1 ? 0 : Math.min(11 + 7.4 * Math.sqrt(n - 1), Math.min(cellW, cellH) * 0.34)
    const shrink = Math.max(0.55, Math.min(1, step / 62))

    bucket.forEach((node, index) => {
      const ratio = n <= 1 ? 0 : Math.sqrt(index / (n - 1))
      const spread = step * ratio
      const angle = index === 0 ? 0 : index * GOLDEN_ANGLE
      const x = cx + Math.cos(angle) * spread * 1.08
      const y = cy + Math.sin(angle) * spread * 0.86
      const radius =
        (3.8 + Math.min(7.2, Math.sqrt(Math.max(0, node.degree)) * 1.35)) * shrink

      const outward =
        Math.cos(angle) * Math.cos(-Math.PI / 2) + Math.sin(angle) * Math.sin(-Math.PI / 2) >= 0
      const anchor: 'start' | 'middle' | 'end' =
        index === 0 ? 'middle' : outward ? 'start' : 'end'
      placedNodes.push({
        node,
        x,
        y,
        radius,
        angle,
        ring: index,
        labelX: index === 0 ? x : x + (outward ? radius + 7 : -(radius + 7)),
        labelY: index === 0 ? y - radius - 10 : y + 3.5,
        labelAnchor: anchor,
      })
    })

    clusters.push({
      type,
      label: typeLabel(type),
      color: typeColor(type),
      count: n,
      x: cx,
      y: cy,
      radius: step + 16,
      // 标签固定在格子顶部，避免被簇内节点盖住。
      labelY: cellY + 18,
    })
  })

  return { nodes: placedNodes, clusters }
}

const layoutResult = computed(() => layout(graph.value?.nodes ?? []))
const placed = computed(() => layoutResult.value.nodes)
const clusters = computed(() => layoutResult.value.clusters)

const positions = computed(() => new Map(placed.value.map((item) => [item.node.id, item])))

/** 基础关系：按两端较弱度数分三档，每档合并成一条 path。 */
const baseEdgeBuckets = computed(() => {
  const buckets = [
    { key: 'weak', d: [] as string[], width: 0.6, opacity: 0.035 },
    { key: 'mid', d: [] as string[], width: 0.8, opacity: 0.08 },
    { key: 'strong', d: [] as string[], width: 1.1, opacity: 0.16 },
  ]
  for (const edge of graph.value?.edges ?? []) {
    const from = positions.value.get(edge.source)
    const to = positions.value.get(edge.target)
    if (!from || !to) continue
    const weak = Math.min(from.node.degree, to.node.degree)
    const bucket = weak >= 12 ? buckets[2] : weak >= 4 ? buckets[1] : buckets[0]
    bucket.d.push(`M${from.x.toFixed(1)} ${from.y.toFixed(1)}L${to.x.toFixed(1)} ${to.y.toFixed(1)}`)
  }
  return buckets.map((bucket) => ({ ...bucket, d: bucket.d.join('') }))
})

/** 选中节点的一跳关系：单独绘制，带箭头与关系描述 tooltip。 */
const highlightEdges = computed(() => {
  if (!selectedId.value) return []
  const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number; description: string }> = []
  for (const edge of graph.value?.edges ?? []) {
    if (edge.source !== selectedId.value && edge.target !== selectedId.value) continue
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

const selected = computed(() => (graph.value?.nodes ?? []).find((node) => node.id === selectedId.value) ?? null)

const selectedRelations = computed(() => {
  const node = selected.value
  if (!node) return []
  const rows: Array<{ dir: string; other: string; description: string }> = []
  for (const edge of graph.value?.edges ?? []) {
    if (edge.source === node.id) {
      rows.push({ dir: '→', other: edge.target, description: (edge.description || '').trim() })
    } else if (edge.target === node.id) {
      rows.push({ dir: '←', other: edge.source, description: (edge.description || '').trim() })
    }
  }
  return rows.slice(0, 10)
})

const topNodes = computed(() =>
  [...(graph.value?.nodes ?? [])]
    .sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))
    .slice(0, 6),
)

const neighbours = computed(() => {
  const ids = new Set<string>()
  if (!selected.value) return ids
  for (const edge of graph.value?.edges ?? []) {
    if (edge.source === selected.value.id) ids.add(edge.target)
    if (edge.target === selected.value.id) ids.add(edge.source)
  }
  return ids
})

const legend = computed(() => {
  const counts = new Map<string, number>()
  for (const node of graph.value?.nodes ?? []) {
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

/** 标签上限 14 个：节点多时只标度数最高的实体，否则长实体名会互相压住。 */
const labelIds = computed(() => {
  const ids = new Set<string>()
  // 每簇只标「度数最高」的那个（簇心）：两个标签一定会在簇内重叠。
  const perCluster = new Set<string>()
  for (const item of placed.value) {
    const key = (item.node.entity_type || 'other').toLowerCase()
    if (perCluster.has(key)) continue
    perCluster.add(key)
    ids.add(item.node.id)
  }
  // 选中节点与它的一跳邻居补标签，方便顺着关系看。
  if (selectedId.value) {
    ids.add(selectedId.value)
    let extra = 0
    for (const id of neighbours.value) {
      if (extra >= 12) break
      ids.add(id)
      extra += 1
    }
  }
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
  if (!selectedId.value) return false
  return nodeId !== selectedId.value && !neighbours.value.has(nodeId)
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
