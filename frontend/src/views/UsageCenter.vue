<template>
  <div class="usage-page">
    <header class="page-head">
      <div>
        <h1>用量中心</h1>
        <p class="page-sub">按 assistant 消息的 turn_stats 聚合 token；当前未配置逐模型单价，不展示费用估算。</p>
      </div>
      <div class="page-actions">
        <div class="range-switch" role="group" aria-label="统计时间范围">
          <button v-for="option in ranges" :key="option.value" class="range-btn" :class="{ active: days === option.value }" @click="changeRange(option.value)">
            {{ option.label }}
          </button>
        </div>
        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="loading && !data" class="panel usage-state">正在聚合用量…</div>
    <div v-else-if="error" class="panel usage-state">
      <p>{{ error }}</p>
      <button class="btn btn-secondary btn-sm" @click="load">重试</button>
    </div>

    <template v-else-if="data">
      <div v-if="!data.calls" class="panel usage-state">
        当前时间范围内没有可统计的模型调用。发送几轮 Agent 对话后再回来查看。
      </div>

      <template v-else>
        <!-- 聚合上限提示：数字只覆盖最近 N 条消息，不能当全量用量 -->
        <div v-if="data.truncated" class="panel" style="padding: 10px 14px; margin-bottom: 12px; border-color: var(--accent-warning)">
          <span class="small" style="color: var(--accent-warning)">
            当前时间窗内匹配消息超过聚合上限，以下数字只统计最近 {{ data.scanned_messages ?? data.sample_limit }} 条
            消息（上限 {{ data.sample_limit }} 条），不代表全量用量。请缩小时间范围后查看。
          </span>
        </div>
        <section class="kpi-grid">
          <div class="kpi"><b>{{ data.calls }}</b><span>模型调用</span></div>
          <div class="kpi"><b>{{ data.sessions }}</b><span>会话数</span></div>
          <div class="kpi"><b>{{ data.users }}</b><span>成员数</span></div>
          <div class="kpi"><b>{{ formatTokens(data.total_tokens) }}</b><span>总 token</span></div>
          <div class="kpi"><b>{{ formatTokens(data.prompt_tokens) }}</b><span>输入 token</span></div>
          <div class="kpi"><b>{{ formatTokens(data.completion_tokens) }}</b><span>输出 token</span></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div>
              <h3>每日 token</h3>
              <p class="small tertiary">柱高按当日总 token 归一；悬停查看调用数与输入/输出。</p>
            </div>
            <span class="small tertiary">最近 {{ data.days }} 天</span>
          </div>
          <div v-if="!hasSeries" class="empty-inline">当前范围没有每日数据。</div>
          <div v-else class="trend">
            <div v-for="point in data.series" :key="point.day" class="trend-col" :title="`${point.day}：${point.calls} 次 / ${point.total_tokens} tokens`">
              <div class="trend-bar" :style="{ height: barHeight(point.total_tokens) }"></div>
              <span class="trend-label">{{ point.day.slice(5) }}</span>
            </div>
          </div>
        </section>

        <div class="two-col">
          <section class="panel">
            <div class="panel-head"><h3>按模型 / 协议档</h3></div>
            <table class="ds-table">
              <thead><tr><th>模型</th><th>调用</th><th>会话</th><th>输入</th><th>输出</th><th>总 token</th><th>占比</th></tr></thead>
              <tbody>
                <tr v-for="item in data.by_model" :key="`${item.profile_id}-${item.model_name}`">
                  <td>
                    <div class="model-name">{{ item.model_name }}</div>
                    <div class="small tertiary">{{ item.profile_id || '未记录协议档' }}</div>
                  </td>
                  <td>{{ item.calls }}</td>
                  <td>{{ item.sessions }}</td>
                  <td>{{ formatTokens(item.prompt_tokens) }}</td>
                  <td>{{ formatTokens(item.completion_tokens) }}</td>
                  <td>{{ formatTokens(item.total_tokens) }}</td>
                  <td>{{ share(item.total_tokens) }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section class="panel">
            <div class="panel-head"><h3>按成员</h3></div>
            <div v-if="!data.by_user.length" class="empty-inline">暂无成员用量。</div>
            <div v-for="item in data.by_user" :key="item.user_id" class="user-row">
              <span class="user-name">{{ item.username }}</span>
              <span class="user-meta">{{ item.calls }} 次 · {{ formatTokens(item.total_tokens) }}</span>
              <span class="user-bar"><i :style="{ width: userWidth(item.total_tokens) }"></i></span>
            </div>
          </section>
        </div>

        <section class="panel">
          <div class="panel-head">
            <h3>最近调用</h3>
            <span class="small tertiary">最多 50 条；不展示消息正文</span>
          </div>
          <table class="ds-table">
            <thead><tr><th>时间</th><th>会话</th><th>模型</th><th>输入</th><th>输出</th><th>总 token</th></tr></thead>
            <tbody>
              <tr v-for="(item, index) in data.recent" :key="`${item.session_id}-${index}`">
                <td class="small mono">{{ formatTime(item.created_at) }}</td>
                <td>
                  <router-link :to="`/agent?session_id=${item.session_id}`" class="link">{{ item.session_title }}</router-link>
                </td>
                <td class="small">{{ item.model_name || '未记录' }}</td>
                <td>{{ formatTokens(item.prompt_tokens) }}</td>
                <td>{{ formatTokens(item.completion_tokens) }}</td>
                <td>{{ formatTokens(item.total_tokens) }}</td>
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
import type { UsageSummary } from '../api/types'

const ranges = [
  { value: 7, label: '7 天' },
  { value: 30, label: '30 天' },
  { value: 90, label: '90 天' },
]
const days = ref(30)
const data = ref<UsageSummary | null>(null)
const loading = ref(false)
const error = ref('')

const hasSeries = computed(() => (data.value?.series || []).some((item) => item.total_tokens > 0))
const maxTokens = computed(() => Math.max(1, ...(data.value?.series || []).map((item) => item.total_tokens)))

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.usage.summary(days.value)
  } catch (err: any) {
    error.value = err?.message || '加载用量数据失败'
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
  return `${Math.max(4, Math.round((value / maxTokens.value) * 100))}%`
}

