<template>
  <tr
    class="data-row"
    :class="{ 'row-checked': row.checked, 'row-incomplete': !row.q.trim() || !row.r.trim(), 'row-focused': focused }"
    @contextmenu.prevent="emit('row-context', $event)"
    @dblclick="emit('edit-row')"
  >
    <!-- 居中自定义多选框列 (支持直接点击与 Shift 连选) -->
    <td class="td-chk" :class="{ 'cell-cursor': focusedField === 'chk' }" @click.stop="emit('check-click', $event)">
      <div class="clean-chk-box" :class="{ checked: row.checked }" :title="`勾选第 ${row.row_no} 行（支持 Shift 连选）`" role="checkbox" :aria-checked="row.checked">
        <svg v-if="row.checked" class="chk-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>
    </td>

    <!-- 行号 -->
    <td class="mono td-num" :class="{ 'cell-cursor': focusedField === 'row_no' }" @click="emit('cell-cursor', 'row_no')">
      {{ row.row_no }}
    </td>

    <!-- 测试问句 (14px 舒适字阶) -->
    <td class="cell-edit" :class="{ 'cell-invalid': !row.q.trim(), 'cell-cursor': focusedField === 'q' }" @click="emit('cell-click', 'q')">
      <input
        v-if="editingField === 'q'"
        :value="row.q"
      @input="emit('update-field', 'q', ($event.target as HTMLInputElement).value)"
        class="inline-input"
        placeholder="输入测试问题..."
        :aria-label="`编辑第 ${row.row_no} 行测试问题`"
        autofocus
        @blur="emit('finish')"
        @keyup.enter="emit('finish')"
        @keyup.esc="emit('cancel')"
      />
      <div v-else class="cell-content primary-text" :class="{ empty: !row.q.trim() }" v-html="highlight(row.q || '（空问句 · 点击录入）')"></div>
    </td>

    <!-- 参考答案 (14px 舒适字阶) -->
    <td class="cell-edit" :class="{ 'cell-invalid': !row.r.trim(), 'cell-cursor': focusedField === 'r' }" @click="emit('cell-click', 'r')">
      <input
        v-if="editingField === 'r'"
        :value="row.r"
      @input="emit('update-field', 'r', ($event.target as HTMLInputElement).value)"
        class="inline-input"
        placeholder="输入标准答案..."
        :aria-label="`编辑第 ${row.row_no} 行标准答案`"
        autofocus
        @blur="emit('finish')"
        @keyup.enter="emit('finish')"
        @keyup.esc="emit('cancel')"
      />
      <div v-else class="cell-content" :class="{ empty: !row.r.trim() }" v-html="highlight(row.r || '（空答案 · 点击录入）')"></div>
    </td>

    <!-- 上下文注入 -->
    <td class="cell-edit" :class="{ 'cell-cursor': focusedField === 'c' }" @click="emit('cell-click', 'c')">
      <input
        v-if="editingField === 'c'"
        :value="row.c"
      @input="emit('update-field', 'c', ($event.target as HTMLInputElement).value)"
        class="inline-input"
        placeholder="注入 Context..."
        :aria-label="`编辑第 ${row.row_no} 行上下文`"
        autofocus
        @blur="emit('finish')"
        @keyup.enter="emit('finish')"
        @keyup.esc="emit('cancel')"
      />
      <div v-else class="cell-content mono-sm" :class="{ placeholder: !row.c }" v-html="highlight(row.c || '—')"></div>
    </td>

    <!-- 标签 -->
    <td class="cell-edit" :class="{ 'cell-cursor': focusedField === 'tags' }" @click="emit('cell-click', 'tags')">
      <input
        v-if="editingField === 'tags'"
        :value="row.tags"
      @input="emit('update-field', 'tags', ($event.target as HTMLInputElement).value)"
        class="inline-input"
        placeholder="业务标签..."
        :aria-label="`编辑第 ${row.row_no} 行标签`"
        autofocus
        @blur="emit('finish')"
        @keyup.enter="emit('finish')"
        @keyup.esc="emit('cancel')"
      />
      <div v-else class="cell-content">
        <span v-if="row.tags" class="tag-pill" v-html="highlight(row.tags)"></span>
        <span v-else class="placeholder">常规</span>
      </div>
    </td>

    <!-- 难度 -->
    <td class="cell-edit" :class="{ 'cell-cursor': focusedField === 'difficulty' }" @click="emit('cell-click', 'difficulty')">
      <select
        v-if="editingField === 'difficulty'"
        :value="row.difficulty"
      @change="onSelectChange('difficulty', $event)"
        class="inline-select"
        :aria-label="`选择第 ${row.row_no} 行难度`"
        autofocus
        @blur="emit('finish')"
        @keyup.esc="emit('cancel')"
      >
        <option>简单</option>
        <option>中等</option>
        <option>高</option>
      </select>
      <div v-else class="cell-content">
        <span class="diff-badge" :class="`diff-${row.difficulty}`">
          {{ row.difficulty || '简单' }}
        </span>
      </div>
    </td>

    <!-- 自定义扩展列 -->
    <td v-for="col in columns" :key="col.key" class="cell-edit" :class="{ 'cell-cursor': focusedField === col.key }" @click="emit('cell-click', col.key)">
      <input
        v-if="editingField === col.key"
        :value="row.extras[col.key]"
      @input="emit('update-field', col.key, ($event.target as HTMLInputElement).value)"
        class="inline-input"
        :placeholder="`输入 ${col.name}...`"
        :aria-label="`编辑第 ${row.row_no} 行 ${col.name}`"
        autofocus
        @blur="emit('finish')"
        @keyup.enter="emit('finish')"
        @keyup.esc="emit('cancel')"
      />
      <div v-else class="cell-content" :class="{ placeholder: !row.extras[col.key] }">
        {{ row.extras[col.key] || '—' }}
      </div>
    </td>

    <!-- 校验状态 -->
    <td>
      <span v-if="!row.q.trim() || !row.r.trim()" class="status-tag-amber" title="缺少问句或答案">待补全</span>
      <span v-else class="status-tag-green">达标</span>
    </td>

    <!-- 操作区 -->
    <td class="td-actions">
      <div class="action-links">
        <button class="icon-link" title="详细编辑" :aria-label="`详细编辑第 ${row.row_no} 行`" @click.stop="emit('edit-row')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" /><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" /></svg>
        </button>
        <button class="icon-link danger" title="删除行" :aria-label="`删除第 ${row.row_no} 行`" @click.stop="emit('delete-row')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /></svg>
        </button>
      </div>
    </td>
  </tr>
