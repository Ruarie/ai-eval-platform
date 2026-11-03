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
              <i :style="{ background: item.color }"></i>{{ item.type }}
            </span>
            <button class="btn btn-secondary btn-sm" @click="load">刷新</button>
          </div>
        </div>

        <div v-if="!graph?.nodes.length" class="graph-state">
          当前库还没有抽出实体：请先上传文档并等待索引状态变为 indexed，图谱由索引阶段的实体抽取产生。
        </div>

        <div v-else class="graph-body">
          <svg
            class="graph-canvas"
            :viewBox="`0 0 ${CANVAS_WIDTH} ${CANVAS_HEIGHT}`"
            preserveAspectRatio="xMidYMid meet"
            role="img"
            aria-label="知识图谱实体关系图"
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
              @click="selectedId = selectedId === item.node.id ? '' : item.node.id"
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
                v-if="item.node.degree >= 2 || item.node.id === selectedId"
                :x="item.x"
                :y="item.y - item.radius - 5"
                text-anchor="middle"
                class="graph-label"
              >
                {{ item.node.id }}
              </text>
            </g>
          </svg>

          <aside class="graph-side">
            <template v-if="selected">
              <div class="side-title">{{ selected.id }}</div>
              <div class="side-row">
                <span class="small tertiary">类型</span>
                <span class="chip">{{ selected.entity_type || '未标注' }}</span>
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
import type { KbGraph, KbGraphEdge, KbGraphNode } from '../../api/types'

const props = defineProps<{
  show: boolean
  kbId: string
  kbName?: string
  docs?: Array<{ doc_id: string; filename: string }>
}>()

const emit = defineEmits<{ (event: 'update:show', value: boolean): void }>()

const CANVAS_WIDTH = 820
const CANVAS_HEIGHT = 520
const PADDING = 44
const ITERATIONS = 160
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
    graph.value = await api.kb.getGraph(props.kbId, 150)
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

/** 力导向布局：斥力 + 边引力 + 向心引力，迭代固定次数后一次性渲染（不做持续动画）。 */
function layout(nodes: KbGraphNode[], edges: KbGraphEdge[]): PlacedNode[] {
  const total = nodes.length
  if (!total) return []

  const centerX = CANVAS_WIDTH / 2
  const centerY = CANVAS_HEIGHT / 2
  const usableWidth = CANVAS_WIDTH - PADDING * 2
  const usableHeight = CANVAS_HEIGHT - PADDING * 2
  const ideal = Math.sqrt((usableWidth * usableHeight) / total) * 0.75
  const xs: number[] = []
  const ys: number[] = []
  const indexOf = new Map<string, number>()

  nodes.forEach((node, index) => {
    const angle = (index / total) * Math.PI * 2
    // 度数最高的前 8 个实体放在内圈，核心实体不被挤到画布边缘。
    const ring = index < 8 ? 0.52 : 1
    xs.push(centerX + Math.cos(angle) * usableWidth * 0.34 * ring)
    ys.push(centerY + Math.sin(angle) * usableHeight * 0.34 * ring)
    indexOf.set(node.id, index)
  })

  for (let step = 0; step < ITERATIONS; step += 1) {
    const dx = new Array<number>(total).fill(0)
    const dy = new Array<number>(total).fill(0)

    for (let i = 0; i < total; i += 1) {
      for (let j = i + 1; j < total; j += 1) {
        let vx = xs[i] - xs[j]
        let vy = ys[i] - ys[j]
        let distance = Math.hypot(vx, vy)
        if (distance < 0.01) {
          vx = 0.01 * (i - j + 1)
          vy = 0.01
          distance = Math.hypot(vx, vy)
        }
        const force = (ideal * ideal) / distance
        const ux = (vx / distance) * force
        const uy = (vy / distance) * force
        dx[i] += ux
        dy[i] += uy
        dx[j] -= ux
        dy[j] -= uy
      }
    }

    for (const edge of edges) {
      const from = indexOf.get(edge.source)
      const to = indexOf.get(edge.target)
      if (from === undefined || to === undefined || from === to) continue
      const vx = xs[from] - xs[to]
      const vy = ys[from] - ys[to]
      const distance = Math.max(Math.hypot(vx, vy), 0.01)
      const force = (distance * distance) / ideal / 40
      const ux = (vx / distance) * force
      const uy = (vy / distance) * force
      dx[from] -= ux
      dy[from] -= uy
      dx[to] += ux
      dy[to] += uy
    }

    for (let i = 0; i < total; i += 1) {
      dx[i] += (centerX - xs[i]) * 0.02
      dy[i] += (centerY - ys[i]) * 0.02
      const length = Math.hypot(dx[i], dy[i]) || 1
      const stepSize = Math.min(length, 12)
      xs[i] = Math.min(CANVAS_WIDTH - PADDING, Math.max(PADDING, xs[i] + (dx[i] / length) * stepSize))
      ys[i] = Math.min(CANVAS_HEIGHT - PADDING, Math.max(PADDING, ys[i] + (dy[i] / length) * stepSize))
    }
  }

  return nodes.map((node, index) => ({
    node,
    x: xs[index],
    y: ys[index],
    radius: 6 + Math.min(10, node.degree * 1.6),
  }))
}

const placed = computed(() => layout(graph.value?.nodes ?? [], graph.value?.edges ?? []))

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
    const type = node.entity_type || '未标注'
    if (!types.includes(type)) types.push(type)
    if (types.length >= LEGEND_LIMIT) break
  }
  return types.map((type) => ({ type, color: typeColor(type) }))
})

function isDimmed(nodeId: string) {
  if (!selectedId.value) return false
  return nodeId !== selectedId.value && !neighbours.value.has(nodeId)
}

/** 按实体类型稳定取色，同一类型在刷新前后保持一致。 */
function typeColor(type: string) {
  let hash = 0
  for (const char of type || '未标注') hash = (hash * 31 + char.charCodeAt(0)) % 9973
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

.graph-node {
  cursor: pointer;
  transition: opacity 0.15s ease;
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
