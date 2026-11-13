<template>
  <div class="floating-dock dock-left" :class="{ collapsed: collapsed }">
    <div class="dock-header">
      <div class="dock-header-title">
        <span class="dock-ico">🛰</span>
        <span v-show="!collapsed" class="dock-title-text font-bold">调度内核与算力</span>
      </div>
      <button class="dock-toggle-btn" :title="collapsed ? '展开左侧面板' : '收折左侧面板'" @click="emit('update:collapsed', !collapsed)">
        {{ collapsed ? '⇥' : '⇤' }}
      </button>
    </div>

    <div v-show="!collapsed" class="dock-scroll-content">
      <!-- 调度内核状态与指标 -->
      <div class="dock-card mb10">
        <div class="dock-card-title">
          <span>内核状态</span>
          <span class="badge" :class="isRunning ? 'badge-running' : 'badge-cancelled'">
            <i class="bdot"></i>{{ kernelStateLabel }}
          </span>
        </div>
        <div class="kernel-metric-row mb8">
          <div class="k-stat">
            <span class="k-label tertiary">健康度</span>
            <!-- 契约未提供健康度指标，不再用固定 99.4% 冒充真实值 -->
            <span class="k-val font-bold" :style="{ color: 'var(--text-tertiary)' }">—</span>
          </div>
          <div class="k-stat">
            <span class="k-label tertiary">活跃并发</span>
            <span class="k-val font-bold mono" style="color: var(--accent-ai)">{{ overviewReady ? runningCount + '/' + capacity : '—' }}</span>
          </div>
          <div class="k-stat">
            <span class="k-label tertiary">心跳</span>
            <span class="k-val font-bold mono">{{ overviewReady ? heartbeatMs + 'ms' : '—' }}</span>
          </div>
        </div>
        <div class="row" style="gap: 6px">
          <button
            class="btn btn-secondary btn-xs"
            style="flex: 1"
            :disabled="schedulerBusy"
            @click="emit('toggle-scheduler')"
          >
            {{ isRunning ? '⏸ 暂停' : '▶ 恢复' }}
          </button>
          <button class="btn btn-primary btn-xs" style="flex: 1" @click="emit('register-worker')">
            + 注册节点
          </button>
        </div>
      </div>

      <!-- 分发策略与并发滑块 -->
      <div class="dock-card mb10">
        <div class="dock-card-title">分发策略</div>
        <div class="chip-group mb8">
          <button
            v-for="s in ['负载均衡', '优先级抢占', '亲和性']"
            :key="s"
            class="chip chip-xs"
            :class="{ on: strategy === s }"
            @click="emit('strategy-change', s)"
          >
            {{ s }}
          </button>
        </div>
        <div class="field" style="margin: 6px 0 0">
          <div class="row-between">
            <span class="field-label" style="margin: 0; font-size: 11px">并发容量</span>
            <b class="num font-bold" style="color: var(--accent-ai); font-size: 13px">{{ overviewReady ? capacity : '—' }}</b>
          </div>
          <input
            :value="capacity"
            type="range"
            class="cap-slider"
            min="1"
            max="8"
            step="1"
            style="margin-top: 4px"
            :disabled="!overviewReady"
            @change="emit('capacity-change', Number(($event.target as HTMLInputElement).value))"
          />
        </div>
      </div>

      <!-- Worker 专精计算节点池 -->
      <div class="dock-card mb10">
        <div class="dock-card-title">
          <span>Worker 专精集群</span>
          <span class="small tertiary mono">{{ onlineCount }}/{{ totalWorkers }} 在线</span>
        </div>
        <div class="worker-card-list">
          <div
            v-for="w in workers"
            :key="w.id"
            class="worker-rich-card"
            :class="w.state"
            @click="emit('open-worker', w)"
          >
            <div class="wrc-head">
              <span class="wrc-dot" :class="w.state"></span>
              <span class="wrc-name font-bold">{{ w.name }}</span>
              <span class="wrc-state-tag" :class="w.state">{{ props.stateLabel(w.state) }}</span>
            </div>
            <div class="wrc-body">
              <div class="wrc-caps">
                <span v-for="c in w.caps" :key="c" class="cap-tag">{{ c }}</span>
              </div>
              <div class="wrc-load-wrap">
                <span class="wrc-load-text mono small">{{ w.load }}%</span>
                <div class="wrc-load-bar">
                  <div class="wrc-load-fill" :style="{ width: `${w.load}%`, background: w.load > 70 ? 'var(--accent-warning)' : 'var(--accent-ai)' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI 调度调优建议 -->
      <div class="dock-card ai-dock-card">
        <div class="dock-card-title">
          <span class="ai-badge"><i class="ai-dot"></i>AI 调度优化建议</span>
          <button class="link-btn" style="font-size: 11px" @click="emit('next-advice')">换一条</button>
        </div>
        <div class="small" style="line-height: 1.45; color: var(--text-secondary); margin-top: 4px">
          {{ advice }}
        </div>
        <div class="row mt6" style="justify-content: flex-end">
          <button class="btn btn-ai btn-xs" @click="emit('apply-advice')">采纳建议</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 左侧调度控制坞：内核指标、并发容量、分发策略、Worker 概览与 AI 调优建议。 */
