<template>
  <div ref="rootRef" class="notif-bell">
    <button
      class="topbar-icon-btn notif-trigger"
      :aria-label="unread ? `通知，${unread} 条未读` : '通知'"
      title="通知"
      @click="toggle"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"></path>
        <path d="M13.7 21a2 2 0 0 1-3.4 0"></path>
      </svg>
      <span v-if="unread" class="notif-badge">{{ unread > 99 ? '99+' : unread }}</span>
    </button>

    <Transition name="notif-fade">
      <div v-if="open" class="notif-panel" role="dialog" aria-label="通知列表">
        <div class="notif-head">
          <b>通知</b>
          <span class="small tertiary">{{ unread ? `${unread} 条未读` : '全部已读' }}</span>
          <button v-if="unread" class="link-btn" :disabled="markingAll" @click="markAll">
            {{ markingAll ? '处理中…' : '全部已读' }}
          </button>
        </div>

        <div v-if="loading" class="notif-state">加载中…</div>
        <div v-else-if="error" class="notif-state">
          <span>{{ error }}</span>
          <button class="link-btn" @click="load">重试</button>
        </div>
        <div v-else-if="!items.length" class="notif-state">暂无通知。</div>
        <div v-else class="notif-list">
          <button
            v-for="item in items"
            :key="item.id"
            class="notif-item"
            :class="{ unread: !item.read_at }"
            @click="openItem(item)"
          >
            <span class="notif-item-main">
              <span class="notif-item-title">{{ item.title }}</span>
              <span v-if="item.body" class="notif-item-body">{{ item.body }}</span>
              <span class="notif-item-time">{{ formatTime(item.created_at) }}</span>
            </span>
            <span v-if="!item.read_at" class="notif-dot" aria-label="未读"></span>
          </button>
        </div>

        <router-link class="notif-foot" to="/notifications" @click="open = false">查看全部通知</router-link>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '../../api/http'
import type { NotificationItem } from '../../api/types'

const router = useRouter()
const rootRef = ref<HTMLElement | null>(null)
const open = ref(false)
const unread = ref(0)
const items = ref<NotificationItem[]>([])
const loading = ref(false)
const error = ref('')
const markingAll = ref(false)
let timer: number | undefined
let lastRefresh = 0

async function refreshUnread(): Promise<void> {
  lastRefresh = Date.now()
  try {
    unread.value = await api.notifications.unreadCount()
  } catch {
    // 顶栏计数失败不打断主流程；打开面板时会再请求一次。
  }
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await api.notifications.list({ limit: 8 })
    items.value = result.items
    unread.value = result.unread
  } catch (err: any) {
    items.value = []
    error.value = err?.message || '加载通知失败'
  } finally {
    loading.value = false
  }
}

function toggle(): void {
  open.value = !open.value
  if (open.value) void load()
}

async function openItem(item: NotificationItem): Promise<void> {
  if (!item.read_at) {
    try {
      unread.value = await api.notifications.markRead(item.id)
      item.read_at = new Date().toISOString()
    } catch {
      // 已读失败不阻止跳转，列表下次刷新会纠正。
    }
  }
  open.value = false
  if (item.link) router.push(item.link)
}

async function markAll(): Promise<void> {
  markingAll.value = true
  try {
    unread.value = await api.notifications.markAllRead()
    items.value = items.value.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() }))
  } finally {
    markingAll.value = false
  }
}

function formatTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const diff = Date.now() - date.getTime()
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return date.toLocaleString('zh-CN', { hour12: false })
}

function onDocumentPointerDown(event: PointerEvent): void {
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) open.value = false
}

function onVisibilityChange(): void {
  if (document.visibilityState === 'visible' && Date.now() - lastRefresh > 15_000) {
    void refreshUnread()
  }
}

onMounted(() => {
  void refreshUnread()
  timer = window.setInterval(() => {
    if (document.visibilityState === 'visible') void refreshUnread()
  }, 30_000)
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  window.clearInterval(timer)
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})
</script>

<style scoped>
.notif-bell {
  position: relative;
}

.notif-trigger {
  position: relative;
}

.notif-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: #dc2626;
  color: #fff;
  font: 600 9px/16px var(--font-mono);
  text-align: center;
}

.notif-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 900;
  width: 340px;
  max-width: calc(100vw - 24px);
  max-height: 480px;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--bg-main);
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
  overflow: hidden;
}

.notif-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.notif-head .link-btn {
  margin-left: auto;
  font-size: 11px;
}

.notif-state {
  padding: 26px 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12px;
}

.notif-list {
  overflow-y: auto;
}

.notif-item {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 9px 12px;
  border: none;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.notif-item:hover {
  background: var(--row-hover);
}

.notif-item.unread {
  background: color-mix(in srgb, var(--accent-ai) 5%, transparent);
}

.notif-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.notif-item-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary);
}

.notif-item-body {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.notif-item-time {
  font-size: 10px;
  color: var(--text-tertiary);
}

.notif-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: #dc2626;
}

.notif-foot {
  display: block;
  padding: 9px 12px;
  border-top: 1px solid var(--border-subtle);
  text-align: center;
  font-size: 12px;
  color: var(--accent-ai);
}

.notif-fade-enter-active,
.notif-fade-leave-active {
  transition: opacity 120ms ease, transform 120ms ease;
}

.notif-fade-enter-from,
.notif-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 700px) {
  .notif-panel {
    position: fixed;
    top: 58px;
    left: 12px;
    right: 12px;
    width: auto;
    max-height: 70vh;
  }
}
</style>
