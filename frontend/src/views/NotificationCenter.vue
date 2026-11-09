<template>
  <div class="notif-page">
    <header class="page-head">
      <div>
        <h1>通知中心</h1>
        <p class="page-sub">任务终态、评审指派与结论的站内提醒；通知不代表任务最终状态，请以任务/用例页为准。</p>
      </div>
      <div class="page-actions">
        <div class="range-switch" role="group" aria-label="通知筛选">
          <button class="range-btn" :class="{ active: !unreadOnly }" @click="setFilter(false)">全部</button>
          <button class="range-btn" :class="{ active: unreadOnly }" @click="setFilter(true)">未读 {{ unread ? `(${unread})` : '' }}</button>
        </div>
        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
        <button class="btn btn-primary btn-sm" :disabled="!unread || markingAll" @click="markAll">
          {{ markingAll ? '处理中…' : '全部已读' }}
        </button>
      </div>
    </header>

    <section class="panel">
      <div v-if="loading" class="notif-state">正在读取通知…</div>
      <div v-else-if="error" class="notif-state">
        <p>{{ error }}</p>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>
      <div v-else-if="!items.length" class="notif-state">
        {{ unreadOnly ? '没有未读通知。' : '暂无通知；任务完成或评审指派后会出现在这里。' }}
      </div>

      <template v-else>
        <button
          v-for="item in items"
          :key="item.id"
          class="notif-row"
          :class="{ unread: !item.read_at }"
          @click="openItem(item)"
        >
          <span class="notif-type" :data-type="item.type">{{ typeLabel(item.type) }}</span>
          <span class="notif-main">
            <span class="notif-title">{{ item.title }}</span>
            <span v-if="item.body" class="notif-body">{{ item.body }}</span>
            <span class="notif-time">{{ formatTime(item.created_at) }}</span>
          </span>
          <span v-if="!item.read_at" class="notif-dot" aria-label="未读"></span>
        </button>

        <div class="notif-pager">
          <span class="small tertiary">共 {{ total }} 条</span>
          <button class="btn btn-secondary btn-sm" :disabled="offset === 0 || loading" @click="changePage(-1)">上一页</button>
          <span class="small">{{ Math.floor(offset / limit) + 1 }} / {{ Math.max(1, Math.ceil(total / limit)) }}</span>
          <button class="btn btn-secondary btn-sm" :disabled="offset + limit >= total || loading" @click="changePage(1)">下一页</button>
        </div>
      </template>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'

import { api } from '../api/http'
import type { NotificationItem } from '../api/types'

const router = useRouter()
const message = useMessage()

const items = ref<NotificationItem[]>([])
const total = ref(0)
const unread = ref(0)
const offset = ref(0)
const limit = 20
const unreadOnly = ref(false)
const loading = ref(false)
const error = ref('')
const markingAll = ref(false)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await api.notifications.list({
      unread: unreadOnly.value,
      offset: offset.value,
      limit,
    })
    items.value = result.items
    total.value = result.total
    unread.value = result.unread
  } catch (err: any) {
    items.value = []
    total.value = 0
    error.value = err?.message || '加载通知失败'
  } finally {
    loading.value = false
  }
}

function setFilter(value: boolean): void {
  if (unreadOnly.value === value) return
  unreadOnly.value = value
  offset.value = 0
  void load()
}

function changePage(direction: number): void {
  offset.value = Math.max(0, offset.value + direction * limit)
  void load()
}

async function openItem(item: NotificationItem): Promise<void> {
  if (!item.read_at) {
    try {
      unread.value = await api.notifications.markRead(item.id)
      item.read_at = new Date().toISOString()
    } catch {
      // 已读失败不阻止跳转。
    }
  }
  if (item.link) router.push(item.link)
}

async function markAll(): Promise<void> {
  markingAll.value = true
  try {
    unread.value = await api.notifications.markAllRead()
    items.value = items.value.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() }))
    message.success('已全部标为已读')
  } catch (err: any) {
    message.error(err?.message || '操作失败')
  } finally {
    markingAll.value = false
  }
}

function typeLabel(type: string): string {
  const labels: Record<string, string> = {
    task_ready: '待确认',
    task_failed: '失败',
    review_requested: '待评审',
    review_approved: '评审通过',
    review_changes: '要求修改',
  }
  return labels[type] || '通知'
}

function formatTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.notif-page {
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
  gap: 8px;
  flex-wrap: wrap;
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

.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-main);
  padding: 8px 16px 14px;
}

.notif-state {
  padding: 48px 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.notif-row {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 2px;
  border: none;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.notif-row:hover {
  background: var(--row-hover);
}

.notif-row.unread {
  background: color-mix(in srgb, var(--accent-ai) 4%, transparent);
}

.notif-type {
  flex-shrink: 0;
  margin-top: 1px;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  color: var(--text-secondary);
  background: var(--bg-elevated);
}

.notif-type[data-type='task_failed'] { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
.notif-type[data-type='task_ready'] { color: #b45309; background: rgba(245, 158, 11, 0.12); }
.notif-type[data-type='review_requested'] { color: #1d4ed8; background: rgba(59, 130, 246, 0.1); }
.notif-type[data-type='review_approved'] { color: #15803d; background: rgba(34, 197, 94, 0.12); }
.notif-type[data-type='review_changes'] { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }

.notif-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.notif-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.notif-body {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}

.notif-time {
  font-size: 10px;
  color: var(--text-tertiary);
}

.notif-dot {
  flex-shrink: 0;
  width: 7px;
  height: 7px;
  margin-top: 6px;
  border-radius: 50%;
  background: #dc2626;
}

.notif-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

@media (max-width: 700px) {
  .page-actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
