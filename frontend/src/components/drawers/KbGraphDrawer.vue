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
            :viewBox="viewBoxAttr"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="知识图谱实体关系图"
            @wheel.prevent="onWheel"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointerleave="onPointerUp"
          >
            <g>
              <line
                v-for="line in renderedEdges"
                :key="line.key"
                :x1="line.x1"
                :y1="line.y1"
                :x2="line.x2"
                :y2="line.y2"
                stroke="var(--border-strong, #d8dce3)"
                :stroke-width="line.dimmed ? 0.6 : 1.2"
                :opacity="line.dimmed ? 0.25 : 0.75"
              />
            </g>
            <g
              v-for="item in placed"
              :key="item.node.id"
              class="graph-node"
              :class="{ dimmed: isDimmed(item.node.id) }"
              @click="onNodeClick(item.node.id)"
            >
              <circle
                :cx="item.x"
                :cy="item.y"
                :r="item.radius"
                :fill="typeColor(item.node.entity_type)"
                :stroke="item.node.id === selectedId ? 'var(--text-primary, #1f2430)' : 'rgba(0,0,0,0.18)'"
                :stroke-width="item.node.id === selectedId ? 2.4 : 1"
              />
              <text
                v-if="showLabel(item.node)"
                :x="item.x"
                :y="item.y - item.radius - 5"
                text-anchor="middle"
                class="graph-label"
                :class="{ strong: item.node.id === selectedId }"
              >
                {{ shortLabel(item.node.id) }}
              </text>
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
            </template>
            <div v-else class="small tertiary side-hint">
              点击节点查看实体类型、描述与来源文档；节点大小表示库内关联度。
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

const CANVAS_WIDTH = 820
const CANVAS_HEIGHT = 520
const PADDING = 44
const LEGEND_LIMIT = 6
const TYPE_COLORS = ['#5b8def', '#e8894a', '#3fae8f', '#9b6be0', '#d0a03a', '#5aa9c9']

const graph = ref<KbGraph | null>(null)
const loading = ref(false)
const error = ref('')
const selectedId = ref('')

async function load() {
  if (!props.kbId) return
  loading.value = true
  error.value = ''
  selectedId.value = ''
  try {
    // 默认取 100 个实体：更多节点会让环形布局过密，图例与标签失去可读性。
    graph.value = await api.kb.getGraph(props.kbId, 100)
  } catch (err) {
    graph.value = null
    error.value = err instanceof Error ? err.message : '图谱读取失败，请稍后重试'
  } finally {
    loading.value = false
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
}

/**
 * 分层环形布局（按度数分环 + 环内均匀分布）。
 *
 * 之前用力导向：150 个节点时斥力把大半节点推到画布边界并被钳制成"边框一圈球"，
 * 中间只剩交叉的边。环形布局稳定、有层次，也不会随数据量抖动；缩放/拖拽负责
 * 看局部细节。
 */
function layout(nodes: KbGraphNode[]): PlacedNode[] {
  const total = nodes.length
  if (!total) return []

  const centerX = CANVAS_WIDTH / 2
  const centerY = CANVAS_HEIGHT / 2
  const maxRadiusY = Math.min(CANVAS_HEIGHT / 2 - PADDING, CANVAS_HEIGHT * 0.42)
  const maxRadiusX = maxRadiusY * (CANVAS_WIDTH / CANVAS_HEIGHT)
  const sorted = [...nodes].sort((a, b) => b.degree - a.degree || a.id.localeCompare(b.id))

  // 内圈放度数最高的实体，外圈放长尾；数量按环周长近似分配。
  const ringSizes = [
    Math.min(12, total),
    Math.min(40, Math.max(0, total - 12)),
    Math.max(0, total - 52),
  ]
  const ringRadius = [0.36, 0.68, 1]
  const placedNodes: PlacedNode[] = []
  let cursor = 0

  ringSizes.forEach((size, ringIndex) => {
    const count = Math.min(size, total - cursor)
    if (count <= 0) return
    const rx = maxRadiusX * ringRadius[ringIndex]
    const ry = maxRadiusY * ringRadius[ringIndex]
    // 每环错开半个扇区，避免不同环的节点在视觉上连成直线。
    const offset = ringIndex === 0 ? -Math.PI / 2 : -Math.PI / 2 + Math.PI / count
    for (let i = 0; i < count; i += 1) {
      const angle = offset + (i / count) * Math.PI * 2
      const node = sorted[cursor + i]
      placedNodes.push({
        node,
        x: centerX + Math.cos(angle) * rx,
        y: centerY + Math.sin(angle) * ry,
        radius: (ringIndex === 0 ? 8 : ringIndex === 1 ? 5.5 : 4) + Math.min(6, node.degree * 0.5),
      })
    }
    cursor += count
  })

  return placedNodes
}

const placed = computed(() => layout(graph.value?.nodes ?? []))

const positions = computed(() => new Map(placed.value.map((item) => [item.node.id, item])))

const renderedEdges = computed(() => {
  const lines: Array<{ key: string; x1: number; y1: number; x2: number; y2: number; dimmed: boolean }> = []
  for (const edge of graph.value?.edges ?? []) {
    const from = positions.value.get(edge.source)
    const to = positions.value.get(edge.target)
    if (!from || !to) continue
    lines.push({
      key: `${edge.source}->${edge.target}`,
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      dimmed: Boolean(selectedId.value) && selectedId.value !== edge.source && selectedId.value !== edge.target,
    })
  }
  return lines
})

const selected = computed(() => (graph.value?.nodes ?? []).find((node) => node.id === selectedId.value) ?? null)

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
  const types: string[] = []
  for (const node of graph.value?.nodes ?? []) {
    const type = node.entity_type || 'other'
    if (!types.includes(type)) types.push(type)
    if (types.length >= LEGEND_LIMIT) break
  }
  return types.map((type) => ({ type, label: typeLabel(type), color: typeColor(type) }))
})

