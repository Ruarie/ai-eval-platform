<template>
    <div class="kpi-grid mb16" data-od-id="dispatch-kpis" style="--glow-c: var(--c-agent)">
      <div class="kpi kpi-glow">
        <div class="kpi-num num">{{ ready ? online + ' / ' + totalWorkers : '—' }}</div>
        <div class="kpi-label">在线 Worker 节点</div>
      </div>
      <div class="kpi kpi-trend kpi-glow">
        <div class="kpi-num num">{{ ready ? queue : '—' }}</div>
        <div class="kpi-label">排队队列深度</div>
        <svg class="spark" viewBox="0 0 76 24" preserveAspectRatio="none"><polyline :points="sparkPoints(histQueue)" /></svg>
      </div>
      <div class="kpi kpi-trend kpi-glow">
        <div class="kpi-num num">{{ ready ? running : '—' }}</div>
        <div class="kpi-label">运行中任务</div>
        <svg class="spark" viewBox="0 0 76 24" preserveAspectRatio="none"><polyline :points="sparkPoints(histRunning)" /></svg>
      </div>
      <div class="kpi kpi-trend kpi-glow">
        <div class="kpi-num num">{{ ready ? cost : '—' }}<span class="unit">ms</span></div>
        <div class="kpi-label">平均分发调度延迟</div>
        <svg class="spark" viewBox="0 0 76 24" preserveAspectRatio="none"><polyline :points="sparkPoints(histCost)" /></svg>
      </div>
      <div class="kpi kpi-trend kpi-glow">
        <div class="kpi-num num">{{ ready ? assigned : '—' }}</div>
        <div class="kpi-label">今日已分配任务</div>
        <svg class="spark" viewBox="0 0 76 24" preserveAspectRatio="none"><polyline :points="sparkPoints(histAssigned)" /></svg>
      </div>
    </div>
</template>

<script setup lang="ts">
import { sparkPoints } from '../../utils/sparkline'

/**
 * 调度大盘 KPI 趋势带：只做展示，指标与历史序列由页面下发。
 * 样式定义在全局 base.css（.kpi / .kpi-grid / .kpi-num），组件不携带 scoped 样式。
 */
defineProps<{
  ready: boolean
  online: number
  totalWorkers: number
  queue: number
  running: number
  cost: number
  assigned: number
  histQueue: number[]
  histRunning: number[]
  histCost: number[]
  histAssigned: number[]
}>()
</script>
