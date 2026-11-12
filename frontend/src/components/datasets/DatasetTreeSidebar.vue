<template>
  <aside class="nordic-sidebar">
    <div class="sidebar-header">
      <div class="sidebar-title-row">
        <div class="sidebar-title">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="title-icon">
            <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
          </svg>
          <span>数据集资源</span>
        </div>
        <div class="sidebar-actions">
          <button class="btn btn-ghost-subtle btn-xs" title="通过场景或模板自动合成数据集" aria-label="自动合成新数据集" @click="emit('ai-gen')">
            + 合成
          </button>
          <button class="btn btn-ghost-subtle btn-xs" title="上传 JSONL / CSV 数据集文件" aria-label="上传数据集文件" @click="emit('upload')">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            上传
          </button>
        </div>
      </div>

      <!-- 搜索输入框 -->
      <div class="search-box">
        <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <input :value="search" class="search-input" @input="onSearchInput" placeholder="搜索数据集 / 黄金 QA..." aria-label="搜索数据集或黄金QA" />
        <button v-if="search" class="clear-search-btn" aria-label="清空搜索" @click="emit('update:search', '')">✕</button>
      </div>
    </div>

    <!-- 目录树内容区 -->
    <div class="tree-content custom-scroll">
      <div v-for="folder in folders" :key="folder.id" class="folder-group" :data-fid="folder.id">
        <!-- 文件夹节点 -->
        <div
          class="tree-node folder-node"
          :class="{ open: folder.open }"
          @click="emit('toggle-folder', folder.id)"
          @contextmenu.prevent.stop="emit('context-menu', { event: $event, kind: 'folder', id: folder.id })"
        >
          <span class="chevron-icon" :class="{ rotated: folder.open }">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </span>
          <svg class="folder-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path v-if="folder.open" d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2" />
            <path v-else d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
          </svg>
          <span class="node-name">{{ folder.name }}</span>
          <span class="node-badge">{{ folder.items.length }}</span>
        </div>

        <!-- 文件夹子项目 -->
        <div v-if="folder.open" class="folder-children">
          <div
            v-for="item in folder.items"
            :key="item.id"
            class="tree-node file-node"
            :class="{ active: activeId === item.id }"
            :title="`${item.name} · v${item.version}`"
            @click="emit('select', item.id)"
            @contextmenu.prevent.stop="emit('context-menu', { event: $event, kind: 'file', id: item.id })"
          >
            <span v-if="item.isGoldQa" class="file-icon gold-qa" title="黄金 QA">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
              </svg>
            </span>
            <span v-else class="file-icon dataset" title="基准数据集">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </span>
            <span class="node-name">{{ item.name }}</span>
            <span class="version-badge">v{{ item.version }}</span>
            <span v-if="item.pending_complete_count > 0" class="pending-dot" :title="`${item.pending_complete_count} 行待补全`"></span>
          </div>
        </div>
      </div>

      <div v-if="!folders.length" class="tree-empty">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="empty-icon">
          <circle cx="11" cy="11" r="8" />
          <line x1="21" y1="21" x2="16.65" y2="16.65" />
        </svg>
        <p>{{ search.trim() ? `无匹配结果「${search.trim()}」` : '暂无数据集，点击上方「+ 合成」或「上传」开始' }}</p>
      </div>
    </div>

    <!-- 调宽手柄 -->
    <div
      class="sidebar-resizer"
      :class="{ active: resizing }"
      title="拖拽调整侧栏宽度 · 双击复位为 280px"
      @mousedown="onResizeStart"
      @dblclick="emit('reset-size')"
    >
      <div class="resizer-bar"></div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface TreeItem {
  id: string
  name: string
  version: number
  isGoldQa?: boolean
  pending_complete_count: number
}
interface TreeFolder {
  id: string
  name: string
  open: boolean
  items: TreeItem[]
}

const props = defineProps<{
  folders: TreeFolder[]
  activeId: string
  search: string
  width: number
}>()

