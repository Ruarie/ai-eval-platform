<template>
  <div class="quality-page">
    <header class="page-head">
      <div>
        <h1>用例质量看板</h1>
        <p class="page-sub">按已落库的生成任务、用例集、评审与 AI 评分聚合，最多扫描最近 1000 条运行；覆盖率不等于功能正确。</p>
      </div>
      <div class="page-actions">
        <div class="range-switch" role="group" aria-label="统计时间范围">
          <button
            v-for="option in rangeOptions"
            :key="option.value"
            class="range-btn"
            :class="{ active: days === option.value }"
            @click="changeRange(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="loading && !data" class="panel empty-state">正在汇总质量数据…</div>

    <div v-else-if="error" class="panel empty-state">
      <p>{{ error }}</p>
      <button class="btn btn-secondary btn-sm" @click="load">重试</button>
    </div>

    <template v-else-if="data">
      <div v-if="!data.total_runs" class="panel empty-state">
        当前时间范围内没有用例生成任务。去「用例」页从 PRD 生成一批候选后再回来查看。
      </div>

      <template v-else>
        <section class="kpi-grid">
          <div class="kpi">
            <div class="kpi-num">{{ data.total_runs }}</div>
            <div class="kpi-label">生成运行</div>
            <div class="kpi-hint">{{ data.succeeded_runs }} 成功 · {{ data.failed_runs }} 失败</div>
          </div>
          <div class="kpi">
            <div class="kpi-num">{{ data.total_generated }}</div>
            <div class="kpi-label">生成用例</div>
            <div class="kpi-hint">最近 {{ data.recent.length }} 条目标上限合计 {{ targetTotal }}</div>
          </div>
          <div class="kpi">
            <div class="kpi-num">{{ data.total_confirmed }}</div>
            <div class="kpi-label">确认入库</div>
            <div class="kpi-hint">采纳率 {{ formatPercent(data.adoption_rate) }}</div>
          </div>
          <div class="kpi">
            <div class="kpi-num" :class="rateClass(data.success_rate)">{{ formatPercent(data.success_rate) }}</div>
            <div class="kpi-label">任务成功率</div>
            <div class="kpi-hint">{{ data.awaiting_runs }} 待确认 · {{ data.cancelled_runs }} 取消</div>
          </div>
          <div class="kpi">
            <div class="kpi-num">{{ data.avg_ai_score == null ? '—' : data.avg_ai_score.toFixed(1) }}</div>
            <div class="kpi-label">最新 AI 评分均值</div>
            <div class="kpi-hint">{{ data.ai_scored_runs }} 个用例集有评分</div>
          </div>
          <div class="kpi">
            <div class="kpi-num">{{ data.review_approved }}</div>
            <div class="kpi-label">评审通过用例集</div>
            <div class="kpi-hint">不代表已执行验证</div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <h3>生成与确认趋势</h3>
              <p class="small tertiary">柱高按生成数归一；深色为确认入库，浅色为未确认部分。</p>
            </div>
            <span class="small tertiary">最近 {{ data.days }} 天</span>
          </div>
          <div v-if="!hasSeries" class="empty-inline">当前范围没有可展示的每日数据。</div>
          <div v-else class="trend">
            <div v-for="point in visibleSeries" :key="point.day" class="trend-col" :title="`${point.day}：生成 ${point.generated} / 确认 ${point.confirmed}`">
              <div class="trend-bar" :style="{ height: barHeight(point.generated) }">
                <span class="trend-confirmed" :style="{ height: confirmedHeight(point) }"></span>
              </div>
              <span class="trend-label">{{ shortDay(point.day) }}</span>
            </div>
          </div>
        </section>

        <div class="two-col">
          <section class="panel">
            <div class="panel-head"><h3>按模型 / 协议档</h3></div>
            <div v-if="!data.by_model.length" class="empty-inline">没有记录到模型信息。</div>
            <table v-else class="ds-table">
              <thead>
                <tr>
                  <th>模型</th>
                  <th>运行</th>
                  <th>生成</th>
                  <th>确认</th>
                  <th>采纳率</th>
                  <th>AI 分</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="model in data.by_model" :key="`${model.profile_id}-${model.model_name}`">
                  <td>
                    <div class="model-name">{{ model.model_name }}</div>
                    <div class="small tertiary">{{ model.profile_id || '未记录协议档' }}</div>
                  </td>
                  <td>{{ model.runs }}</td>
                  <td>{{ model.generated }}</td>
                  <td>{{ model.confirmed }}</td>
                  <td>{{ formatPercent(model.adoption_rate) }}</td>
                  <td>{{ model.avg_ai_score == null ? '—' : model.avg_ai_score.toFixed(1) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section class="panel">
            <div class="panel-head"><h3>状态与模块分布</h3></div>
            <div class="status-list">
              <div v-for="item in data.by_status" :key="item.status" class="status-row">
                <span class="status-name">{{ statusLabel(item.status) }}</span>
                <span class="status-count">{{ item.count }}</span>
              </div>
              <div v-if="!data.by_status.length" class="empty-inline">暂无状态数据。</div>
            </div>
            <div class="module-list">
              <div class="small tertiary module-title">模块用例数 Top {{ data.modules.length }}</div>
              <div v-for="item in data.modules" :key="item.module" class="module-row">
                <span class="module-name">{{ item.module }}</span>
                <span class="module-bar"><i :style="{ width: moduleWidth(item.case_count) }"></i></span>
                <span class="module-count">{{ item.case_count }}</span>
              </div>
              <div v-if="!data.modules.length" class="empty-inline">暂无用例模块数据。</div>
            </div>
          </section>
        </div>

        <section class="panel">
          <div class="panel-head">
            <h3>最近生成运行</h3>
            <span class="small tertiary">最多展示 50 条；点击任务或用例集可直达</span>
          </div>
          <div v-if="!data.recent.length" class="empty-inline">暂无运行明细。</div>
          <table v-else class="ds-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>用例集</th>
                <th>状态</th>
                <th>目标 / 生成</th>
                <th>确认</th>
                <th>采纳率</th>
                <th>AI 分</th>
                <th>模型</th>
                <th>耗时</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in data.recent" :key="run.task_id">
                <td class="small mono">{{ formatTime(run.created_at) }}</td>
                <td>
                  <router-link v-if="run.case_set_id" :to="`/cases?set_id=${run.case_set_id}`" class="link">
                    {{ run.name || run.case_set_id }}
                  </router-link>
                  <span v-else class="small tertiary">—</span>
                </td>
                <td>
                  <span class="status-pill" :class="`status-${run.status}`">{{ statusLabel(run.status) }}</span>
                  <span v-if="run.error_code" class="small tertiary error-code">{{ run.error_code }}</span>
                </td>
                <td>{{ run.target_count || '—' }} / {{ run.generated_count }}</td>
                <td>{{ run.confirmed_count }}</td>
                <td>{{ formatPercent(run.adoption_rate) }}</td>
                <td>{{ run.ai_score == null ? '—' : run.ai_score }}</td>
                <td class="small">{{ run.model_name || '未记录' }}</td>
                <td class="small">{{ formatDuration(run.duration_ms) }}</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '../api/http'
import type { CasegenMetrics } from '../api/types'

const rangeOptions = [
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
]

const days = ref(30)
const data = ref<CasegenMetrics | null>(null)
const loading = ref(false)
const error = ref('')

const targetTotal = computed(() =>
  (data.value?.recent || []).reduce((sum, run) => sum + (run.target_count || 0), 0),
)

// 90 天窗口保留完整序列，横向滚动查看；不悄悄截成 30 天。
const visibleSeries = computed(() => data.value?.series || [])

const hasSeries = computed(() => visibleSeries.value.some((point) => point.generated > 0 || point.confirmed > 0))

const maxGenerated = computed(() =>
  Math.max(1, ...visibleSeries.value.map((point) => point.generated || 0)),
)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.metrics.casegen(days.value)
  } catch (err: any) {
    error.value = err?.message || '加载质量数据失败'
  } finally {
    loading.value = false
  }
}

