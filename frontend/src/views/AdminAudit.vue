<template>
  <div class="aa-page">
    <header class="aa-head">
      <div>
        <div class="eyebrow">管理后台</div>
        <h1>审计日志</h1>
        <p>写操作全量留痕：新建、编辑、删除、远程执行、账号与协议档变更。只读，不可修改。</p>
      </div>
      <div class="aa-head-actions">
        <n-button :disabled="loading" @click="reload">刷新</n-button>
      </div>
    </header>

    <section class="aa-toolbar">
      <n-date-picker
        v-model:value="range"
        type="daterange"
        clearable
        size="medium"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        style="width: 260px"
      />
      <n-select v-model:value="action" :options="actionOptions" clearable placeholder="全部动作" style="width: 200px" filterable />
      <n-input v-model:value="keyword" clearable placeholder="筛选对象 ID" style="width: 200px" @keyup.enter="reload" />
      <n-button :loading="loading" @click="reload">查询</n-button>
      <span class="aa-total">共 {{ total }} 条</span>
    </section>

    <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

    <n-spin :show="loading">
      <div v-if="rows.length" class="aa-table-wrap">
        <table class="aa-table">
          <thead>
            <tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>IP</th><th>明细</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in paged" :key="row.id">
              <td class="aa-time">{{ fmt(row.at) }}</td>
              <td class="aa-actor">{{ actorName(row) }}</td>
              <td><code>{{ row.action }}</code></td>
              <td class="aa-target">
                <span v-if="row.target">{{ row.target.type || '—' }}<template v-if="row.target.id"> · {{ row.target.id.slice(0, 8) }}</template></span>
                <span v-else>—</span>
              </td>
              <td class="aa-ip">{{ row.ip || '—' }}</td>
              <td class="aa-detail" :title="detailText(row)">{{ detailText(row) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="aa-more">
          <n-button v-if="hasMore" size="small" :loading="loading" @click="loadMore">加载更多</n-button>
          <span v-else-if="total > rows.length" class="aa-cap">
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
import { adminConsole, type AuditEntry } from '../api/adminConsole'

const ACTIONS = [
  'resource_create', 'resource_update', 'resource_delete', 'resource_clone',
  'workspace_remote_exec', 'workspace_remote_write',
  'user_create', 'user_disable', 'user_reset_password',
  'profile_update', 'settings_update',
]

const rows = ref<AuditEntry[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const range = ref<[number, number] | null>(null)
const action = ref<string | null>(null)
const keyword = ref('')
const pageSize = 50

const actionOptions = ACTIONS.map((value) => ({ label: value, value }))

/** 日期范围转 ISO；to 取当天 23:59:59，避免「当天查不到」的困惑。 */
const rangeParams = () => {
  if (!range.value) return {}
  const [from, to] = range.value
  const end = new Date(to)
  end.setHours(23, 59, 59, 999)
  return { from: new Date(from).toISOString(), to: end.toISOString() }
}

const filtered = computed(() => {
  let list = rows.value
  if (action.value) list = list.filter((row) => row.action === action.value)
  const kw = keyword.value.trim()
  if (kw) list = list.filter((row) => (row.target?.id || '').includes(kw))
  return list
})

const pages = ref(1)
const paged = computed(() => filtered.value.slice(0, pageSize * Math.max(1, pages.value)))
const hasMore = computed(() => paged.value.length < filtered.value.length)

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

async function reload(): Promise<void> {
  loading.value = true
  error.value = ''
  pages.value = 1
  try {
    const page = await adminConsole.audit({ ...rangeParams(), offset: 0, limit: 200 })
    rows.value = page.items
    total.value = page.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    rows.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function loadMore(): void {
  pages.value += 1
}

onMounted(reload)
</script>

<style scoped>
.aa-page { display: flex; flex-direction: column; gap: 14px; }
.aa-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.eyebrow { font-size: 12px; letter-spacing: .12em; color: var(--text-tertiary); text-transform: uppercase; }
.aa-head h1 { margin: 4px 0; font-size: 22px; }
.aa-head p { margin: 0; color: var(--text-secondary); font-size: 13.5px; }

.aa-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.aa-total { font-size: 12px; color: var(--text-tertiary); margin-left: auto; }

.aa-table-wrap { border: 1px solid var(--border-subtle); border-radius: 14px; background: var(--bg-card); overflow: hidden; }
.aa-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.aa-table th { text-align: left; padding: 10px 12px; font-size: 11.5px; color: var(--text-tertiary); background: var(--bg-elevated); font-weight: 600; }
.aa-table td { padding: 9px 12px; border-top: 1px solid var(--border-subtle); }
.aa-table code { font-size: 11.5px; }
.aa-time { white-space: nowrap; color: var(--text-secondary); font-variant-numeric: tabular-nums; }
.aa-actor { white-space: nowrap; }
.aa-target, .aa-ip { color: var(--text-tertiary); font-size: 11.5px; }
.aa-detail { color: var(--text-tertiary); font-size: 11.5px; max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.aa-more { padding: 12px; text-align: center; font-size: 12px; color: var(--text-tertiary); display: flex; gap: 10px; justify-content: center; align-items: center; }
.aa-cap { color: var(--text-tertiary); }
</style>
