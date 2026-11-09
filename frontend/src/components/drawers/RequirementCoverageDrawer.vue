<template>
  <n-drawer :show="show" width="min(900px, 96vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`需求覆盖 · ${setName || '当前用例集'}`" closable>
      <p class="req-intro">
        按需求编号统计用例覆盖；覆盖率只代表“有用例关联”，不代表功能已验证。基线确认后只读，改版请新建基线。
      </p>

      <div class="req-toolbar">
        <n-select
          :value="selectedId || null"
          :options="baselineOptions"
          placeholder="选择需求基线"
          clearable
          filterable
          class="req-select"
          @update:value="onSelectBaseline"
        />
        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="loadBaselines">刷新</button>
        <button class="btn btn-secondary btn-sm" @click="showCreate = !showCreate">
          {{ showCreate ? '收起新建' : '新建基线' }}
        </button>
      </div>

      <div v-if="showCreate" class="req-create">
        <div class="field">
          <label class="field-label">基线名称</label>
          <n-input v-model:value="createForm.name" placeholder="例如：支付模块 PRD V2" maxlength="120" />
        </div>
        <div class="field">
          <label class="field-label">需求原文</label>
          <n-input
            v-model:value="createForm.sourceText"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 14 }"
            placeholder="粘贴含 FR-/NFR-/BR-/SR- 编号的需求文本；平台只抽取原文条目，不扩写。"
          />
          <p class="field-hint">
            未识别到编号时不会创建空基线；请先在需求里补充编号（例如 FR-101）。
          </p>
        </div>
        <div class="req-create-actions">
          <button class="btn btn-primary btn-sm" :disabled="creating" @click="createBaseline">
            {{ creating ? '解析中…' : '解析并保存草稿' }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="req-state">正在加载需求基线…</div>
      <div v-else-if="error" class="req-state">
        <p class="req-error">{{ error }}</p>
        <button class="btn btn-secondary btn-sm" @click="reloadSelected">重试</button>
      </div>

      <template v-else-if="detail">
        <div class="req-meta">
          <span class="req-badge" :class="detail.status === 'confirmed' ? 'is-confirmed' : 'is-draft'">
            {{ detail.status === 'confirmed' ? '已确认' : '草稿' }}
          </span>
          <span class="small tertiary">{{ detail.requirement_count }} 条需求 · 版本 {{ detail.revision }}</span>
          <span v-if="detail.source_name" class="small tertiary">来源：{{ detail.source_name }}</span>
        </div>

        <div v-if="detail.status === 'draft'" class="req-draft">
          <p class="req-notice">
            草稿状态还不能计算覆盖率。请先核对下方条目；确认后基线只读，并成为当前用例集的覆盖率分母。
          </p>
          <div class="req-draft-actions">
            <button class="btn btn-primary btn-sm" :disabled="confirming" @click="confirmBaseline">
              {{ confirming ? '确认中…' : '确认基线' }}
            </button>
            <span class="small tertiary">确认后条目不可修改；改版请新建基线。</span>
          </div>
          <div class="req-table-wrap">
            <table class="req-table">
              <thead>
                <tr><th>编号</th><th>需求</th><th>优先级</th><th>模块</th><th>来源</th></tr>
              </thead>
              <tbody>
                <tr v-for="item in detail.requirements.slice(0, 50)" :key="item.id">
                  <td class="mono">{{ item.req_no }}</td>
                  <td>{{ item.title }}</td>
                  <td>{{ item.priority || '—' }}</td>
                  <td>{{ item.module || '—' }}</td>
                  <td class="small tertiary">{{ item.source_ref || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-if="detail.requirements.length > 50" class="small tertiary">
            仅展示前 50 条；确认后可在覆盖率明细中查看全部。
          </p>
        </div>

        <template v-else>
          <div v-if="coverage" class="req-coverage">
            <div class="req-cards">
              <div class="req-card">
                <span class="req-card-label">整体覆盖率</span>
                <b class="req-card-value">{{ coverage.coverage_percent }}%</b>
                <span class="small tertiary">{{ coverage.covered }} / {{ coverage.total }} 条需求</span>
              </div>
              <div class="req-card">
                <span class="req-card-label">P0 覆盖率</span>
                <b class="req-card-value" :class="{ 'is-bad': coverage.p0_percent < 100 }">{{ coverage.p0_percent }}%</b>
                <span class="small tertiary">{{ coverage.p0_covered }} / {{ coverage.p0_total }} 条 P0</span>
              </div>
              <div class="req-card">
                <span class="req-card-label">已关联用例</span>
                <b class="req-card-value">{{ coverage.linked_case_count }}</b>
                <span class="small tertiary">未关联 {{ coverage.unlinked_case_count }} 条</span>
              </div>
            </div>

            <div class="req-actions">
              <button class="btn btn-secondary btn-sm" :disabled="binding" @click="reloadCoverage">重新计算</button>
              <button class="btn btn-secondary btn-sm" :disabled="autoLoading" @click="runAutoLink">
                {{ autoLoading ? '匹配中…' : '自动关联候选' }}
              </button>
            </div>

            <div v-if="coverage.uncovered.length" class="req-section">
              <div class="req-section-title">未覆盖 {{ coverage.uncovered.length }} 条</div>
              <div class="req-table-wrap">
                <table class="req-table">
                  <thead><tr><th>编号</th><th>需求</th><th>优先级</th><th>模块</th></tr></thead>
                  <tbody>
                    <tr v-for="item in coverage.uncovered" :key="item.id">
                      <td class="mono">{{ item.req_no }}</td>
                      <td>{{ item.title }}</td>
                      <td>{{ item.priority || '—' }}</td>
                      <td>{{ item.module || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <p v-else class="req-all-covered">当前基线全部需求都已有用例关联。</p>

            <div v-if="coverage.modules.length" class="req-section">
              <div class="req-section-title">按模块</div>
              <div class="req-modules">
                <div v-for="item in coverage.modules" :key="item.module" class="req-module">
                  <div class="row-between">
                    <span class="small">{{ item.module }}</span>
                    <span class="mono small">{{ item.coverage_percent }}%</span>
                  </div>
                  <div class="req-bar"><i :style="{ width: `${item.coverage_percent}%` }" /></div>
                  <span class="small tertiary">{{ item.covered }} / {{ item.total }}</span>
                </div>
              </div>
            </div>

            <div class="req-section req-change">
              <div class="req-section-title row-between">
                <span>需求变更分析</span>
                <button v-if="!showChange" class="link-btn" @click="openChange">粘贴新版本需求</button>
                <button v-else class="link-btn" @click="showChange = false">收起</button>
              </div>

              <div v-if="showChange && !changeTarget" class="req-change-form">
                <div class="field">
                  <label class="field-label">新版本名称</label>
                  <n-input v-model:value="changeForm.name" placeholder="例如：支付模块 PRD V3" maxlength="120" />
                </div>
                <div class="field">
                  <label class="field-label">新版本需求原文</label>
                  <n-input
                    v-model:value="changeForm.sourceText"
                    type="textarea"
                    :autosize="{ minRows: 6, maxRows: 12 }"
                    placeholder="粘贴改版后的需求文本；平台只抽取 FR-/NFR-/BR-/SR- 条目并与当前版本对比。"
                  />
                </div>
                <div class="req-actions">
                  <button class="btn btn-primary btn-sm" :disabled="changeCreating" @click="createChangeVersion">
                    {{ changeCreating ? '解析中…' : '解析并分析影响' }}
                  </button>
                </div>
              </div>

              <div v-if="changeTarget" class="req-change-result">
                <div class="req-meta">
                  <span class="req-badge" :class="changeTarget.status === 'confirmed' ? 'is-confirmed' : 'is-draft'">
                    {{ changeTarget.status === 'confirmed' ? '新版本已确认' : '新版本草稿' }}
                  </span>
                  <span class="small tertiary">{{ changeTarget.name }} · {{ changeTarget.requirement_count }} 条需求</span>
                </div>

                <div v-if="changeDiff" class="req-change-counts">
                  <span>新增 <b>{{ changeDiff.added_count }}</b></span>
                  <span>删除 <b>{{ changeDiff.removed_count }}</b></span>
                  <span>修改 <b>{{ changeDiff.changed_count }}</b></span>
                  <span v-if="changeDiff.truncated" class="small tertiary">明细仅展示前 500 条</span>
                </div>

                <div v-if="changeDiff?.added.length" class="req-change-group">
                  <div class="small">新增需求</div>
                  <div v-for="item in changeDiff.added.slice(0, 20)" :key="`add-${item.id}`" class="req-change-row">
                    <b class="mono">{{ item.req_no }}</b>
                    <span>{{ item.title }}</span>
                    <span class="small tertiary">{{ item.priority || '—' }} · {{ item.module || '未分模块' }}</span>
                  </div>
                </div>
                <div v-if="changeDiff?.removed.length" class="req-change-group">
                  <div class="small">删除需求</div>
                  <div v-for="item in changeDiff.removed.slice(0, 20)" :key="`del-${item.id}`" class="req-change-row">
                    <b class="mono">{{ item.req_no }}</b>
                    <span>{{ item.title }}</span>
                  </div>
                </div>
                <div v-if="changeDiff?.changed.length" class="req-change-group">
                  <div class="small">修改需求</div>
                  <div v-for="item in changeDiff.changed.slice(0, 20)" :key="`chg-${item.id}`" class="req-change-row">
                    <b class="mono">{{ item.req_no }}</b>
                    <span>{{ item.title }}</span>
                    <span class="small tertiary">
                      <template v-for="(field, index) in item.fields" :key="field.field">
                        {{ index ? '；' : '' }}{{ field.label }}：{{ field.before || '空' }} → {{ field.after || '空' }}
                      </template>
                    </span>
                  </div>
                </div>

                <div v-if="changeImpact" class="req-change-impact">
                  <div class="small">
                    受影响用例集 <b>{{ changeImpact.affected_set_count }}</b> 个 · 用例 <b>{{ changeImpact.affected_case_count }}</b> 条
                    <span v-if="changeImpact.truncated" class="tertiary">（明细截断）</span>
                  </div>
                  <div v-if="!changeImpact.affected_case_count" class="small tertiary">
                    没有已关联用例受本次变更影响；新增需求仍需补充用例。
                  </div>
                  <div v-for="item in changeImpact.sets" :key="item.case_set_id" class="req-change-row">
                    <router-link :to="`/cases?set_id=${item.case_set_id}`" class="link">{{ item.name }}</router-link>
                    <span class="small tertiary">{{ item.status }} · {{ item.affected_cases }} 条受影响</span>
                  </div>
                  <div class="req-change-cases">
                    <div v-for="item in changeImpact.cases.slice(0, 50)" :key="`${item.case_set_id}-${item.case_item_id}-${item.req_no}`" class="req-change-row">
                      <span class="mono small">{{ item.req_no }}</span>
                      <span>{{ item.case_name }}</span>
                      <span class="small tertiary">{{ item.change_type === 'removed' ? '需求已删除' : '需求已修改' }}</span>
                    </div>
                  </div>
                </div>

                <div class="req-actions">
                  <button
                    v-if="changeTarget.status === 'draft'"
                    class="btn btn-primary btn-sm"
                    :disabled="confirming"
                    @click="confirmChangeVersion"
                  >
                    {{ confirming ? '确认中…' : '确认新版本' }}
                  </button>
                  <button class="btn btn-secondary btn-sm" @click="changeTarget = null; changeDiff = null; changeImpact = null">
                    重新分析
                  </button>
                  <span class="small tertiary">本期只展示影响，不自动修改用例；请按清单人工处理。</span>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="req-unbound">
            <p>当前用例集尚未绑定这份基线。</p>
            <button class="btn btn-primary btn-sm" :disabled="binding" @click="bindBaseline">
              {{ binding ? '绑定中…' : '绑定并计算覆盖率' }}
            </button>
          </div>

          <div v-if="autoLinks.length" class="req-section req-candidates">
            <div class="req-section-title">自动关联候选（{{ autoLinks.length }} 条，需人工确认）</div>
            <p class="small tertiary">确认后会替换这些用例现有的需求关联；未列出的用例不受影响。</p>
            <label v-for="link in autoLinks" :key="`${link.case_item_id}-${link.requirement_id}`" class="req-candidate">
              <input v-model="selectedCandidates[`${link.case_item_id}-${link.requirement_id}`]" type="checkbox" />
              <span class="req-candidate-main">
                <b>{{ link.case_name || link.case_item_id }}</b>
                <span class="small tertiary">→ {{ link.req_no }} {{ link.req_title }}</span>
              </span>
              <span class="small mono">{{ Math.round(link.confidence * 100) }}% · {{ link.reason }}</span>
            </label>
            <div class="req-actions">
              <button class="btn btn-primary btn-sm" :disabled="linking || !selectedCandidateCount" @click="applyAutoLinks">
                {{ linking ? '保存中…' : `确认关联 ${selectedCandidateCount} 条` }}
              </button>
              <button class="btn btn-secondary btn-sm" @click="autoLinks = []">取消</button>
            </div>
          </div>
        </template>
      </template>

      <div v-else class="req-empty">
        选择一份需求基线，或先新建基线。需求文本需包含 FR-/NFR-/BR-/SR- 编号。
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'

import { api } from '../../api/http'
import type {
  CaseCoverage,
  RequirementAutoLink,
  RequirementBaseline,
  RequirementBaselineDetail,
  RequirementDiff,
  RequirementImpact,
} from '../../api/types'

const props = defineProps<{
  show: boolean
  setId: string
  setName?: string
  baselineId?: string | null
}>()

const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'linked', baselineId: string): void
}>()

const message = useMessage()

const baselines = ref<RequirementBaseline[]>([])
const selectedId = ref('')
const boundId = ref('')
const detail = ref<RequirementBaselineDetail | null>(null)
const coverage = ref<CaseCoverage | null>(null)
const loading = ref(false)
const binding = ref(false)
const confirming = ref(false)
const creating = ref(false)
const autoLoading = ref(false)
const linking = ref(false)
const error = ref('')
const showCreate = ref(false)
const autoLinks = ref<RequirementAutoLink[]>([])
const selectedCandidates = reactive<Record<string, boolean>>({})

const createForm = reactive({ name: '', sourceText: '' })
// 需求改版分析：默认以当前确认基线为父版本，只读展示差异与影响。
const showChange = ref(false)
const changeForm = reactive({ name: '', sourceText: '' })
const changeCreating = ref(false)
const changeTarget = ref<RequirementBaselineDetail | null>(null)
const changeDiff = ref<RequirementDiff | null>(null)
const changeImpact = ref<RequirementImpact | null>(null)

const baselineOptions = computed(() =>
  baselines.value.map((item) => ({
    label: `${item.name} · ${item.status === 'confirmed' ? '已确认' : '草稿'} · ${item.requirement_count} 条`,
    value: item.id,
  })),
)

const selectedCandidateCount = computed(() =>
  autoLinks.value.filter((link) => selectedCandidates[`${link.case_item_id}-${link.requirement_id}`]).length,
)

function resetState(): void {
  detail.value = null
  coverage.value = null
  error.value = ''
  autoLinks.value = []
  for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
}

async function loadBaselines(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    baselines.value = await api.requirements.listBaselines()
    boundId.value = props.baselineId || ''
    if (!selectedId.value) {
      selectedId.value = boundId.value || baselines.value.find((item) => item.status === 'confirmed')?.id || ''
    }
    if (selectedId.value) await loadDetail(selectedId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载需求基线失败'
  } finally {
    loading.value = false
  }
}

async function loadDetail(baselineId: string): Promise<void> {
  if (!baselineId) {
    detail.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    detail.value = await api.requirements.getBaseline(baselineId)
    if (detail.value.status === 'confirmed' && boundId.value === baselineId) {
      await loadCoverage()
    } else {
      coverage.value = null
    }
  } catch (err) {
    detail.value = null
    error.value = err instanceof Error ? err.message : '加载需求条目失败'
  } finally {
    loading.value = false
  }
}

async function loadCoverage(): Promise<void> {
  if (!props.setId) return
  try {
    coverage.value = await api.requirements.coverage(props.setId)
  } catch (err) {
    coverage.value = null
    // 未绑定是正常流程，不作为错误横幅。
    const text = err instanceof Error ? err.message : ''
    if (!text.includes('尚未绑定')) error.value = text || '计算覆盖率失败'
  }
}

function onSelectBaseline(value: string | null): void {
  selectedId.value = value || ''
  resetState()
  if (selectedId.value) void loadDetail(selectedId.value)
}

async function reloadSelected(): Promise<void> {
  if (selectedId.value) await loadDetail(selectedId.value)
  else await loadBaselines()
}

async function reloadCoverage(): Promise<void> {
  binding.value = true
  try {
    await loadCoverage()
  } finally {
    binding.value = false
  }
}

async function createBaseline(): Promise<void> {
  if (creating.value) return
  if (!createForm.name.trim() || !createForm.sourceText.trim()) {
    message.warning('请填写基线名称与需求原文')
    return
  }
  creating.value = true
  try {
    const created = await api.requirements.createBaseline({
      name: createForm.name.trim(),
      source_text: createForm.sourceText,
      source_kind: 'text',
    })
    baselines.value.unshift(created)
    selectedId.value = created.id
    detail.value = created
    showCreate.value = false
    createForm.name = ''
    createForm.sourceText = ''
    message.success(`已解析 ${created.requirement_count} 条需求，请核对后确认`)
  } catch (err) {
    message.error(err instanceof Error ? err.message : '创建需求基线失败')
  } finally {
    creating.value = false
  }
}

async function confirmBaseline(): Promise<void> {
  if (!detail.value || confirming.value) return
  confirming.value = true
  try {
    detail.value = await api.requirements.confirmBaseline(detail.value.id)
    message.success('需求基线已确认')
    await bindBaseline()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '确认需求基线失败')
  } finally {
    confirming.value = false
  }
}

function openChange(): void {
  if (!detail.value) return
  showChange.value = true
  changeTarget.value = null
  changeDiff.value = null
  changeImpact.value = null
  changeForm.name = `${detail.value.name} V${detail.value.revision + 1}`
  changeForm.sourceText = ''
}

async function createChangeVersion(): Promise<void> {
  if (!detail.value || changeCreating.value) return
  if (!changeForm.name.trim() || !changeForm.sourceText.trim()) {
    message.warning('请填写新版本名称与需求原文')
    return
  }
  changeCreating.value = true
  try {
    const target = await api.requirements.createVersion(detail.value.id, {
      name: changeForm.name.trim(),
      source_text: changeForm.sourceText,
      source_kind: 'text',
    })
    changeTarget.value = target
    const [diff, impact] = await Promise.all([
      api.requirements.diff(target.id, detail.value.id),
      api.requirements.impact(target.id, detail.value.id),
    ])
    changeDiff.value = diff
    changeImpact.value = impact
    message.success(`已解析新版本 ${target.requirement_count} 条需求，请核对差异后确认`)
  } catch (err) {
    message.error(err instanceof Error ? err.message : '创建需求新版本失败')
  } finally {
    changeCreating.value = false
  }
}

async function confirmChangeVersion(): Promise<void> {
  if (!changeTarget.value || confirming.value) return
  confirming.value = true
  try {
    changeTarget.value = await api.requirements.confirmBaseline(changeTarget.value.id)
    await loadBaselines()
    message.success('新版本已确认；请按影响清单人工处理用例')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '确认新版本失败')
  } finally {
    confirming.value = false
  }
}

async function bindBaseline(): Promise<void> {
  if (!selectedId.value || binding.value) return
  binding.value = true
  error.value = ''
  try {
    coverage.value = await api.requirements.bind(props.setId, selectedId.value)
    boundId.value = selectedId.value
    emit('linked', selectedId.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '绑定需求基线失败'
  } finally {
    binding.value = false
  }
}

async function runAutoLink(): Promise<void> {
  if (!selectedId.value || autoLoading.value) return
  autoLoading.value = true
  try {
    const result = await api.requirements.autoLink(props.setId, selectedId.value)
    autoLinks.value = result.links
    for (const key of Object.keys(selectedCandidates)) delete selectedCandidates[key]
    for (const link of result.links) {
      selectedCandidates[`${link.case_item_id}-${link.requirement_id}`] = true
    }
    if (!result.links.length) message.info('没有达到阈值的自动关联候选，可先人工补充需求编号')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '自动关联失败')
  } finally {
    autoLoading.value = false
  }
}

async function applyAutoLinks(): Promise<void> {
  if (!selectedId.value || linking.value) return
  const grouped = new Map<string, string[]>()
  for (const link of autoLinks.value) {
    const key = `${link.case_item_id}-${link.requirement_id}`
    if (!selectedCandidates[key]) continue
    const current = grouped.get(link.case_item_id) || []
    current.push(link.requirement_id)
    grouped.set(link.case_item_id, current)
  }
  if (!grouped.size) {
    message.warning('请至少选择一条候选')
    return
  }
  linking.value = true
  try {
    await api.requirements.link(
      props.setId,
      selectedId.value,
      [...grouped.entries()].map(([case_item_id, requirement_ids]) => ({ case_item_id, requirement_ids })),
    )
    autoLinks.value = []
    await loadCoverage()
    emit('linked', selectedId.value)
    message.success('需求关联已保存')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '保存需求关联失败')
  } finally {
    linking.value = false
  }
}