function changeRange(value: number): void {
  if (days.value === value) return
  days.value = value
  void load()
}

function barHeight(value: number): string {
  if (!value) return '2px'
  return `${Math.max(4, Math.round((value / maxGenerated.value) * 100))}%`
}

function confirmedHeight(point: { generated: number; confirmed: number }): string {
  if (!point.generated || !point.confirmed) return '0%'
  return `${Math.min(100, Math.round((point.confirmed / point.generated) * 100))}%`
}

function moduleWidth(count: number): string {
  const max = Math.max(1, ...(data.value?.modules || []).map((item) => item.case_count))
  return `${Math.max(4, Math.round((count / max) * 100))}%`
}

function formatPercent(value: number): string {
  return `${((value || 0) * 100).toFixed(1)}%`
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function shortDay(value: string): string {
  return value.slice(5)
}

function formatDuration(value?: number | null): string {
  if (value == null) return '—'
  if (value < 1000) return `${value}ms`
  const seconds = Math.round(value / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m${seconds % 60}s`
}

function rateClass(value: number): string {
  if (value >= 0.9) return 'good'
  if (value >= 0.7) return 'warn'
  return 'bad'
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: '排队中',
    running: '执行中',
    awaiting_case_confirm: '待用例确认',
    succeeded: '成功',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[status] || status || '—'
}

onMounted(load)
</script>

<style scoped>
.quality-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-head h1 {
  margin: 0;
  font-size: 22px;
}

.page-sub {
  margin: 6px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.range-switch {
  display: inline-flex;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-elevated);
}

.range-btn {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  padding: 5px 10px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
}

.range-btn.active {
  background: var(--bg-main);
  color: var(--accent-ai);
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}

.kpi {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-main);
  padding: 12px 13px;
}

.kpi-num {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.kpi-num.good { color: #2f8f63; }
.kpi-num.warn { color: #c08a2e; }
.kpi-num.bad { color: #c0504d; }

.kpi-label {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.kpi-hint {
  margin-top: 3px;
  font-size: 10px;
  color: var(--text-tertiary);
}

.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-main);
  padding: 14px 16px;
}

.panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.panel-head h3 {
  margin: 0;
  font-size: 14px;
}

.panel-head p {
  margin: 4px 0 0;
}

.empty-state {
  padding: 48px 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.empty-inline {
  padding: 18px 4px;
  color: var(--text-tertiary);
  font-size: 12px;
}

.trend {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 160px;
  padding-top: 8px;
  overflow-x: auto;
}

.trend-col {
  flex: 1;
  min-width: 8px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: center;
  gap: 5px;
}

.trend-bar {
  position: relative;
  width: 100%;
  max-width: 26px;
  min-height: 2px;
  display: flex;
  align-items: flex-end;
  border-radius: 4px 4px 0 0;
  background: color-mix(in srgb, var(--accent-ai) 22%, transparent);
  overflow: hidden;
}

.trend-confirmed {
  width: 100%;
  display: block;
  background: var(--accent-ai);
  border-radius: 3px 3px 0 0;
}

.trend-label {
  font-size: 9px;
  color: var(--text-tertiary);
  white-space: nowrap;
  transform: rotate(-45deg);
  transform-origin: center;
}

.two-col {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  gap: 16px;
}

.model-name {
  font-size: 12.5px;
  font-weight: 600;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px;
  border-radius: 6px;
  background: var(--bg-elevated);
  font-size: 12px;
}

.status-count {
  font-family: var(--font-mono);
}

.module-title {
  margin-bottom: 6px;
}

.module-row {
  display: grid;
  grid-template-columns: 100px minmax(0, 1fr) 36px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 5px;
}

.module-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-secondary);
}

.module-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--bg-elevated);
  overflow: hidden;
}

.module-bar i {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent-ai) 75%, transparent);
}

.module-count {
  text-align: right;
  font-family: var(--font-mono);
  color: var(--text-tertiary);
}

.status-pill {
  display: inline-flex;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.status-pill.status-succeeded { color: #15803d; background: rgba(34, 197, 94, 0.12); }
.status-pill.status-failed { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
.status-pill.status-running,
.status-pill.status-awaiting_case_confirm { color: #b45309; background: rgba(245, 158, 11, 0.12); }

.error-code {
  margin-left: 4px;
}

.link {
  color: var(--accent-ai);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .two-col {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 700px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .page-actions {
    width: 100%;
    justify-content: space-between;
  }
  .trend {
    height: 130px;
  }
  .trend-label {
    display: none;
  }
}
</style>
