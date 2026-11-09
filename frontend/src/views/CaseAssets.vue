<template>
  <div class="asset-page">
    <header class="page-head">
      <div>
        <h1>用例资产库</h1>
        <p class="page-sub">已确认用例的跨集合快照；标签与查重只做提示，不改写任何用例。</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="load">刷新</button>
        <button class="btn btn-secondary btn-sm" @click="openSimilar()">查重</button>
        <button class="btn btn-primary btn-sm" :disabled="backfilling" @click="backfill">
          {{ backfilling ? '回填中…' : '回填历史确认用例' }}
        </button>
      </div>
    </header>

    <section class="stat-grid">
      <div class="stat-card">
        <b>{{ stats?.total ?? 0 }}</b>
        <span>资产总数</span>
      </div>
      <div class="stat-card">
        <b>{{ stats?.source_sets ?? 0 }}</b>
        <span>来源用例集</span>
      </div>
      <div class="stat-card">
        <b>{{ stats?.modules.length ?? 0 }}</b>
        <span>覆盖模块</span>
      </div>
      <div class="stat-card">
        <b>{{ stats?.tags.length ?? 0 }}</b>
        <span>标签种类</span>
      </div>
    </section>

    <section class="panel">
      <div class="filter-row">
        <n-input
          v-model:value="filters.q"
          placeholder="搜索名称、功能点、步骤或预期"
          clearable
          class="filter-search"
          @keyup.enter="applyFilters"
        />
        <n-select v-model:value="filters.module" :options="moduleOptions" placeholder="模块" clearable filterable class="filter-select" />
        <n-select v-model:value="filters.strategy" :options="strategyOptions" placeholder="策略" clearable class="filter-select" />
        <n-select v-model:value="filters.priority" :options="priorityOptions" placeholder="优先级" clearable class="filter-select" />
        <n-input v-model:value="filters.tag" placeholder="标签（精确）" clearable class="filter-tag" @keyup.enter="applyFilters" />
        <button class="btn btn-primary btn-sm" :disabled="loading" @click="applyFilters">筛选</button>
        <button class="btn btn-secondary btn-sm" @click="resetFilters">重置</button>
      </div>

      <div v-if="loading" class="asset-state">正在读取资产…</div>
      <div v-else-if="error" class="asset-state">
        <p>{{ error }}</p>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>
      <div v-else-if="!assets.length" class="asset-state">
        没有匹配的用例资产。确认用例集入库后会自动生成资产，也可以先执行“回填历史确认用例”。
      </div>

      <template v-else>
        <table class="ds-table asset-table">
          <thead>
            <tr>
              <th>用例</th>
              <th>模块</th>
              <th>策略</th>
              <th>优先级</th>
              <th>标签</th>
              <th>来源用例集</th>
              <th>更新时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="asset in assets"
              :key="asset.id"
              tabindex="0"
              class="asset-row"
              @click="openDetail(asset)"
              @keydown.enter="openDetail(asset)"
            >
              <td>
                <div class="asset-name">{{ asset.name }}</div>
                <div v-if="asset.feature_point" class="small tertiary">{{ asset.feature_point }}</div>
              </td>
              <td class="small">{{ asset.module || '—' }}</td>
              <td class="small">{{ asset.strategy || '—' }}</td>
              <td><span class="priority-pill" :data-priority="asset.priority">{{ asset.priority || '—' }}</span></td>
              <td>
                <span v-for="tag in asset.tags" :key="tag" class="tag-soft asset-tag">{{ tag }}</span>
                <span v-if="!asset.tags.length" class="small tertiary">—</span>
              </td>
              <td class="small">
                <router-link v-if="asset.source_case_set_id" :to="`/cases?set_id=${asset.source_case_set_id}`" class="link" @click.stop>
                  {{ asset.source_set_name || asset.source_case_set_id }}
                </router-link>
                <span v-else class="tertiary">来源已删除</span>
              </td>
              <td class="small mono">{{ formatTime(asset.updated_at || asset.created_at) }}</td>
            </tr>
          </tbody>
        </table>

        <div class="asset-pager">
          <span class="small tertiary">共 {{ total }} 条</span>
          <button class="btn btn-secondary btn-sm" :disabled="offset === 0 || loading" @click="changePage(-1)">上一页</button>
          <span class="small">{{ Math.floor(offset / limit) + 1 }} / {{ Math.max(1, Math.ceil(total / limit)) }}</span>
          <button class="btn btn-secondary btn-sm" :disabled="offset + limit >= total || loading" @click="changePage(1)">下一页</button>
        </div>
      </template>
    </section>

    <n-drawer v-model:show="detailOpen" width="min(760px, 96vw)">
      <n-drawer-content title="用例资产详情" closable>
        <template v-if="selected">
          <div class="asset-detail-head">
            <h3>{{ selected.name }}</h3>
            <span class="small tertiary">v{{ selected.source_version }} · {{ formatTime(selected.updated_at || selected.created_at) }}</span>
          </div>
          <div class="asset-detail-tags">
            <span class="small tertiary">标签</span>
            <n-dynamic-tags v-model:value="tagsDraft" :max="10" />
            <button class="btn btn-secondary btn-sm" :disabled="tagSaving" @click="saveTags">
              {{ tagSaving ? '保存中…' : '保存标签' }}
            </button>
          </div>

          <dl class="asset-kv">
            <dt>模块</dt><dd>{{ selected.module || '—' }}<template v-if="selected.submodule"> / {{ selected.submodule }}</template></dd>
            <dt>功能点</dt><dd>{{ selected.feature_point || '—' }}</dd>
            <dt>策略</dt><dd>{{ selected.strategy || '—' }}</dd>
            <dt>优先级</dt><dd>{{ selected.priority || '—' }}</dd>
            <dt>前置条件</dt><dd class="pre-wrap">{{ selected.precondition || '—' }}</dd>
            <dt>执行步骤</dt><dd class="pre-wrap">{{ selected.steps || '—' }}</dd>
            <dt>预期结果</dt><dd class="pre-wrap">{{ selected.expected || '—' }}</dd>
            <dt>来源</dt>
            <dd>
              <router-link v-if="selected.source_case_set_id" :to="`/cases?set_id=${selected.source_case_set_id}`" class="link" @click="detailOpen = false">
                {{ selected.source_set_name || selected.source_case_set_id }}
              </router-link>
              <span v-else class="tertiary">来源已删除</span>
            </dd>
          </dl>

          <div class="asset-detail-actions">
            <button class="btn btn-secondary btn-sm" @click="openSimilar(selected)">用这条查重</button>
            <button class="btn btn-secondary btn-sm" @click="copyAsset">复制文本</button>
          </div>
        </template>
      </n-drawer-content>
    </n-drawer>

    <n-drawer v-model:show="similarOpen" width="min(760px, 96vw)">
      <n-drawer-content title="用例查重" closable>
        <p class="small tertiary">对最近 500 条资产做文本相似度提示；只返回候选，不自动合并或修改。</p>
        <div class="similar-form">
          <n-input v-model:value="similarForm.name" placeholder="用例名称（必填）" maxlength="300" />
          <n-input v-model:value="similarForm.expected" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="预期结果（可选）" />
          <n-input v-model:value="similarForm.steps" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="执行步骤（可选）" />
          <div class="row" style="justify-content: flex-end">
            <button class="btn btn-primary btn-sm" :disabled="similarLoading || !similarForm.name.trim()" @click="runSimilar">
              {{ similarLoading ? '匹配中…' : '查找相似用例' }}
            </button>
          </div>
        </div>

        <div v-if="similarLoading" class="asset-state">正在计算相似度…</div>
        <div v-else-if="similarResults.length" class="similar-results">
          <div v-for="item in similarResults" :key="item.id" class="similar-item">
            <div class="similar-main">
              <b>{{ item.name }}</b>
              <span class="small tertiary">{{ item.module || '未分模块' }} · {{ item.priority || '—' }} · {{ item.source_set_name || '来源已删除' }}</span>
            </div>
            <span class="similar-score" :class="{ high: item.score >= 0.8 }">{{ Math.round(item.score * 100) }}%</span>
          </div>
        </div>
        <div v-else class="asset-state">输入名称后查找相似用例；没有候选时会显示空态。</div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { api } from '../api/http'
