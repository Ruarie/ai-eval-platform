<template>
  <Teleport to="body">
    <Transition name="gs-fade">
      <div v-if="visible" class="gs-overlay" @mousedown.self="close">
        <section class="gs-panel" role="dialog" aria-modal="true" aria-label="全局搜索">
          <div class="gs-head">
            <svg class="gs-search-icon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="7"></circle>
              <path d="m20 20-3.5-3.5"></path>
            </svg>
            <input
              ref="inputRef"
              v-model="query"
              class="gs-input"
              placeholder="搜索用例集、任务、会话、报告、知识库…"
              aria-label="全局搜索关键词"
              autocomplete="off"
              spellcheck="false"
              @input="onInput"
              @keydown="onKeydown"
            />
            <kbd class="gs-kbd">Esc</kbd>
          </div>

          <div v-if="!query.trim()" class="gs-body gs-empty">
            <p class="gs-hint">输入关键词开始搜索；支持用例集、任务、会话、报告、知识库、数据集、工作区与个人记忆。</p>
            <div class="gs-quick">
              <button v-for="link in quickLinks" :key="link.url" class="gs-quick-item" @click="go(link.url)">
                {{ link.label }}
              </button>
            </div>
            <div v-if="recent.length" class="gs-recent">
              <span class="gs-section-label">最近搜索</span>
              <button v-for="item in recent" :key="item" class="gs-chip" @click="applyRecent(item)">{{ item }}</button>
            </div>
          </div>

          <div v-else-if="loading" class="gs-body gs-state">搜索中…</div>

          <div v-else-if="error" class="gs-body gs-state gs-error">
            <span>{{ error }}</span>
            <button class="gs-retry" @click="runSearch">重试</button>
          </div>

          <div v-else-if="!groups.length" class="gs-body gs-state">没有找到“{{ query.trim() }}”相关结果</div>

          <div v-else class="gs-body gs-results">
            <div v-for="group in groups" :key="group.type" class="gs-group">
              <div class="gs-group-label">
                <span>{{ group.label }}</span>
                <span class="gs-group-count">{{ group.items.length }}</span>
              </div>
              <button
                v-for="item in group.items"
                :key="itemKey(item)"
                class="gs-item"
                :class="{ active: activeKey === itemKey(item) }"
                @mouseenter="activeKey = itemKey(item)"
                @click="go(item.url)"
              >
                <span class="gs-item-main">
                  <span class="gs-item-title">
                    <template v-for="(part, index) in highlight(item.title)" :key="index">
                      <mark v-if="part.hit">{{ part.text }}</mark>
                      <template v-else>{{ part.text }}</template>
                    </template>
                  </span>
                  <span class="gs-item-sub">{{ item.subtitle }}</span>
                </span>
                <span v-if="item.status" class="gs-status">{{ item.status }}</span>
                <span class="gs-enter" aria-hidden="true">↵</span>
              </button>
            </div>
          </div>

          <div class="gs-foot">
            <span>↑↓ 选择</span>
            <span>Enter 打开</span>
            <span>Esc 关闭</span>
            <span class="gs-foot-brand">AI 测试与评估平台</span>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api/http'
import type { GlobalSearchGroup, GlobalSearchItem } from '../../api/types'

const router = useRouter()
const visible = ref(false)
const query = ref('')
const loading = ref(false)
const error = ref('')
const groups = ref<GlobalSearchGroup[]>([])
const activeKey = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const recent = ref<string[]>(loadRecent())

let searchTimer: number | undefined
let searchSeq = 0

const quickLinks = [
  { label: '智能体', url: '/agent' },
  { label: '用例', url: '/cases' },
  { label: '任务中心', url: '/tasks' },
  { label: '历史报告', url: '/reports' },
]

/** 扁平化结果，供方向键在分组之间连续移动。 */
const flatItems = computed<GlobalSearchItem[]>(() =>
  groups.value.flatMap((group) => group.items)
)

function itemKey(item: GlobalSearchItem): string {
  return `${item.type}:${item.id}`
}

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem('aieval:search:recent')
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === 'string').slice(0, 5) : []
  } catch {
    return []
  }
}

function remember(term: string): void {
  const value = term.trim()
  if (!value) return
  recent.value = [value, ...recent.value.filter((item) => item !== value)].slice(0, 5)
  try {
    localStorage.setItem('aieval:search:recent', JSON.stringify(recent.value))
  } catch {
    // 隐私模式下 localStorage 可能不可写，不影响搜索主流程。
  }
}

function open(): void {
  visible.value = true
  nextTick(() => inputRef.value?.focus())
}

function close(): void {
  visible.value = false
  loading.value = false
  error.value = ''
}

function applyRecent(term: string): void {
  query.value = term
  void runSearch()
}

function onInput(): void {
  window.clearTimeout(searchTimer)
  if (!query.value.trim()) {
    groups.value = []
    loading.value = false
    error.value = ''
    return
  }
  searchTimer = window.setTimeout(() => void runSearch(), 220)
}

async function runSearch(): Promise<void> {
  const term = query.value.trim()
  if (!term) return
  const seq = ++searchSeq
  loading.value = true
  error.value = ''
  try {
    const result = await api.search.query(term, 5)
    if (seq !== searchSeq) return
    groups.value = result.groups || []
    activeKey.value = groups.value[0]?.items[0] ? itemKey(groups.value[0].items[0]) : ''
  } catch (err: any) {
    if (seq !== searchSeq) return
    groups.value = []
    error.value = err?.message || '搜索失败，请稍后重试'
  } finally {
    if (seq === searchSeq) loading.value = false
  }
}

