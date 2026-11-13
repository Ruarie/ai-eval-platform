<template>
  <!-- 悬停详情 tooltip -->
  <div v-if="tooltip" class="topo-tip" :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
    <div class="tt-title">{{ tooltip.title }}</div>
    <div v-for="(ln, i) in tooltip.lines" :key="i" class="tt-line">
      <span class="tertiary">{{ ln[0] }}</span><span class="tt-val">{{ ln[1] }}</span>
    </div>
  </div>

  <!-- 工单锁定详情卡 -->
  <div v-if="pinnedTask && pinnedPos" class="pin-card" :style="{ left: pinnedPos.x + 'px', top: pinnedPos.y + 'px' }">
    <div class="pc-head">
      <i class="pc-bar" :style="{ background: props.kindColor(pinnedTask.kind) }"></i>
      <span class="mono pc-id">{{ pinnedTask.shortId }}</span>
      <span class="badge" :class="`badge-${pinnedTask.status}`">{{ props.statusLabel(pinnedTask.status) }}</span>
      <span class="grow"></span>
      <button class="pc-close" title="解锁（Esc）" @click="emit('unpin')">×</button>
    </div>
    <div class="pc-label">{{ pinnedTask.label }}</div>
    <div v-if="pinnedTask.status === 'running' && pinnedTask.progress != null" class="pc-progress">
      <i :style="{ width: `${pinnedTask.progress}%` }"></i>
    </div>
    <div class="pc-lines">
      <div class="tt-line"><span class="tertiary">执行节点</span><span class="tt-val mono">{{ pinnedTask.workerId || '排队待分发' }}</span></div>
      <div v-if="pinnedTask.progress != null" class="tt-line"><span class="tertiary">进度</span><span class="tt-val mono">{{ pinnedTask.progress }}%</span></div>
      <div v-if="pinnedTask.parentId" class="tt-line"><span class="tertiary">派生自</span><span class="tt-val mono">{{ pinnedTask.parentId.substring(0, 8) }}</span></div>
    </div>
    <div class="row" style="gap: 6px; margin-top: 8px">
      <button class="btn btn-secondary btn-sm grow" @click="emit('open-task', pinnedTask.id)">在任务中心查看 ↗</button>
      <button v-if="pinnedTask.status === 'succeeded'" class="btn btn-ai btn-sm" @click="emit('open-report', pinnedTask.id)">查看报告 📊</button>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 星图浮层：悬停详情与工单锁定卡，只负责渲染与事件上报。 */
interface TopoTooltip {
  x: number
  y: number
  title: string
  lines: [string, string][]
}
interface PinnedTask {
  id: string
  shortId: string
  kind: string
  status: string
  label: string
  progress?: number | null
  workerId?: string | null
  parentId?: string | null
}

const props = defineProps<{
  tooltip: TopoTooltip | null
  pinnedTask: PinnedTask | null
  pinnedPos: { x: number; y: number } | null
  kindColor: (kind: string) => string
  statusLabel: (status: string) => string
}>()

const emit = defineEmits<{
  (event: 'unpin'): void
  (event: 'open-task', taskId: string): void
  (event: 'open-report', taskId: string): void
}>()
void props
</script>

<style scoped>
.topo-tip {
  position: absolute;
  z-index: 25;
  min-width: 180px;
  max-width: 250px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-main);
  box-shadow: 0 8px 24px rgba(17, 24, 39, 0.14);
  pointer-events: none;
  font-size: 11.5px;
}
.tt-title {
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 6px;
}
.tt-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  line-height: 1.8;
}
.tt-val {
  text-align: right;
  word-break: break-all;
}
.pin-card {
  position: absolute;
  z-index: 25;
  width: 228px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent-ai) 40%, var(--border-subtle));
  background: var(--bg-main);
  box-shadow: 0 10px 28px rgba(17, 24, 39, 0.18), 0 0 0 1px color-mix(in srgb, var(--accent-ai) 14%, transparent);
  font-size: 11.5px;
  animation: pin-in 0.18s ease;
}
.pc-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pc-bar {
  width: 3.5px;
  height: 14px;
  border-radius: 2px;
  flex: 0 0 3.5px;
}
.pc-id {
  font-weight: 700;
  font-size: 11.5px;
}
.pc-close {
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 4px;
}
.pc-close:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.pc-label {
  margin-top: 6px;
  font-weight: 500;
  line-height: 1.45;
  word-break: break-all;
}
.pc-progress {
  margin-top: 6px;
  height: 4px;
  border-radius: 999px;
  background: var(--bg-elevated);
  overflow: hidden;
}
.pc-progress > i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: repeating-linear-gradient(45deg, var(--accent-ai) 0 8px, color-mix(in srgb, var(--accent-ai) 55%, #fff) 8px 16px);
  background-size: 23px 100%;
  animation: bar-stripes 0.9s linear infinite;
  transition: width 0.4s ease;
}
.pc-lines {
  margin-top: 6px;
}

/* ── 自父视图补回的基础样式（拆分迁移时遗漏） ── */

@media (max-width: 768px) {
.dock-bottom-header .row {
    display: none;
  }
}

/* ── 补回动画关键帧 ── */
@keyframes pin-in {
  from { opacity: 0; transform: translateY(4px) scale(0.97); }
  to { opacity: 1; transform: none; }
}
@keyframes bar-stripes {
  to { background-position: 23px 0; }
}
</style>