import type { CaseAsset, CaseAssetSimilarItem, CaseAssetStats } from '../api/types'

const message = useMessage()
const dialog = useDialog()

const assets = ref<CaseAsset[]>([])
const total = ref(0)
const offset = ref(0)
const limit = 20
const loading = ref(false)
const error = ref('')
const stats = ref<CaseAssetStats | null>(null)
const backfilling = ref(false)

const filters = reactive({ q: '', module: '', strategy: '', priority: '', tag: '' })

const detailOpen = ref(false)
const selected = ref<CaseAsset | null>(null)
const tagsDraft = ref<string[]>([])
const tagSaving = ref(false)

const similarOpen = ref(false)
const similarLoading = ref(false)
const similarResults = ref<CaseAssetSimilarItem[]>([])
const similarForm = reactive({ name: '', expected: '', steps: '' })

const strategyOptions = [
  { label: '正向', value: '正向' },
  { label: '反向', value: '反向' },
  { label: '边界', value: '边界' },
  { label: '等价', value: '等价' },
  { label: '状态', value: '状态' },
  { label: '场景', value: '场景' },
]
const priorityOptions = ['P0', 'P1', 'P2', 'P3'].map((value) => ({ label: value, value }))
const moduleOptions = computed(() =>
  (stats.value?.modules || []).map((item) => ({ label: `${item.module} (${item.count})`, value: item.module })),
)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await api.caseAssets.list({
      q: filters.q.trim(),
      module: filters.module,
      strategy: filters.strategy,
      priority: filters.priority,
      tag: filters.tag.trim(),
      offset: offset.value,
      limit,
    })
    assets.value = result.items
    total.value = result.total
    stats.value = await api.caseAssets.stats()
  } catch (err: any) {
    assets.value = []
    total.value = 0
    error.value = err?.message || '加载用例资产失败'
  } finally {
    loading.value = false
  }
}