interface DockWorker {
  id: string
  name: string
  state: string
  load: number
  caps: string[]
}

const props = defineProps<{
  collapsed: boolean
  overviewReady: boolean
  isRunning: boolean
  strategy: string
  capacity: number
  schedulerBusy: boolean
  workers: DockWorker[]
  onlineCount: number
  totalWorkers: number
  runningCount: number
  heartbeatMs: number
  kernelStateLabel: string
  advice: string
  stateLabel: (state: string) => string
}>()

const emit = defineEmits<{
  (event: 'update:collapsed', value: boolean): void
  (event: 'capacity-change', value: number): void
  (event: 'strategy-change', strategy: string): void
  (event: 'toggle-scheduler'): void
  (event: 'register-worker'): void
  (event: 'open-worker', worker: DockWorker): void
  (event: 'next-advice'): void
  (event: 'apply-advice'): void
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
.dock-scroll-content {
  padding: 10px;
  overflow-y: auto;
  flex: 1;
  max-height: calc(100vh - 360px);
}
.dock-card {
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 8px 10px;
}
.dock-card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
  font-weight: 600;
  margin-bottom: 6px;
}
.dock-left {
  top: 14px;
  left: 14px;
  width: 290px;
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
.dock-bottom.collapsed {
  max-height: 38px;
  overflow: hidden;
}
.kernel-metric-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  background: var(--bg-elevated);
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
}
.k-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 2px;
}
.k-label {
  font-size: 9.5px;
}
.k-val {
  font-size: 11.5px;
}
.worker-card-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.worker-rich-card {
  background: var(--bg-elevated);
  border: 1px solid var(--border-subtle);
  border-radius: 6px;
  padding: 6px 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.worker-rich-card:hover {
  border-color: var(--accent-ai);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.worker-rich-card.busy {
  border-color: color-mix(in srgb, var(--accent-ai) 40%, var(--border-subtle));
}
.worker-rich-card.offline {
  opacity: 0.55;
}
.wrc-head {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
}
.wrc-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--text-tertiary);
}
.wrc-dot.idle { background: var(--accent-success); }
.wrc-dot.busy { background: var(--accent-ai); animation: dot-breathe 1.4s ease-in-out infinite; }
.wrc-dot.draining { background: var(--accent-warning); }
.wrc-name {
  font-size: 11px;
  color: var(--text-primary);
}
.wrc-state-tag {
  margin-left: auto;
  font-size: 9px;
  padding: 0 4px;
  border-radius: 3px;
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.wrc-state-tag.idle { color: var(--accent-success); }
.wrc-state-tag.busy { color: var(--accent-ai); }
.wrc-body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.wrc-caps {
  display: flex;
  gap: 3px;
  flex-wrap: wrap;
}
.cap-tag {
  font-size: 8.5px;
  font-family: var(--font-mono);
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
  padding: 0 3px;
  border-radius: 2px;
  color: var(--text-tertiary);
}
.wrc-load-wrap {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.wrc-load-text {
  font-size: 9.5px;
  color: var(--text-secondary);
}
.wrc-load-bar {
  width: 32px;
  height: 3.5px;
  background: var(--bg-main);
  border-radius: 2px;
  overflow: hidden;
}
.wrc-load-fill {
  height: 100%;
  transition: width 0.3s;
}
.tab-pill-btn.active {
  background: var(--bg-main);
  color: var(--text-primary);
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}
.dock-left {
    width: 260px;
  }
.dock-left,
  .dock-right {
    width: min(320px, calc(100vw - 32px));
    z-index: 40;
    box-shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
  }
.dock-left {
    left: 12px;
    top: 12px;
  }
.dock-scroll-content {
    max-height: 44vh;
  }
.dock-bottom-header .row {
    display: none;
  }
.panel-title .small {
    display: none;
  }
.dock-left,
  .dock-right {
    width: calc(100vw - 24px);
    left: 12px;
    right: 12px;
  }
</style>