function userWidth(value: number): string {
  const max = Math.max(1, ...(data.value?.by_user || []).map((item) => item.total_tokens))
  return `${Math.max(4, Math.round((value / max) * 100))}%`
}

function share(value: number): string {
  const total = data.value?.total_tokens || 0
  return total ? `${((value / total) * 100).toFixed(1)}%` : '—'
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`
  return String(value || 0)
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.usage-page { display: flex; flex-direction: column; gap: 16px; }
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.page-head h1 { margin: 0; font-size: 22px; }
.page-sub { margin: 6px 0 0; color: var(--text-tertiary); font-size: 12px; }
.page-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.range-switch { display: inline-flex; padding: 2px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-elevated); }
.range-btn { border: none; background: transparent; color: var(--text-secondary); padding: 5px 10px; border-radius: 6px; font-size: 12px; cursor: pointer; }
.range-btn.active { background: var(--bg-main); color: var(--accent-ai); box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08); }
.kpi-grid { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 10px; }
.kpi { border: 1px solid var(--border); border-radius: 10px; background: var(--bg-main); padding: 12px 14px; display: flex; flex-direction: column; gap: 3px; }
.kpi b { font-size: 22px; line-height: 1.1; }
.kpi span { font-size: 12px; color: var(--text-secondary); }
.panel { border: 1px solid var(--border); border-radius: 12px; background: var(--bg-main); padding: 14px 16px; }
.panel-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.panel-head h3 { margin: 0; font-size: 14px; }
.panel-head p { margin: 4px 0 0; }
.usage-state { padding: 48px 20px; text-align: center; color: var(--text-tertiary); font-size: 13px; }
.empty-inline { padding: 18px 4px; color: var(--text-tertiary); font-size: 12px; }
.trend { display: flex; align-items: flex-end; gap: 4px; height: 160px; padding-top: 8px; overflow-x: auto; }
.trend-col { flex: 1; min-width: 8px; height: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; gap: 5px; }
.trend-bar { width: 100%; max-width: 26px; min-height: 2px; border-radius: 4px 4px 0 0; background: color-mix(in srgb, var(--accent-ai) 70%, transparent); }
.trend-label { font-size: 9px; color: var(--text-tertiary); white-space: nowrap; transform: rotate(-45deg); transform-origin: center; }
.two-col { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 16px; }
.model-name { font-size: 12.5px; font-weight: 600; }
.user-row { display: grid; grid-template-columns: 110px minmax(0, 1fr) 130px; gap: 8px; align-items: center; padding: 6px 2px; border-bottom: 1px solid var(--border-subtle); font-size: 12px; }
.user-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-meta { color: var(--text-tertiary); font-size: 11px; }
.user-bar { height: 6px; border-radius: 999px; background: var(--bg-elevated); overflow: hidden; }
.user-bar i { display: block; height: 100%; border-radius: 999px; background: color-mix(in srgb, var(--accent-ai) 70%, transparent); }
.link { color: var(--accent-ai); font-size: 12px; }
@media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); } .two-col { grid-template-columns: 1fr; } }
@media (max-width: 700px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .trend { height: 130px; } .trend-label { display: none; } }
</style>
