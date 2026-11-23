<template>
  <div class="ao-page">
    <header class="ao-head">
      <div>
        <div class="eyebrow">管理后台</div>
        <h1>平台概览</h1>
        <p>成员、协作、任务、资源、存储与审计的一屏口径；数据由服务端聚合，刷新即最新。</p>
      </div>
      <div class="ao-head-actions">
        <n-button :loading="loading" @click="load">刷新</n-button>
        <n-button @click="$router.push('/admin/audit')">审计日志</n-button>
      </div>
    </header>

    <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

    <n-spin :show="loading">
      <section class="ao-cards">
        <article v-for="card in cards" :key="card.key" class="ao-card" :style="{ '--c': card.color }">
          <div class="ao-card-top">
            <span>{{ card.label }}</span>

          </div>
          <b>{{ card.value }}</b>
          <small>{{ card.sub }}</small>
        </article>
      </section>

      <div class="ao-grid">
        <section class="ao-panel">
          <div class="ao-panel-head">
            <h2>资源分布</h2>
            <span>共 {{ data?.resources.total ?? '—' }} 个 · 使用 {{ data?.resources.usage_total ?? '—' }} 次</span>
          </div>
          <div v-if="kindBars.length" class="ao-bars">
            <div v-for="bar in kindBars" :key="bar.kind" class="ao-bar">
              <span class="ao-bar-label">{{ bar.label }}</span>
              <div class="ao-bar-track">
                <div class="ao-bar-fill" :style="{ width: bar.width + '%', background: bar.color }"></div>
              </div>
              <span class="ao-bar-value">{{ bar.value }}</span>
            </div>
          </div>
          <n-empty v-else description="还没有资源" size="small" />
        </section>

        <section class="ao-panel">
          <div class="ao-panel-head">
            <h2>任务状态</h2>
            <span>近 7 天 {{ data?.tasks.total_7d ?? '—' }} 个</span>
          </div>
          <div v-if="taskBars.length" class="ao-bars">
            <div v-for="bar in taskBars" :key="bar.key" class="ao-bar">
              <span class="ao-bar-label">{{ bar.label }}</span>
              <div class="ao-bar-track">
                <div class="ao-bar-fill" :style="{ width: bar.width + '%', background: bar.color }"></div>
              </div>
              <span class="ao-bar-value">{{ bar.value }}</span>
            </div>
          </div>
          <n-empty v-else description="近 7 天没有任务" size="small" />
        </section>

        <section class="ao-panel">
          <div class="ao-panel-head">
            <h2>审计热点</h2>
            <span>近 24 小时 {{ data?.audit_24h ?? '—' }} 条</span>
          </div>
          <ul v-if="topActions.length" class="ao-rank">
            <li v-for="(item, index) in topActions" :key="item.action">
              <span class="ao-no">{{ index + 1 }}</span>
              <span class="ao-rank-name">{{ auditActionLabel(item.action) }}</span>
              <code>{{ item.action }}</code>
              <span class="ao-rank-value">{{ item.count }}</span>
            </li>
          </ul>
          <n-empty v-else description="近 24 小时没有审计事件" size="small" />
        </section>

        <section class="ao-panel ao-panel-wide">
          <div class="ao-panel-head">
            <h2>最近操作</h2>
            <router-link class="ao-more" to="/admin/audit">查看全部 →</router-link>
          </div>
          <table v-if="recent.length" class="ao-table">
            <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>对象</th><th>IP</th></tr></thead>
            <tbody>
              <tr v-for="row in recent" :key="row.id">
                <td class="ao-time">{{ fmtTime(row.ts) }}</td>
                <td>{{ row.user_name || '—' }}</td>
                <td><code>{{ row.action }}</code></td>
                <td class="ao-target">{{ row.target_type || '—' }}<span v-if="row.target_id"> · {{ row.target_id.slice(0, 8) }}</span></td>
                <td class="ao-ip">{{ row.ip || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <n-empty v-else description="还没有审计记录" size="small" />
        </section>
      </div>

      <p class="ao-foot">统计生成于 {{ fmtTime(data?.generated_at) }}</p>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { adminConsole, type AdminOverview } from '../api/adminConsole'
import { auditActionLabel } from '../utils/auditActions'

const data = ref<AdminOverview | null>(null)
const loading = ref(false)
const error = ref('')

const KIND_META: Record<string, { label: string; color: string }> = {
  agent: { label: 'Agent', color: 'var(--c-agent)' },
  skill: { label: 'Skill', color: 'var(--c-datasets)' },
  script: { label: 'Script', color: 'var(--c-reports)' },
  rule: { label: 'Rule', color: 'var(--c-profiles)' },
  rag: { label: 'RAG', color: 'var(--c-kb)' },
}

const STATUS_META: Record<string, { label: string; color: string }> = {
  queued: { label: '排队中', color: 'var(--c-dispatch)' },
  running: { label: '执行中', color: 'var(--c-tasks)' },
  succeeded: { label: '成功', color: 'var(--accent-success)' },
  failed: { label: '失败', color: 'var(--accent-error)' },
  cancelled: { label: '已取消', color: 'var(--text-tertiary)' },
  awaiting_case_confirm: { label: '待确认', color: 'var(--accent-warning)' },
}

interface OverviewCard { key: string; label: string; value: string | number; sub: string; color: string }

/** 文件体量按 KB / MB 自适应，避免小文件一律显示 0.0 MB。 */
function formatBytes(bytes?: number): string {
  if (bytes === undefined || bytes === null) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const cards = computed<OverviewCard[]>(() => {
  const d = data.value
  const size = formatBytes(d?.storage.bytes)
  return [
    { key: 'users', label: '成员', value: d?.users.total ?? '—', sub: `近 7 天活跃 ${d?.users.active_7d ?? '—'} · 停用 ${d?.users.disabled ?? '—'}`, color: 'var(--c-users)' },
    { key: 'sessions', label: '会话', value: d?.sessions.total ?? '—', sub: `近 7 天新增 ${d?.sessions.new_7d ?? '—'} · 共享 ${d?.sessions.shared ?? '—'}`, color: 'var(--c-agent)' },
    { key: 'tasks', label: '任务（7 天）', value: d?.tasks.total_7d ?? '—', sub: `成功 ${d?.tasks.by_status.succeeded ?? 0} · 失败 ${d?.tasks.by_status.failed ?? 0}`, color: 'var(--c-tasks)' },
    { key: 'resources', label: '能力资源', value: d?.resources.total ?? '—', sub: `团队 ${d?.resources.team ?? '—'} · 私有 ${d?.resources.private ?? '—'}`, color: 'var(--c-datasets)' },
    { key: 'storage', label: '文件存储', value: size, sub: `${d?.storage.files ?? '—'} 个文件 · 知识库 ${d?.storage.kb_count ?? '—'} 个`, color: 'var(--c-kb)' },
    { key: 'audit', label: '审计（24h）', value: d?.audit_24h ?? '—', sub: '写操作全量留痕', color: 'var(--c-profiles)' },
  ]
})

const kindBars = computed(() => {
  const byKind = data.value?.resources.by_kind || {}
  const entries = Object.entries(byKind)
  const max = Math.max(1, ...entries.map(([, v]) => v))
  return entries
    .sort((a, b) => b[1] - a[1])
    .map(([kind, value]) => ({
      kind,
      label: KIND_META[kind]?.label || kind,
      color: KIND_META[kind]?.color || 'var(--accent-ai)',
      value,
      width: Math.max(6, Math.round((value / max) * 100)),
    }))
})

const taskBars = computed(() => {
  const byStatus = data.value?.tasks.by_status || {}
  const entries = Object.entries(byStatus)
  const max = Math.max(1, ...entries.map(([, v]) => v))
  return entries
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => ({
      key,
      label: STATUS_META[key]?.label || key,
      color: STATUS_META[key]?.color || 'var(--accent-ai)',
      value,
      width: Math.max(6, Math.round((value / max) * 100)),
    }))
})

const topActions = computed(() =>
  Object.entries(data.value?.top_actions || {})
    .map(([action, count]) => ({ action, count }))
    .sort((a, b) => b.count - a.count),
)

const recent = computed(() => data.value?.recent_audit || [])

function fmtTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await adminConsole.overview()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载概览失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.ao-page { display: flex; flex-direction: column; gap: 16px; }
.ao-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; }
.eyebrow { font-size: 12px; letter-spacing: .12em; color: var(--text-tertiary); text-transform: uppercase; }
.ao-head h1 { margin: 4px 0; font-size: 22px; }
.ao-head p { margin: 0; color: var(--text-secondary); font-size: 13.5px; }
.ao-head-actions { display: flex; gap: 8px; }

.ao-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); gap: 10px; }
.ao-card {
  border: 1px solid var(--border-subtle); border-radius: 14px; background: var(--bg-card);
  padding: 12px 14px; display: flex; flex-direction: column; gap: 4px;
  border-top: 3px solid var(--c);
}
.ao-card-top { display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: var(--text-tertiary); }
.ao-card b { font-size: 26px; line-height: 1.1; font-variant-numeric: tabular-nums; }
.ao-card small { font-size: 11.5px; color: var(--text-tertiary); }
.ao-hint { font-size: 10.5px; }

