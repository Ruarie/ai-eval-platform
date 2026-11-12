<template>
  <!-- 4. 底部固定分页工具栏 (Table Pagination Bar) -->
  <div v-if="!isGoldQa && allCount > 0" class="table-pagination-bar">
    <div class="pagination-info">
      <span class="pagination-total">
        共 <strong class="mono">{{ total }}</strong> 条样本
        <span class="pagination-pages mono">（第 {{ page }} / {{ totalPages }} 页）</span>
      </span>
      <span v-if="filtered" class="pagination-filter-tag">
        已从全部 {{ allCount }} 条中过滤
      </span>
      <span v-if="selectedCount > 0" class="pagination-selection-tag">
        已勾选 {{ selectedCount }} 条
      </span>
    </div>
    <div class="pagination-controls">
      <n-pagination
          :page="page"
          :page-size="pageSize"
          :item-count="total"
          :page-sizes="[10, 20, 50, 100]"
          show-size-picker
          show-quick-jumper
          @update:page="emit('update:page', $event)"
          @update:page-size="emit('update:pageSize', $event)"
        />
    </div>
  </div>

  <!-- 5. 底部浮动批量操作栏 (Floating Action Dock) -->
  <transition name="slide-up">
    <div v-if="selectedCount > 0" class="floating-batch-dock">
      <div class="batch-dock-info">
        <span class="batch-dock-badge">{{ selectedCount }}</span>
        <span class="batch-dock-text">已选择 / 筛选共 {{ total }} 行</span>
      </div>
      <div class="batch-dock-actions">
        <button
          v-if="selectedCount < total"
          class="btn btn-ghost btn-sm"
          @click="emit('select-all')"
        >
          全选所有筛选行 ({{ total }})
        </button>
        <button class="btn btn-secondary btn-sm" @click="emit('export')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" /></svg>
          导出选中 JSONL
        </button>
        <button class="btn btn-danger btn-sm" @click="emit('delete')">
          批量删除 ({{ selectedCount }})
        </button>
        <button class="btn btn-ghost btn-sm" @click="emit('clear')">
          取消选择
        </button>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  page: number
  pageSize: number
  /** 筛选后的总行数（分页控件与批量栏都以它为准）。 */
  total: number
  /** 未筛选的总行数，用于「已从全部 N 条中过滤」提示。 */
  allCount: number
  selectedCount: number
  filtered: boolean
  isGoldQa: boolean
}>()

const emit = defineEmits<{
  (event: 'update:page', value: number): void
  (event: 'update:pageSize', value: number): void
  (event: 'select-all'): void
  (event: 'export'): void
  (event: 'delete'): void
  (event: 'clear'): void
}>()

const totalPages = computed(() =>
  Math.max(1, Math.ceil(props.total / Math.max(1, props.pageSize))),
)
</script>

<style scoped>
.table-pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 18px;
  background: var(--bg-elevated);
  border-top: 1px solid var(--border-subtle);
  min-height: 46px;
  flex-shrink: 0;
  gap: 16px;
  z-index: 10;
}
.pagination-info {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  color: var(--text-secondary);
  flex-wrap: wrap;
}
.pagination-total strong {
  color: var(--text-primary);
}
.pagination-pages {
  color: var(--text-tertiary);
  font-size: 11.5px;
  margin-left: 4px;
}
.pagination-filter-tag {
  font-size: 11.5px;
  color: var(--accent-ai);
  background: color-mix(in srgb, var(--accent-ai) 10%, transparent);
  padding: 1px 7px;
  border-radius: 4px;
  border: 1px solid color-mix(in srgb, var(--accent-ai) 22%, transparent);
}
.pagination-selection-tag {
  font-size: 11.5px;
  color: var(--c-datasets);
  background: var(--t-datasets);
  padding: 1px 7px;
  border-radius: 4px;
  font-weight: 500;
}
.pagination-controls {
  display: flex;
  align-items: center;
}

/* ─── 底部浮动批量操作栏 (Floating Action Dock) ─── */
.floating-batch-dock {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 18px;
  border-radius: 24px;
  background: rgba(17, 24, 39, 0.92);
  color: #FFFFFF;
  backdrop-filter: blur(12px);
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.15);
}
.batch-dock-info {
  display: flex;
  align-items: center;
  gap: 8px;
}
.batch-dock-badge {
  background: var(--accent-ai);
  color: #FFFFFF;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 12px;
}
.batch-dock-text {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}
.batch-dock-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.floating-batch-dock .btn-secondary {
  background: rgba(255, 255, 255, 0.12);
  color: #FFFFFF;
  border: 1px solid rgba(255, 255, 255, 0.2);
}
.floating-batch-dock .btn-secondary:hover {
  background: rgba(255, 255, 255, 0.2);
}
.floating-batch-dock .btn-ghost {
  color: rgba(255, 255, 255, 0.7);
}
.floating-batch-dock .btn-ghost:hover {
  color: #FFFFFF;
  background: rgba(255, 255, 255, 0.1);
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.24s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translate(-50%, 20px);
}
</style>