const emit = defineEmits<{
  (event: 'update:search', value: string): void
  (event: 'select', id: string): void
  (event: 'toggle-folder', id: string): void
  (event: 'context-menu', payload: { event: MouseEvent; kind: 'folder' | 'file'; id: string }): void
  (event: 'upload'): void
  (event: 'ai-gen'): void
  (event: 'resize', width: number): void
  (event: 'resize-end'): void
  (event: 'reset-size'): void
}>()

const resizing = ref(false)

function onSearchInput(event: Event) {
  emit('update:search', (event.target as HTMLInputElement).value)
}

/** 拖拽调宽：只算位移，宽度由父视图统一持有并下发（受最小/最大值约束）。 */
function onResizeStart(event: MouseEvent) {
  event.preventDefault()
  resizing.value = true
  const startX = event.clientX
  const startWidth = props.width
  const move = (e: MouseEvent) => emit('resize', startWidth + (e.clientX - startX))
  const stop = () => {
    resizing.value = false
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', stop)
    emit('resize-end')
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', stop)
}
</script>

<style scoped>
.nordic-sidebar {
  border-right: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
  user-select: none;
}

.sidebar-header {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-subtle);
}
.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.sidebar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13.5px;
  color: var(--text-primary);
}
.title-icon {
  color: var(--c-datasets);
}
.sidebar-actions {
  display: flex;
  gap: 4px;
}

.btn-xs {
  min-height: 24px;
  padding: 2px 7px;
  font-size: 12px;
  border-radius: 4px;
}
.btn-ghost-subtle {
  background: transparent;
  border: 1px solid transparent;
  color: var(--text-secondary);
}
.btn-ghost-subtle:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
}
.search-icon {
  position: absolute;
  left: 9px;
  color: var(--text-tertiary);
  pointer-events: none;
}
.search-input {
  width: 100%;
  height: 30px;
  padding-left: 28px;
  padding-right: 24px;
  font-size: 12.5px;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-main);
  color: var(--text-primary);
  outline: none;
  transition: border-color 0.15s ease;
}
.search-input:focus {
  border-color: var(--accent-ai);
  box-shadow: var(--focus-ring);
}
.clear-search-btn {
  position: absolute;
  right: 7px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 12px;
  cursor: pointer;
  padding: 2px;
}
.clear-search-btn:hover {
  color: var(--text-primary);
}

.tree-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background-color 0.12s ease, color 0.12s ease;
}
.tree-node:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.tree-node.active {
  background: var(--t-datasets);
  color: var(--c-datasets);
  font-weight: 600;
  border: 1px solid transparent;
}

.folder-node {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13.5px;
}
.folder-children {
  padding-left: 16px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chevron-icon {
  display: grid;
  place-items: center;
  color: var(--text-tertiary);
  transition: transform 0.15s ease;
}
.chevron-icon.rotated {
  transform: rotate(90deg);
}

.folder-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
}
.file-icon {
  display: grid;
  place-items: center;
  flex-shrink: 0;
}
.file-icon.gold-qa { color: var(--c-profiles); }
.file-icon.dataset { color: var(--c-datasets); }

.node-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.version-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg-elevated);
  color: var(--text-tertiary);
  border: 1px solid var(--border-subtle);
}
.tree-node.active .version-badge {
  background: rgba(255, 255, 255, 0.6);
  color: var(--c-datasets);
}
.pending-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-warning);
}
.node-badge {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-tertiary);
}

.tree-empty {
  padding: 36px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 12.5px;
}

.sidebar-resizer {
  position: absolute;
  top: 0;
  right: -3px;
  width: 6px;
  height: 100%;
  cursor: col-resize;
  z-index: 10;
  display: grid;
  place-items: center;
}
.resizer-bar {
  width: 2px;
  height: 24px;
  border-radius: 1px;
  background: transparent;
}
.sidebar-resizer:hover .resizer-bar,
.sidebar-resizer.active .resizer-bar {
  background: var(--accent-ai);
}

/* ─── 主工作区 ─── */
</style>