// ─── 视图缩放 / 平移：150 个节点在固定画布里会挤成一团，必须能放大看局部 ───
const viewBox = ref({ x: 0, y: 0, w: CANVAS_WIDTH, h: CANVAS_HEIGHT })
const viewBoxAttr = computed(
  () => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.w} ${viewBox.value.h}`,
)
const dragging = ref(false)
let dragOrigin: { x: number; y: number; vx: number; vy: number } | null = null
let moved = false

function resetView() {
  viewBox.value = { x: 0, y: 0, w: CANVAS_WIDTH, h: CANVAS_HEIGHT }
}

function onWheel(event: WheelEvent) {
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  const factor = event.deltaY > 0 ? 1.12 : 0.89
  const nextW = Math.min(CANVAS_WIDTH * 2.5, Math.max(CANVAS_WIDTH / 5, viewBox.value.w * factor))
  const nextH = (nextW * CANVAS_HEIGHT) / CANVAS_WIDTH
  const ratioX = (event.clientX - rect.left) / rect.width
  const ratioY = (event.clientY - rect.top) / rect.height
  viewBox.value = {
    x: viewBox.value.x + (viewBox.value.w - nextW) * ratioX,
    y: viewBox.value.y + (viewBox.value.h - nextH) * ratioY,
    w: nextW,
    h: nextH,
  }
}

function onPointerDown(event: PointerEvent) {
  dragging.value = true
  moved = false
  dragOrigin = {
    x: event.clientX,
    y: event.clientY,
    vx: viewBox.value.x,
    vy: viewBox.value.y,
  }
  ;(event.currentTarget as SVGSVGElement).setPointerCapture?.(event.pointerId)
}

function onPointerMove(event: PointerEvent) {
  if (!dragOrigin) return
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect()
  if (Math.abs(event.clientX - dragOrigin.x) + Math.abs(event.clientY - dragOrigin.y) > 3) {
    moved = true
  }
  viewBox.value = {
    ...viewBox.value,
    x: dragOrigin.vx - ((event.clientX - dragOrigin.x) * viewBox.value.w) / rect.width,
    y: dragOrigin.vy - ((event.clientY - dragOrigin.y) * viewBox.value.h) / rect.height,
  }
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
  if (selectedId.value) ids.add(selectedId.value)
  const total = placed.value.length
  const threshold = total > 80 ? 8 : total > 40 ? 4 : 2
  for (const item of placed.value) {
    if (ids.size >= 14) break
    if (item.node.degree >= threshold) ids.add(item.node.id)
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

/** 按实体类型稳定取色，同一类型在刷新前后保持一致。 */
function typeColor(type: string) {
  let hash = 0
  for (const char of type || 'other') hash = (hash * 31 + char.charCodeAt(0)) % 9973
  return TYPE_COLORS[hash % TYPE_COLORS.length]
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
  height: calc(100vh - 280px);
  min-height: 380px;
  background: var(--bg-elevated, #f7f8fa);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 12px;
}

.graph-canvas.dragging {
  cursor: grabbing;
}

.graph-node {
  cursor: pointer;
  transition: opacity 0.15s ease;
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
  fill: var(--text-secondary, #4b5563);
  pointer-events: none;
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