watch(
  () => props.show,
  (visible) => {
    if (visible) {
      resetState()
      selectedId.value = props.baselineId || ''
      void loadBaselines()
    }
  },
)
</script>

<style scoped>
.req-intro {
  margin: 0 0 14px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.req-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.req-select {
  flex: 1;
  min-width: 220px;
}

.req-create {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
  margin-bottom: 14px;
  background: rgba(15, 23, 42, 0.02);
}

.req-create-actions {
  display: flex;
  justify-content: flex-end;
}

.req-state,
.req-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.7;
}

.req-error {
  color: #c0504d;
  margin: 0 0 10px;
}

.req-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.req-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
}

.req-badge.is-draft {
  color: #9a6a18;
  background: #fdf3df;
}

.req-badge.is-confirmed {
  color: #2f6b52;
  background: #e8f5ee;
}

.req-notice {
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  margin: 0 0 10px;
}

.req-draft {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
}

.req-draft-actions,
.req-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.req-table-wrap {
  overflow: auto;
  max-height: 420px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
}

.req-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}

.req-table th,
.req-table td {
  padding: 7px 9px;
  border-bottom: 1px solid var(--border, #e5e7eb);
  text-align: left;
  vertical-align: top;
}

.req-table th {
  position: sticky;
  top: 0;
  background: var(--bg-card, #fff);
  font-weight: 600;
  white-space: nowrap;
}

.req-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.req-card {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.req-card-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.req-card-value {
  font-size: 24px;
  line-height: 1.2;
}

.req-card-value.is-bad {
  color: #c0504d;
}

.req-section {
  margin-top: 16px;
}

.req-section-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
}

.req-all-covered {
  margin-top: 14px;
  color: #2f6b52;
  font-size: 13px;
}

.req-modules {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}

.req-module {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  padding: 8px 10px;
}

.req-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(15, 23, 42, 0.08);
  overflow: hidden;
  margin: 5px 0;
}

.req-bar i {
  display: block;
  height: 100%;
  background: #2f8f63;
}

.req-unbound {
  padding: 24px 16px;
  text-align: center;
  border: 1px dashed var(--border, #e5e7eb);
  border-radius: 10px;
  color: var(--text-secondary);
}

.req-candidate {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
}

.req-candidate-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.req-change-form {
  padding: 10px 12px;
  border: 1px dashed var(--border, #d1d5db);
  border-radius: 10px;
  margin-top: 8px;
}

.req-change-result {
  margin-top: 8px;
}

.req-change-counts {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg-elevated);
  font-size: 12px;
  margin: 8px 0;
}

.req-change-group {
  margin-top: 10px;
}

.req-change-group > .small {
  color: var(--text-tertiary);
  margin-bottom: 5px;
}

.req-change-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
  padding: 5px 2px;
  border-bottom: 1px solid var(--border-subtle, #f1f5f9);
  font-size: 12.5px;
  line-height: 1.6;
}

.req-change-impact {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
}

.req-change-cases {
  margin-top: 6px;
}

@media (max-width: 700px) {
  .req-change-counts {
    gap: 8px;
  }
}
</style>
