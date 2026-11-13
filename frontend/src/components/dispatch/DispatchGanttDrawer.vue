<template>
  <div class="floating-dock dock-bottom" :class="{ collapsed: collapsed }">
    <div class="dock-header dock-bottom-header" @click="emit('update:collapsed', !collapsed)">
      <div class="dock-header-title">
        <span class="dock-ico">⏱</span>
        <span class="dock-title-text font-bold">先评后压全链路编排甘特图</span>
        <span class="dock-subtitle tertiary small">（多阶段流转与父子派生闭环）</span>
      </div>
      <div class="row" style="gap: 8px; font-size: 11px; margin-left: auto; margin-right: 12px">
        <span v-for="lg in legend" :key="lg.label" class="row" style="gap: 4px; align-items: center">
          <i class="gantt-dot" :style="{ background: lg.color }"></i>
          <span class="tertiary" style="font-size: 10px">{{ lg.label }}</span>
        </span>
      </div>
      <button class="dock-toggle-btn" :title="collapsed ? '展开甘特抽屉' : '收折甘特抽屉'">
        {{ collapsed ? '▲ 展开' : '▼ 收起' }}
      </button>
    </div>

    <div v-show="!collapsed" class="dock-bottom-content">
      <div v-if="rows.length" class="gantt">
        <div class="gantt-axis">
          <span v-for="(tick, i) in props.ticks" :key="i" class="mono">{{ tick }}</span>
        </div>
        <div
          v-for="row in rows"
          :key="row.id"
          class="gantt-row"
          :class="{ child: row.isChild }"
          :title="`${row.label}\n${props.statusLabel(row.status)} · ${props.fmtTime(row.start)} → ${props.fmtTime(row.end)}\n点击前往任务中心查看详情`"
          @click="emit('open-task', row.id)"
        >
          <div class="gantt-name">
            <span v-if="row.isChild" class="tertiary" style="font-size: 10px">↳ 派生压测</span>
            <KindTag :kind="row.kind" />
            <span class="mono gantt-tid" style="font-size: 10.5px">{{ row.shortId }}</span>
          </div>
          <div class="gantt-track">
            <div
              class="gantt-bar"
              :class="`st-${row.status}`"
              :style="{ left: row.left + '%', width: Math.max(10, row.width) + '%' }"
            >
              <span class="gantt-bar-text">{{ props.statusLabel(row.status) }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-else class="empty" style="padding: 16px 10px">
        <div class="small tertiary">暂无任务记录，发起评测任务后此处将展示完整阶段编排流转</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 底部甘特抽屉：只渲染阶段编排与图例，折叠/展开由页面持有。 */
interface GanttRow {
  id: string
  kind: string
  label: string
  status: string
  left: number
  width: number
  start: number
  end: number
  isChild?: boolean
  shortId?: string
}
interface GanttLegendItem {
  label: string
  color: string
}

const props = defineProps<{
  collapsed: boolean
  rows: GanttRow[]
  legend: GanttLegendItem[]
  /** 时间刻度文案（4 档百分比换算后的时间）。 */
  ticks: string[]
  statusLabel: (status: string) => string
  fmtTime: (value: number) => string
}>()

const emit = defineEmits<{
  (event: 'update:collapsed', value: boolean): void
  (event: 'open-task', taskId: string): void
}>()
void props
</script>

<style scoped>
.floating-dock {
  position: absolute;
  z-index: 20;
  background: rgba(var(--bg-main-rgb, 17, 24, 39), 0.92);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
}
.dock-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle);
  user-select: none;
  flex-shrink: 0;
}
.dock-header-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-primary);
}
.dock-ico {
  font-size: 14px;
}
.dock-toggle-btn {
  border: none;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.dock-toggle-btn:hover {
  background: var(--accent-ai);
  color: #fff;
}
.dock-left.collapsed {
  width: 44px;
  overflow: hidden;
}
.dock-left.collapsed .dock-header {
  padding: 8px 6px;
  justify-content: center;
}
.dock-right.collapsed {
  width: 44px;
  overflow: hidden;
}
.dock-right.collapsed .dock-header {
  padding: 8px 6px;
  justify-content: center;
}
.dock-bottom {
  bottom: 14px;
  left: 14px;
  right: 14px;
  max-height: 240px;
}
.dock-bottom.collapsed {
  max-height: 38px;
  overflow: hidden;
}
.dock-bottom-header {
  cursor: pointer;
  padding: 6px 12px;
}
.dock-bottom-content {
  padding: 8px 12px;
  overflow-y: auto;
  max-height: 180px;
}
.gantt {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.gantt-axis {
  display: flex;
  justify-content: space-between;
  font-size: 9.5px;
  color: var(--text-tertiary);
  padding: 0 4px 2px 160px;
}
.gantt-row {
  display: grid;
  grid-template-columns: 160px 1fr;
  align-items: center;
  gap: 8px;
  padding: 2px 4px;
  border-radius: 5px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.gantt-row:hover {
  background: var(--row-hover);
}
.gantt-row.child .gantt-name {
  padding-left: 10px;
}
.gantt-name {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
}
.gantt-tid {
  color: var(--text-secondary);
}
.gantt-track {
  position: relative;
  height: 16px;
  border-radius: 4px;
  background: var(--bg-elevated);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
}
.gantt-bar {
  position: absolute;
  top: 1px;
  bottom: 1px;
  border-radius: 3px;
  display: flex;
  align-items: center;
  padding-left: 5px;
  transition: left 0.6s ease, width 0.6s ease;
}
.gantt-bar-text {
  font-size: 8.5px;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}
.gantt-bar.st-queued { background: #9ca3af; }
.gantt-bar.st-running {
  background: repeating-linear-gradient(45deg, var(--accent-ai) 0 8px, color-mix(in srgb, var(--accent-ai) 55%, #fff) 8px 16px);
  background-size: 23px 100%;
  animation: bar-stripes 0.9s linear infinite;
}
.gantt-bar.st-awaiting_case_confirm { background: var(--accent-warning); }
.gantt-bar.st-succeeded { background: var(--accent-success); }
.gantt-bar.st-failed,
.gantt-bar.st-cancelled { background: var(--accent-error); opacity: 0.75; }
.gantt-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 2px;
}
.dock-bottom {
    left: 10px;
    right: 10px;
    bottom: 10px;
    max-height: 220px;
    z-index: 35;
  }
.dock-bottom-header {
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px 10px;
  }
.dock-bottom-header .row {
    display: none;
  }
.gantt-row {
    grid-template-columns: 100px 1fr;
  }
.gantt-axis {
    padding-left: 100px;
  }
.gantt-name {
    font-size: 10px;
  }
.panel-title .small {
    display: none;
  }
</style>
