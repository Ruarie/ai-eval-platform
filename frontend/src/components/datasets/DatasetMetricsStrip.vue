<template>
  <div class="metrics-strip">
    <div class="strip-left">
      <span class="strip-label">样本筛选:</span>
      <div class="filter-pills-bar" v-if="!isGoldQa">
        <button
          class="filter-pill"
          :class="{ active: mode === 'all' }"
          @click="emit('update:mode', 'all')"
        >
          全部 <b class="pill-num">{{ total }}</b>
        </button>
        <button
          class="filter-pill pill-clean"
          :class="{ active: mode === 'clean' }"
          @click="emit('update:mode', 'clean')"
        >
          达标 <b class="pill-num">{{ cleanCount }}</b>
        </button>
        <button
          v-if="pendingCount > 0"
          class="filter-pill pill-amber"
          :class="{ active: mode === 'pending' }"
          @click="emit('update:mode', mode === 'pending' ? 'all' : 'pending')"
        >
          待补全 <b class="pill-num">{{ pendingCount }}</b>
        </button>
      </div>
      <span v-else class="strip-text mono">{{ goldQaRows }} 行</span>

      <template v-if="!isGoldQa">
        <span class="strip-divider"></span>
        <span v-if="pendingCount === 0" class="status-indicator-success">
          ✓ 100% 格式达标
        </span>
        <span v-else class="status-indicator-warning">
          需补全 {{ pendingCount }} 行样本
        </span>

        <template v-if="customColCount">
          <span class="strip-divider"></span>
          <span class="strip-text">扩展列: {{ customColCount }}</span>
        </template>
      </template>
    </div>

    <div class="grow"></div>

    <!-- 键盘流提示 (可悬停查看) -->
    <div class="keyboard-flow-hint" title="支持键盘方向键与快捷键无障碍操作">
      <span class="kbd-hint"><kbd>↑↓←→</kbd> 移动</span>
      <span class="kbd-hint"><kbd>Enter</kbd> 编辑</span>
      <span class="kbd-hint"><kbd>Space</kbd> 勾选</span>
    </div>

    <span class="strip-divider"></span>

    <!-- 主评分指标选择器 -->
    <div v-if="!isGoldQa && showMetric" class="metric-control">
      <span class="metric-label">主评分指标:</span>
      <select :value="metric" class="metric-select" aria-label="选择主评分指标" @change="emit('update:metric', ($event.target as HTMLSelectElement).value)">
        <option value="contain">Contain (包含匹配)</option>
        <option value="exact">Exact (完全一致)</option>
        <option value="regex">Regex (正则表达式)</option>
        <option value="rouge_l">ROUGE-L (最长公共子序列)</option>
        <option value="bleu">BLEU (自然语言平滑)</option>
      </select>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 数据集指标与筛选条：只负责展示与筛选交互，统计值由页面计算后下发。 */
const props = defineProps<{
  /** 样本总数与达标数（未筛选前）。 */
  total: number
  cleanCount: number
  pendingCount: number
  isGoldQa: boolean
  goldQaRows: number
  customColCount: number
  mode: 'all' | 'clean' | 'pending'
  metric: string
  showMetric: boolean
}>()

const emit = defineEmits<{
  (event: 'update:mode', value: 'all' | 'clean' | 'pending'): void
  (event: 'update:metric', value: string): void
}>()
void props
</script>

<style scoped>
.metrics-strip {
  padding: 8px 18px;
  background: var(--bg-elevated);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12.5px;
}
.strip-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.strip-label {
  color: var(--text-tertiary);
}
.strip-text {
  color: var(--text-primary);
  font-weight: 500;
}
.strip-divider {
  width: 1px;
  height: 14px;
  background: var(--border-subtle);
}
.filter-pills-bar {
  display: flex;
  align-items: center;
  gap: 6px;
}
.filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 9px;
  font-size: 12px;
  border-radius: 14px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-main);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.12s ease;
}
.filter-pill:hover {
  border-color: var(--accent-ai);
  color: var(--text-primary);
}
.filter-pill.active {
  background: var(--text-primary);
  color: var(--bg-main);
  border-color: var(--text-primary);
  font-weight: 600;
}
.filter-pill.pill-clean.active {
  background: var(--accent-success);
  border-color: var(--accent-success);
  color: #FFFFFF;
}
.filter-pill.pill-amber.active {
  background: var(--accent-warning);
  border-color: var(--accent-warning);
  color: #FFFFFF;
}
.pill-num {
  font-family: var(--font-mono);
  font-size: 11px;
}
.status-indicator-warning {
  color: var(--accent-warning);
  font-weight: 500;
}
.status-indicator-success {
  color: var(--accent-success);
  font-weight: 500;
}
.keyboard-flow-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: var(--text-tertiary);
}
.kbd-hint kbd {
  font-family: var(--font-mono);
  font-size: 10.5px;
  padding: 1px 4px;
  border-radius: 3px;
  background: var(--bg-main);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}
.metric-control {
  display: flex;
  align-items: center;
  gap: 6px;
}
.metric-label {
  color: var(--text-tertiary);
  font-size: 12px;
}
.metric-select {
  height: 26px;
  font-size: 12px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-main);
  color: var(--text-primary);
  outline: none;
}
.metric-select:focus {
  border-color: var(--accent-ai);
}
.step-badge.active {
  color: var(--accent-ai);
  font-weight: 600;
}
.step-badge.active .step-idx {
  background: var(--accent-ai);
  color: #FFFFFF;
  border-color: var(--accent-ai);
}
.tab-pill.active {
  background: var(--bg-main);
  color: var(--text-primary);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
</style>