function applyFilters(): void {
  offset.value = 0
  void load()
}

function resetFilters(): void {
  filters.q = ''
  filters.module = ''
  filters.strategy = ''
  filters.priority = ''
  filters.tag = ''
  offset.value = 0
  void load()
}

function changePage(direction: number): void {
  offset.value = Math.max(0, offset.value + direction * limit)
  void load()
}

function openDetail(asset: CaseAsset): void {
  selected.value = asset
  tagsDraft.value = [...asset.tags]
  detailOpen.value = true
}

async function saveTags(): Promise<void> {
  if (!selected.value || tagSaving.value) return
  tagSaving.value = true
  try {
    const updated = await api.caseAssets.updateTags(selected.value.id, tagsDraft.value)
    selected.value = updated
    const index = assets.value.findIndex((item) => item.id === updated.id)
    if (index >= 0) assets.value[index] = updated
    message.success('标签已保存')
    stats.value = await api.caseAssets.stats()
  } catch (err: any) {
    message.error(err?.message || '保存标签失败')
  } finally {
    tagSaving.value = false
  }
}

function openSimilar(asset?: CaseAsset): void {
  similarForm.name = asset?.name || ''
  similarForm.expected = asset?.expected || ''
  similarForm.steps = asset?.steps || ''
  similarResults.value = []
  similarOpen.value = true
  if (asset) void runSimilar()
}

async function runSimilar(): Promise<void> {
  if (!similarForm.name.trim() || similarLoading.value) return
  similarLoading.value = true
  try {
    similarResults.value = await api.caseAssets.similar({
      name: similarForm.name.trim(),
      expected: similarForm.expected,
      steps: similarForm.steps,
      limit: 8,
    })
  } catch (err: any) {
    message.error(err?.message || '查重失败')
  } finally {
    similarLoading.value = false
  }
}

function backfill(): void {
  dialog.warning({
    title: '回填历史确认用例',
    content: '将为最近 100 个已确认用例集补齐资产；幂等，不会覆盖已有标签。',
    positiveText: '开始回填',
    negativeText: '取消',
    onPositiveClick: async () => {
      backfilling.value = true
      try {
        const result = await api.caseAssets.backfill()
        message.success(`扫描 ${result.scanned_sets} 个用例集，新增 ${result.created_assets} 条资产`)
        await load()
      } catch (err: any) {
        message.error(err?.message || '回填失败')
      } finally {
        backfilling.value = false
      }
    },
  })
}

function copyAsset(): void {
  if (!selected.value) return
  const text = [
    `名称：${selected.value.name}`,
    `模块：${selected.value.module || '—'}`,
    `前置：${selected.value.precondition || '—'}`,
    `步骤：\n${selected.value.steps || '—'}`,
    `预期：${selected.value.expected || '—'}`,
  ].join('\n')
  navigator.clipboard?.writeText(text).then(
    () => message.success('已复制用例文本'),
    () => message.error('复制失败，请手动选择文本'),
  )
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.asset-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.page-head h1 {
  margin: 0;
  font-size: 22px;
}

.page-sub {
  margin: 6px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
}

.page-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.stat-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-main);
  padding: 12px 14px;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.stat-card b {
  font-size: 24px;
  line-height: 1;
}

.stat-card span {
  font-size: 12px;
  color: var(--text-secondary);
}

.panel {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg-main);
  padding: 14px 16px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.filter-search {
  width: 280px;
}

.filter-select {
  width: 130px;
}

.filter-tag {
  width: 150px;
}

.asset-table tbody tr {
  cursor: pointer;
}

.asset-row:hover {
  background: var(--row-hover);
}

.asset-row:focus-visible {
  outline: 2px solid var(--accent-ai);
  outline-offset: -2px;
}

.asset-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.asset-tag {
  margin: 0 4px 3px 0;
}

.priority-pill {
  display: inline-flex;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.priority-pill[data-priority='P0'] {
  color: #b91c1c;
  background: rgba(239, 68, 68, 0.1);
}

.asset-pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.asset-state {
  padding: 36px 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.asset-detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.asset-detail-head h3 {
  margin: 0;
  font-size: 17px;
}

.asset-detail-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  margin-bottom: 12px;
}

.asset-kv {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px 12px;
  margin: 0;
  font-size: 12.5px;
}

.asset-kv dt {
  color: var(--text-tertiary);
}

.asset-kv dd {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
}

.pre-wrap {
  white-space: pre-wrap;
  word-break: break-word;
}

.asset-detail-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 16px;
}

.similar-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0 14px;
}

.similar-results {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.similar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
}

.similar-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.similar-main b {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.similar-score {
  flex-shrink: 0;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text-tertiary);
}

.similar-score.high {
  color: #b91c1c;
  font-weight: 700;
}

@media (max-width: 1000px) {
  .stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .filter-search,
  .filter-select,
  .filter-tag {
    width: 100%;
  }
  .asset-kv {
    grid-template-columns: 72px minmax(0, 1fr);
  }
}
</style>