/** 只高亮命中词，输出纯文本片段后交给模板渲染，避免 v-html 注入。 */
function highlight(text: string): Array<{ text: string; hit: boolean }> {
  const term = query.value.trim()
  if (!term) return [{ text, hit: false }]
  const lowerText = text.toLowerCase()
  const lowerTerm = term.toLowerCase()
  const parts: Array<{ text: string; hit: boolean }> = []
  let cursor = 0
  let index = lowerText.indexOf(lowerTerm)
  while (index >= 0) {
    if (index > cursor) parts.push({ text: text.slice(cursor, index), hit: false })
    parts.push({ text: text.slice(index, index + term.length), hit: true })
    cursor = index + term.length
    index = lowerText.indexOf(lowerTerm, cursor)
  }
  if (cursor < text.length) parts.push({ text: text.slice(cursor), hit: false })
  return parts.length ? parts : [{ text, hit: false }]
}

function move(delta: number): void {
  if (!flatItems.value.length) return
  const current = flatItems.value.findIndex((item) => itemKey(item) === activeKey.value)
  const next = (current + delta + flatItems.value.length) % flatItems.value.length
  activeKey.value = itemKey(flatItems.value[next])
  nextTick(() => {
    document.querySelector(`.gs-item.active`)?.scrollIntoView({ block: 'nearest' })
  })
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    move(1)
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    move(-1)
  } else if (event.key === 'Enter') {
    const item = flatItems.value.find((entry) => itemKey(entry) === activeKey.value)
    if (item) {
      event.preventDefault()
      go(item.url)
    }
  } else if (event.key === 'Escape') {
    event.preventDefault()
    close()
  }
}

function go(url: string): void {
  if (!url) return
  remember(query.value)
  close()
  router.push(url)
}

/** 全局快捷键：Ctrl/Cmd+K 打开；只在未处于输入态时拦截，避免影响表单输入。 */
function handleGlobalKeydown(event: KeyboardEvent): void {
  const isSearchShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k'
  if (!isSearchShortcut) return
  event.preventDefault()
  if (visible.value) close()
  else open()
}

onMounted(() => window.addEventListener('keydown', handleGlobalKeydown))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.clearTimeout(searchTimer)
})

defineExpose({ open, close })
</script>

<style scoped>
.gs-overlay {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 12vh 16px 24px;
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(3px);
}

.gs-panel {
  width: 640px;
  max-width: 100%;
  max-height: 72vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  box-shadow: 0 24px 70px rgba(15, 23, 42, 0.22);
  overflow: hidden;
}

.gs-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}

.gs-search-icon {
  flex-shrink: 0;
}

.gs-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.5;
}

.gs-input::placeholder {
  color: var(--text-tertiary, var(--text-secondary));
}

.gs-kbd {
  flex-shrink: 0;
  padding: 2px 6px;
  border: 1px solid var(--border-subtle);
  border-radius: 5px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font: 600 10px/1.6 var(--font-mono);
}

.gs-body {
  min-height: 120px;
  overflow-y: auto;
  padding: 8px;
}

.gs-empty {
  padding: 14px 14px 16px;
}

.gs-hint {
  margin: 0 0 12px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.65;
}

.gs-quick {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.gs-quick-item,
.gs-chip {
  border: 1px solid var(--border-subtle);
  border-radius: 999px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 5px 11px;
  font-size: 12px;
  cursor: pointer;
}

.gs-quick-item:hover,
.gs-chip:hover {
  border-color: var(--accent-ai);
  color: var(--accent-ai);
}

.gs-recent {
  margin-top: 16px;
}

.gs-section-label {
  display: block;
  margin-bottom: 8px;
  color: var(--text-tertiary, var(--text-secondary));
  font-size: 11px;
}

.gs-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 28px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.gs-error {
  color: var(--accent-error, #b91c1c);
}

.gs-retry {
  border: 1px solid currentColor;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  padding: 3px 9px;
  font-size: 12px;
  cursor: pointer;
}

.gs-group {
  padding: 4px 0 6px;
}

.gs-group-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  color: var(--text-tertiary, var(--text-secondary));
  font-size: 11px;
  letter-spacing: 0.04em;
}

.gs-group-count {
  color: var(--text-tertiary, var(--text-secondary));
  opacity: 0.7;
}

.gs-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.gs-item.active {
  background: color-mix(in srgb, var(--accent-ai) 9%, var(--bg-main));
}

.gs-item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.gs-item-title {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-item-title mark {
  background: color-mix(in srgb, var(--accent-warning, #f59e0b) 25%, transparent);
  color: inherit;
  border-radius: 3px;
  padding: 0 1px;
}

.gs-item-sub {
  color: var(--text-secondary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.gs-status {
  flex-shrink: 0;
  border-radius: 999px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 2px 7px;
  font-size: 10px;
}

.gs-enter {
  flex-shrink: 0;
  color: var(--text-tertiary, var(--text-secondary));
  font-size: 11px;
  opacity: 0;
}

.gs-item.active .gs-enter {
  opacity: 1;
}

.gs-foot {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 8px 14px;
  border-top: 1px solid var(--border-subtle);
  color: var(--text-tertiary, var(--text-secondary));
  font-size: 10px;
}

.gs-foot-brand {
  margin-left: auto;
  opacity: 0.7;
}

.gs-fade-enter-active,
.gs-fade-leave-active {
  transition: opacity 140ms ease;
}

.gs-fade-enter-from,
.gs-fade-leave-to {
  opacity: 0;
}

@media (max-width: 640px) {
  .gs-overlay {
    padding: 8vh 10px 16px;
  }

  .gs-panel {
    max-height: 78vh;
  }

  .gs-foot {
    gap: 10px;
  }

  .gs-foot-brand {
    display: none;
  }
}
</style>
