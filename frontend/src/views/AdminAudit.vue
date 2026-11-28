<template>
  <div class="workbench-page">
    <header class="workbench-intro">
      <p>按时间、动作或对象 ID 查询平台的操作记录。</p>
      <n-button :disabled="loading" @click="reload">刷新</n-button>
    </header>

    <section class="aa-toolbar workbench-filters" aria-label="审计日志筛选">
      <n-date-picker
        v-model:value="range"
        class="workbench-filter workbench-filter-wide"
        type="daterange"
        clearable
        size="medium"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
      />
      <n-select v-model:value="action" class="workbench-filter" :options="actionOptions" clearable placeholder="全部动作" :input-props="{ 'aria-label': '筛选动作' }" filterable @update:value="reload" />
      <n-input v-model:value="keyword" class="workbench-filter" clearable placeholder="筛选对象 ID" :input-props="{ 'aria-label': '筛选对象 ID' }" @keyup.enter="reload" />
      <n-button :loading="loading" @click="reload">查询</n-button>
      <span class="aa-total workbench-count">共 {{ total }} 条</span>
    </section>

    <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

    <n-spin :show="loading">
      <div v-if="rows.length" class="workbench-table-panel">
        <div class="workbench-table-scroll" role="region" aria-label="审计日志表格" tabindex="0">
          <table class="aa-table ds-table">
            <thead>
              <tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>IP</th><th>明细</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <td class="aa-time">{{ fmt(row.at) }}</td>
                <td class="aa-actor">{{ actorName(row) }}</td>
                <td class="aa-action"><span>{{ auditActionLabel(row.action) }}</span><code>{{ row.action }}</code></td>
                <td class="aa-target">
                  <span v-if="row.target">{{ row.target.type || '—' }}<template v-if="row.target.id"> · {{ row.target.id.slice(0, 8) }}</template></span>
                  <span v-else>—</span>
                </td>
                <td class="aa-ip">{{ row.ip || '—' }}</td>
                <td class="aa-detail">{{ detailText(row) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="aa-more workbench-table-footer">
          <n-button v-if="hasMore" size="small" :loading="loading" @click="loadMore">加载更多</n-button>
          <span v-else-if="total > rows.length">
            已显示最近 {{ rows.length }} 条（共 {{ total }} 条），更早的记录请缩小时间范围
          </span>
          <span v-else>已到末尾</span>
        </div>
      </div>
      <n-empty v-else :description="error ? '暂时无法读取审计日志' : '这个范围内没有审计记录'" />
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { adminConsole, type AuditActionOption, type AuditEntry } from '../api/adminConsole'
import { auditActionLabel } from '../utils/auditActions'

const rows = ref<AuditEntry[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const range = ref<[number, number] | null>(null)
const action = ref<string | null>(null)
const keyword = ref('')
const pageSize = 50
const actionItems = ref<AuditActionOption[]>([])

const actionOptions = computed(() =>
  actionItems.value.map((item) => ({
    label: `${auditActionLabel(item.action)}（${item.count}）`,
    value: item.action,
  })),
)

/** 日期范围转 ISO；to 取当天 23:59:59，避免「当天查不到」的困惑。 */
const rangeParams = () => {
  if (!range.value) return {}
  const [from, to] = range.value
  const end = new Date(to)
  end.setHours(23, 59, 59, 999)
  return { from: new Date(from).toISOString(), to: end.toISOString() }
}

const hasMore = computed(() => rows.value.length < total.value)

/** 服务端已把操作人解析成展示名；缺失时退回 id 尾段，便于对日志。 */
function actorName(row: AuditEntry): string {
  if (row.actor_name) return row.actor_name
  return row.actor_id ? '成员 ' + row.actor_id.slice(0, 6) : '系统'
}

function detailText(row: AuditEntry): string {
  const detail = row.detail || {}
  const entries = Object.entries(detail).filter(([, v]) => v !== null && v !== '')
  if (!entries.length) return '—'
  return entries.map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' · ').slice(0, 80)
}

function fmt(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

async function loadPage(reset: boolean): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const page = await adminConsole.audit({
      ...rangeParams(),
      action: action.value || undefined,
      target_id: keyword.value.trim() || undefined,
      offset: reset ? 0 : rows.value.length,
      limit: pageSize,
    })
    rows.value = reset ? page.items : [...rows.value, ...page.items]
    total.value = page.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    if (reset) {
      rows.value = []
      total.value = 0
    }
  } finally {
    loading.value = false
  }
}

function reload(): void {
  void loadPage(true)
}

function loadMore(): void {
  void loadPage(false)
}

async function loadActions(): Promise<void> {
  try {
    actionItems.value = await adminConsole.auditActions()
  } catch {
    // 动作下拉失败不阻塞日志主体；仍可按键值手动查询。
  }
}

onMounted(() => {
  void loadActions()
  void loadPage(true)
})
</script>

<style scoped>
.aa-table { min-width: 40rem; font-size: 13px; }
.aa-time { white-space: nowrap; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.aa-actor, .aa-target, .aa-action { overflow-wrap: anywhere; }
.aa-action code { display: block; font: 11px/1.5 var(--font-mono); color: var(--text-secondary); }
.aa-target, .aa-ip, .aa-detail { color: var(--text-secondary); }
.aa-detail { max-width: 18rem; overflow-wrap: anywhere; }
</style>
