<template>
  <div class="workbench-page">
    <header class="workbench-intro">
      <p>管理能力中心资源的可见性与下架，变更会写入审计日志。</p>
      <n-button :disabled="loading" @click="reload">刷新</n-button>
    </header>

    <section class="workbench-filters" aria-label="资源治理筛选">
      <n-input v-model:value="keyword" class="workbench-filter workbench-filter-wide" clearable placeholder="搜索名称或描述" :input-props="{ 'aria-label': '搜索名称或描述' }" @keyup.enter="reload" />
      <n-select v-model:value="kind" class="workbench-filter" :options="kindOptions" clearable placeholder="全部类型" :input-props="{ 'aria-label': '筛选资源类型' }" @update:value="reload" />
      <n-select v-model:value="visibility" class="workbench-filter" :options="visibilityOptions" clearable placeholder="全部可见性" :input-props="{ 'aria-label': '筛选可见性' }" @update:value="reload" />
      <n-button :loading="loading" @click="reload">查询</n-button>
      <span class="ar-total workbench-count">共 {{ total }} 个</span>
    </section>

    <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

    <n-spin :show="loading">
      <div v-if="rows.length" class="workbench-table-panel">
        <div class="workbench-table-scroll" role="region" aria-label="资源治理表格" tabindex="0">
          <table class="ar-table ds-table">
            <thead>
              <tr><th>名称</th><th>类型</th><th>可见性</th><th>创建人</th><th>使用</th><th>更新时间</th><th>操作</th></tr>
            </thead>
            <tbody>
              <tr v-for="item in rows" :key="item.id">
                <td>
                  <div class="ar-name">
                    <b>{{ item.name }}</b>
                    <small>{{ item.summary || '（无描述）' }}</small>
                  </div>
                </td>
                <td><span class="ar-tag" :style="kindStyle(item.kind)">{{ kindLabel(item.kind) }}</span></td>
                <td>
                  <span class="ar-vis" :class="item.visibility">{{ item.visibility === 'team' ? '团队' : '私有' }}</span>
                </td>
                <td class="ar-owner">{{ item.owner_name || '—' }}</td>
                <td class="ar-num">{{ item.usage_count }}</td>
                <td class="ar-time">{{ fmt(item.updated_at) }}</td>
                <td>
                  <div class="ar-actions">
                    <n-button size="tiny" :disabled="busy === item.id" @click="toggleVisibility(item)">
                      {{ item.visibility === 'team' ? '转为私有' : '设为团队' }}
                    </n-button>
                    <n-button size="tiny" quaternary type="error" :disabled="busy === item.id" @click="remove(item)">下架删除</n-button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="workbench-table-footer">
          <n-button v-if="hasMore" size="small" :loading="loading" @click="loadMore">加载更多</n-button>
          <span v-else>已到末尾</span>
        </div>
      </div>
      <n-empty v-else :description="error ? '暂时无法读取资源' : '没有匹配的资源'" />
    </n-spin>

    <p class="ar-note">
      说明：删除为硬删除，会同时清掉该资源的使用记录；由它克隆出的副本保留，仅断开来源血缘。
    </p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'
import { resources, type ResourceItem, type ResourceKind } from '../api/resources'

const message = useMessage()
const rows = ref<ResourceItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const busy = ref('')
const keyword = ref('')
const kind = ref<ResourceKind | null>(null)
const visibility = ref<'team' | 'private' | null>(null)
const pageSize = 50

const KIND_META: Record<string, { label: string; t: string; c: string }> = {
  agent: { label: 'Agent', t: 'var(--t-agent)', c: 'var(--c-agent)' },
  skill: { label: 'Skill', t: 'var(--t-datasets)', c: 'var(--c-datasets)' },
  script: { label: 'Script', t: 'var(--t-reports)', c: 'var(--c-reports)' },
  rule: { label: 'Rule', t: 'var(--t-profiles)', c: 'var(--c-profiles)' },
  rag: { label: 'RAG', t: 'var(--t-kb)', c: 'var(--c-kb)' },
}

const kindOptions = Object.entries(KIND_META).map(([value, meta]) => ({ label: meta.label, value }))
const visibilityOptions = [
  { label: '团队共享', value: 'team' },
  { label: '仅本人', value: 'private' },
]

const kindLabel = (value: string): string => KIND_META[value]?.label || value
const kindStyle = (value: string) => ({ background: KIND_META[value]?.t, color: KIND_META[value]?.c })

const hasMore = computed(() => rows.value.length < total.value)

function fmt(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function loadPage(reset: boolean): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const page = await resources.list({
      kind: kind.value || '',
      visibility: visibility.value || '',
      q: keyword.value.trim(),
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

async function toggleVisibility(item: ResourceItem): Promise<void> {
  busy.value = item.id
  try {
    const next = item.visibility === 'team' ? 'private' : 'team'
    const updated = await resources.update(item.id, { visibility: next })
    if (visibility.value && updated.visibility !== visibility.value) {
      // 当前按可见性筛选时，切换后不再命中筛选条件，直接移出当前列表。
      rows.value = rows.value.filter((row) => row.id !== item.id)
      total.value = Math.max(0, total.value - 1)
    } else {
      item.visibility = updated.visibility
    }
    message.success(next === 'team' ? '已设为团队可见' : '已转为私有')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '操作失败')
  } finally {
    busy.value = ''
  }
}

async function remove(item: ResourceItem): Promise<void> {
  if (!window.confirm(`下架并删除「${item.name}」？该操作不可恢复。`)) return
  busy.value = item.id
  try {
    await resources.remove(item.id)
    rows.value = rows.value.filter((row) => row.id !== item.id)
    total.value = Math.max(0, total.value - 1)
    message.success('已删除')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '删除失败')
  } finally {
    busy.value = ''
  }
}

onMounted(() => {
  void loadPage(true)
})
</script>

<style scoped>
.ar-table { min-width: 47rem; font-size: 13px; }
.ar-name { display: grid; gap: 2px; min-width: 11rem; max-width: 21rem; overflow-wrap: anywhere; }
.ar-name b { font-weight: 600; }
.ar-name small { font-size: 12px; color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ar-tag { font-size: 11px; padding: 2px 7px; border-radius: 6px; }
.ar-vis { font-size: 11px; padding: 2px 7px; border-radius: 6px; border: 1px solid var(--border-subtle); color: var(--text-secondary); }
.ar-vis.private { border-style: dashed; }
.ar-owner { color: var(--text-secondary); overflow-wrap: anywhere; }
.ar-num, .ar-time { color: var(--text-secondary); font-variant-numeric: tabular-nums; white-space: nowrap; }
.ar-actions { display: flex; gap: 6px; white-space: nowrap; }
.ar-note { font-size: 12px; color: var(--text-secondary); }
</style>
