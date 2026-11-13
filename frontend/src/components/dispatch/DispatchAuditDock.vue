<template>
  <div class="floating-dock dock-right" :class="{ collapsed: collapsed }">
    <div class="dock-header">
      <button class="dock-toggle-btn" :title="collapsed ? '展开审计面板' : '收折审计面板'" @click="emit('update:collapsed', !collapsed)">
        {{ collapsed ? '⇤' : '⇥' }}
      </button>
      <div class="dock-header-title">
        <span class="dock-ico">📋</span>
        <span v-show="!collapsed" class="dock-title-text font-bold">调度事件审计流</span>
      </div>
      <button v-show="!collapsed" class="link-btn" style="font-size: 10.5px; margin-left: auto" @click="emit('clear')">清空</button>
    </div>

    <div v-show="!collapsed" class="dock-scroll-content">
      <div class="chip-group mb8" style="gap: 4px">
        <button
          v-for="c in categories"
          :key="c.key"
          class="chip chip-xs"
          :class="{ on: category === c.key }"
          @click="emit('update:category', c.key)"
        >
          {{ c.label }}
        </button>
      </div>

      <div class="log-stream">
        <div
          v-for="(l, idx) in logs"
          :key="idx"
          class="log-card-item"
          :class="[`cat-${l.cat}`, { clickable: !!l.tid }]"
          :title="l.tid ? '点击定位并高亮星图工单' : ''"
          @click="l.tid && emit('flash-task', l.tid)"
        >
          <div class="lci-head">
            <span class="lci-time mono">{{ l.time }}</span>
            <span class="lci-tag" :class="l.cat">{{ l.kind }}</span>
            <span v-if="l.tid" class="lci-tid mono">{{ l.tid.substring(0, 8) }}</span>
          </div>
          <div class="lci-body" v-html="l.html"></div>
        </div>
        <div v-if="!logs.length" class="empty" style="padding: 28px 10px">
          <div class="small tertiary">暂无调度事件流</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 调度事件审计坞：只负责渲染与筛选交互，日志本身由页面采集。 */
interface AuditLogEntry {
  cat: string
  kind: string
  time: string
  tid?: string
  html: string
}

const props = defineProps<{
  collapsed: boolean
  categories: { key: string; label: string }[]
  category: string
  logs: AuditLogEntry[]
}>()

const emit = defineEmits<{
  (event: 'update:collapsed', value: boolean): void
  (event: 'update:category', value: string): void
  (event: 'clear'): void
  (event: 'flash-task', taskId: string): void
}>()

// props 在模板中直接使用，保持与页面的单向数据流
void props
</script>

<style scoped>
.sector-wedge.dim {
  opacity: 0.015;
}
.wire-core.dim,
.wire-member.dim,
.wire-live.dim {
  opacity: 0.08;
}
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
.dock-scroll-content {
  padding: 10px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(100vh - 360px);
}
.dock-left.collapsed {
  width: 44px;
  overflow: hidden;
}
.dock-left.collapsed .dock-header {
  padding: 8px 6px;
  justify-content: center;
}
.dock-right {
  top: 14px;
  right: 14px;
  width: 320px;
}
.dock-right.collapsed {
  width: 44px;
  overflow: hidden;
}
.dock-right.collapsed .dock-header {
  padding: 8px 6px;
  justify-content: center;
}
.dock-bottom.collapsed {
  max-height: 38px;
  overflow: hidden;
}
.worker-rich-card.busy {
  border-color: color-mix(in srgb, var(--accent-ai) 40%, var(--border-subtle));
}
.worker-rich-card.offline {
  opacity: 0.55;
}
.wrc-dot.idle { background: var(--accent-success); }
.wrc-dot.busy { background: var(--accent-ai); animation: dot-breathe 1.4s ease-in-out infinite; }
.wrc-dot.draining { background: var(--accent-warning); }
.wrc-state-tag.idle { color: var(--accent-success); }
.wrc-state-tag.busy { color: var(--accent-ai); }
.log-card-item {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 6px 8px;
  margin-bottom: 5px;
  transition: background 0.15s ease;
}
.log-card-item.clickable {
  cursor: pointer;
}
.log-card-item.clickable:hover {
  border-color: var(--accent-ai);
  background: var(--row-hover);
}
.lci-head {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 2px;
}
.lci-time {
  font-size: 9.5px;
  color: var(--text-tertiary);
}
.lci-tag {
  font-size: 9px;
  padding: 0 4px;
  border-radius: 3px;
  font-weight: 600;
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
}
.lci-tag.done { color: var(--accent-success); border-color: color-mix(in srgb, var(--accent-success) 30%, transparent); }
.lci-tag.error { color: var(--accent-error); border-color: color-mix(in srgb, var(--accent-error) 30%, transparent); }
.lci-tag.node { color: var(--text-secondary); }
.lci-tid {
  font-size: 9px;
  color: var(--accent-ai);
  margin-left: auto;
}
.lci-body {
  font-size: 10.5px;
  line-height: 1.35;
  color: var(--text-primary);
}
.task-chip.dim,
.skill-node.dim,
.worker-node.dim {
  opacity: 0.18;
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
.tc-dot.running {
  fill: var(--accent-ai);
  animation: dot-breathe 1.4s ease-in-out infinite;
}
.tc-dot.awaiting_case_confirm {
  fill: var(--accent-warning);
}
.skill-node.on .sn-halo {
  opacity: 0.22;
  animation: halo-breathe 2.2s ease-in-out infinite;
}
.skill-node:hover .sn-core,
.skill-node.on .sn-core {
  stroke-width: 2.4;
}
.worker-node.busy .wn-core {
  stroke: color-mix(in srgb, var(--accent-ai) 55%, var(--border-subtle));
  filter: drop-shadow(0 0 5px color-mix(in srgb, var(--accent-ai) 35%, transparent));
}
.worker-node.offline {
  opacity: 0.4;
}
.wn-dot.idle { fill: var(--accent-success); }
.wn-dot.busy { fill: var(--accent-ai); animation: dot-breathe 1.4s ease-in-out infinite; }
.wn-dot.draining { fill: var(--accent-warning); }
.tab-pill-btn.active {
  background: var(--bg-main);
  color: var(--text-primary);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
</style>