.ao-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.ao-panel { border: 1px solid var(--border-subtle); border-radius: 14px; background: var(--bg-card); padding: 14px 16px; }
.ao-panel-wide { grid-column: 1 / -1; }
.ao-panel-head { display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.ao-panel-head h2 { margin: 0; font-size: 15px; }
.ao-panel-head span { font-size: 11.5px; color: var(--text-tertiary); }
.ao-more { font-size: 12px; color: var(--accent-ai); }

.ao-bars { display: flex; flex-direction: column; gap: 8px; }
.ao-bar { display: grid; grid-template-columns: 70px minmax(0, 1fr) 42px; align-items: center; gap: 8px; }
.ao-bar-label { font-size: 12px; color: var(--text-secondary); }
.ao-bar-track { height: 8px; border-radius: 999px; background: var(--bg-elevated); overflow: hidden; }
.ao-bar-fill { height: 100%; border-radius: 999px; }
.ao-bar-value { font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; color: var(--text-secondary); }

.ao-rank { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.ao-rank li { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.ao-no { width: 16px; color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
.ao-rank-name { flex: 0 0 auto; }
.ao-rank code { font-size: 11px; color: var(--text-tertiary); flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ao-rank-value { font-variant-numeric: tabular-nums; color: var(--text-secondary); }

.ao-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.ao-table th { text-align: left; color: var(--text-tertiary); font-weight: 600; font-size: 11.5px; padding: 6px 8px; border-bottom: 1px solid var(--border-subtle); }
.ao-table td { padding: 7px 8px; border-bottom: 1px solid var(--border-subtle); }
.ao-table tr:last-child td { border-bottom: 0; }
.ao-table code { font-size: 11.5px; }
.ao-time { color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.ao-target, .ao-ip { color: var(--text-tertiary); font-size: 11.5px; }
.ao-foot { margin: 0; font-size: 11.5px; color: var(--text-tertiary); }

@media (max-width: 900px) { .ao-grid { grid-template-columns: 1fr; } }
</style>