</template>

<script setup lang="ts">
/**
 * 单行渲染：只负责展示与交互上报，行数据与编辑态都由父视图持有。
 * 单元格输入通过 update-field 事件回传，避免直接改写 props。
 */
interface EditableRow {
  row_no: number
  q: string
  r: string
  c: string
  tags: string
  difficulty: string
  checked: boolean
  extras: Record<string, string>
}
interface ExtraColumn {
  key: string
  name: string
}

defineProps<{
  row: EditableRow
  columns: ExtraColumn[]
  focusedField: string | null
  editingField: string | null
  focused: boolean
  highlight: (text: string) => string
}>()

const emit = defineEmits<{
  (event: 'cell-click', field: string): void
  (event: 'cell-cursor', field: string): void
  (event: 'check-click', payload: MouseEvent): void
  (event: 'update-field', field: string, value: string): void
  (event: 'finish'): void
  (event: 'cancel'): void
  (event: 'edit-row'): void
  (event: 'delete-row'): void
  (event: 'row-context', payload: MouseEvent): void
}>()

/** 难度下拉：先回写字段再结束编辑（原生 change 只触发一次）。 */
function onSelectChange(field: string, event: Event) {
  emit('update-field', field, (event.target as HTMLSelectElement).value)
  emit('finish')
}
</script>

<style scoped>
/* 行内容样式：父视图 scoped 样式不作用于子组件，随组件携带一份。 */
td {
  padding: 8px 12px;
  font-size: 13.5px;
  color: var(--text-primary);
  vertical-align: middle;
  border-bottom: 1px solid var(--border-subtle);
  height: 48px;
  background: var(--bg-main);
}

.clean-chk-box {
  width: 17px;
  height: 17px;
  border-radius: 4px;
  border: 1.5px solid var(--border-subtle);
  background: var(--bg-main);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 0.12s ease;
}
.clean-chk-box:hover {
  border-color: var(--accent-ai);
}
.clean-chk-box.checked {
  background: var(--accent-ai);
  border-color: var(--accent-ai);
}

.req-star {
  color: var(--accent-error);
}

.custom-th {
  background: var(--bg-elevated) !important;
}
.th-flex {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}
.th-del-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
  padding: 1px;
}
.th-del-btn:hover { color: var(--accent-error); }

.data-row {
  transition: background-color 0.08s ease;
}
.data-row:hover td {
  background: var(--row-hover);
}
.data-row.row-checked td {
  background: var(--t-datasets);
}
.data-row.row-incomplete td {
  background: rgba(245, 158, 11, 0.04);
}

.cell-cursor {
  box-shadow: inset 0 0 0 1.5px var(--accent-ai);
}

.td-num {
  font-size: 12px;
  color: var(--text-tertiary);
}

.cell-edit {
  cursor: text;
  transition: background-color 0.1s ease;
  position: relative;
}
.cell-edit:hover {
  outline: 1px dashed var(--accent-ai);
  outline-offset: -2px;
  border-radius: 4px;
}

.cell-content {
  min-height: 24px;
  display: flex;
  align-items: center;
  word-break: break-word;
  line-height: 1.5;
  font-size: 13.5px;
}
.cell-content.primary-text {
  font-weight: 500;
  color: var(--text-primary);
}
.cell-content.empty {
  color: var(--accent-warning);
  font-style: italic;
  font-size: 12.5px;
}
.cell-content.placeholder {
  color: var(--text-tertiary);
}
.cell-content.mono-sm {
  font-family: var(--font-mono);
  font-size: 12px;
}

:deep(.highlight-match) {
  /* 半透明高亮在深浅两套主题下都成立，避免深色页出现荧光黄块 */
  background: rgba(250, 204, 21, 0.45);
  color: var(--text-primary);
  padding: 0 2px;
  border-radius: 2px;
}

.inline-input {
  width: 100%;
  padding: 4px 7px;
  font: inherit;
  font-size: 13px;
  background: var(--bg-main);
  border: 1.5px solid var(--accent-ai);
  border-radius: 4px;
  outline: none;
  color: var(--text-primary);
  box-shadow: var(--focus-ring);
}
.inline-select {
  height: 28px;
  font-size: 12.5px;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--accent-ai);
  background: var(--bg-main);
  color: var(--text-primary);
}

.cell-invalid {
  border-bottom: 1px dashed var(--accent-error) !important;
}

.tag-pill {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
  font-size: 11.5px;
}
.diff-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11.5px;
  font-weight: 500;
}
.diff-简单 { background: var(--t-cases); color: var(--c-cases); }
.diff-中等 { background: var(--t-profiles); color: var(--c-profiles); }
.diff-高 { background: var(--t-stress); color: var(--c-stress); }

.status-tag-green {
  font-size: 12px;
  color: var(--accent-success);
  font-weight: 500;
}
.status-tag-amber {
  font-size: 12px;
  color: var(--accent-warning);
  font-weight: 500;
}
.status-tag-clean {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--t-cases);
  color: var(--c-cases);
  font-size: 12px;
  font-weight: 500;
}

.td-actions {
  text-align: right;
  white-space: nowrap;
}
.action-links {
  display: inline-flex;
  gap: 3px;
  opacity: 0.4;
  transition: opacity 0.12s ease;
}
.data-row:hover .action-links {
  opacity: 1;
}
.icon-link {
  background: none;
  border: none;
  padding: 4px;
  border-radius: 4px;
  color: var(--text-tertiary);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.icon-link:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.icon-link.danger:hover {
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-error);
}

</style>
