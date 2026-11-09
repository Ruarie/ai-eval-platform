<template>
  <n-drawer :show="show" width="min(860px, 96vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`评审工作台 · ${setName || '当前用例集'}`" closable>
      <div v-if="loading" class="rf-state">正在读取评审记录…</div>

      <div v-else-if="error" class="rf-state">
        <div class="rf-error">{{ error }}</div>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>

      <template v-else-if="workspace">
        <div class="rf-summary">
          <div class="rf-summary-main">
            <span class="rf-badge" :class="`rf-badge-${workspace.review_state}`">{{ stateLabel }}</span>
            <span class="small tertiary">
              {{ workspace.review_assignee_name ? `负责人：${workspace.review_assignee_name}` : '未指定负责人' }}
              <template v-if="workspace.active_request?.due_at"> · 截止 {{ formatTime(workspace.active_request.due_at) }}</template>
            </span>
            <span v-if="!workspace.active_request && workspace.latest_request" class="small tertiary">
              上次评审：{{ requestLabel(workspace.latest_request.status) }} · {{ formatTime(workspace.latest_request.decided_at) }}
              <template v-if="workspace.latest_request.decision_note"> · {{ workspace.latest_request.decision_note }}</template>
            </span>
          </div>
          <span class="small tertiary">{{ workspace.comments.length }} 条评论 · {{ workspace.ai_runs.length }} 次 AI 评审 · {{ workspace.versions.length }} 个版本</span>
        </div>

        <section class="rf-section">
          <div class="rf-section-head">
            <h4>人工评审</h4>
            <span v-if="workspace.active_request" class="small tertiary">
              发起于 {{ formatTime(workspace.active_request.created_at) }} · {{ workspace.active_request.created_by_name || '成员' }}
            </span>
          </div>

          <div v-if="workspace.active_request" class="rf-card">
            <p v-if="workspace.active_request.note" class="rf-note">{{ workspace.active_request.note }}</p>
            <div class="rf-field">
              <label class="rf-label">评审结论</label>
              <n-input
                v-model:value="decisionNote"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 7 }"
                placeholder="通过可留空；要求修改时必须说明原因"
              />
            </div>
            <div class="rf-actions">
              <button class="btn btn-primary btn-sm" :disabled="deciding" @click="decide('approved')">通过评审</button>
              <button class="btn btn-secondary btn-sm" :disabled="deciding" @click="decide('changes_requested')">要求修改</button>
            </div>
          </div>

          <div v-else-if="caseSetStatus === 'generated'" class="rf-card">
            <div class="rf-grid">
              <div class="rf-field">
                <label class="rf-label">负责人</label>
                <n-select
                  v-model:value="assigneeId"
                  :options="assigneeOptions"
                  placeholder="默认当前成员"
                  clearable
                />
              </div>
              <div class="rf-field">
                <label class="rf-label">截止时间（可选）</label>
                <input v-model="dueAt" class="rf-native-input" type="datetime-local" aria-label="评审截止时间" />
              </div>
            </div>
            <div class="rf-field">
              <label class="rf-label">评审说明</label>
              <n-input
                v-model:value="requestNote"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="例如：请重点检查边界与异常路径"
              />
            </div>
            <div class="rf-actions">
              <button class="btn btn-primary btn-sm" :disabled="starting" @click="startReview">
                {{ starting ? '发起中…' : '发起评审' }}
              </button>
            </div>
          </div>

          <p v-else class="small tertiary">当前用例集不是草稿，不能发起新的评审；历史记录仍可查看。</p>
        </section>

        <section class="rf-section">
          <div class="rf-section-head"><h4>评论</h4></div>
          <div class="rf-comment-form">
            <n-select
              v-model:value="commentCaseId"
              :options="caseOptions"
              placeholder="整体评论（可选关联用例）"
              clearable
              filterable
            />
            <n-input
              v-model:value="commentBody"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 5 }"
              placeholder="写下具体意见；关联用例后会在该用例下展示"
            />
            <div class="rf-actions">
              <button class="btn btn-secondary btn-sm" :disabled="commenting || !commentBody.trim()" @click="addComment">
                {{ commenting ? '提交中…' : '添加评论' }}
              </button>
            </div>
          </div>

          <div v-if="!workspace.comments.length" class="rf-empty">还没有评论。评审意见会按时间倒序展示。</div>
          <div v-for="comment in workspace.comments" :key="comment.id" class="rf-comment">
            <div class="rf-comment-head">
              <b>{{ comment.author_name || '成员' }}</b>
              <span class="small tertiary">{{ formatTime(comment.created_at) }}</span>
              <span v-if="comment.case_item_id" class="rf-chip">{{ caseName(comment.case_item_id) }}</span>
            </div>
            <p class="rf-comment-body">{{ comment.body }}</p>
          </div>
        </section>

        <section class="rf-section">
          <div class="rf-section-head">
            <h4>AI 评审历史</h4>
            <span class="small tertiary">每次评审单独保留，不覆盖旧结果</span>
          </div>
          <div v-if="!workspace.ai_runs.length" class="rf-empty">还没有 AI 评审记录，可在用例页点击「AI 评审」。</div>
          <div v-for="run in workspace.ai_runs" :key="run.id" class="rf-run">
            <div class="rf-run-head">
              <span class="rf-score" :class="run.score >= 80 ? 'good' : run.score >= 60 ? 'warn' : 'bad'">{{ run.score }}</span>
              <span class="small">{{ verdictLabel(run.verdict) }}</span>
              <span class="small tertiary">{{ formatTime(run.created_at) }} · {{ run.case_count }} 条用例</span>
              <span v-if="run.issues.length" class="rf-chip">{{ run.issues.length }} 个问题</span>
            </div>
            <p v-if="run.summary" class="small tertiary rf-run-summary">{{ run.summary }}</p>
            <details v-if="run.issues.length" class="rf-details">
              <summary>查看问题清单</summary>
              <ul>
                <li v-for="(issue, index) in run.issues" :key="index">
                  <b>{{ issue.case || '整体' }}</b>：{{ issue.detail }}<template v-if="issue.fix">（建议：{{ issue.fix }}）</template>
                </li>
              </ul>
            </details>
          </div>
        </section>

        <section class="rf-section">
          <div class="rf-section-head">
            <h4>版本历史</h4>
            <span class="small tertiary">确认入库与评审通过会自动生成版本</span>
          </div>
          <div v-if="caseSetStatus === 'generated'" class="rf-version-create">
            <n-input v-model:value="versionReason" placeholder="本次存版说明（可选）" maxlength="200" />
            <button class="btn btn-secondary btn-sm" :disabled="versioning" @click="createVersion">
              {{ versioning ? '存版中…' : '创建版本' }}
            </button>
          </div>
          <p v-else class="small tertiary">已确认/已废弃用例集不再手动存版；确认入库时已自动生成版本。</p>

          <div v-if="!workspace.versions.length" class="rf-empty">还没有版本快照。</div>
          <div v-for="version in workspace.versions" :key="version.id" class="rf-version">
            <div class="rf-version-main">
              <b>v{{ version.version }}</b>
              <span class="small">{{ version.reason || '未填写说明' }}</span>
              <span class="small tertiary">{{ version.case_count }} 条 · {{ formatTime(version.created_at) }} · {{ version.created_by_name || '成员' }}</span>
            </div>
            <div class="rf-version-actions">
              <button class="link-btn" @click="showDiff(version.version)">对比上一版</button>
              <button class="link-btn" @click="restore(version.version)">回滚为新草稿</button>
            </div>
          </div>

          <div v-if="diff" class="rf-diff">
            <div class="rf-diff-head">
              <b>v{{ diff.base_version }} → v{{ diff.target_version }}</b>
              <span class="small tertiary">新增 {{ diff.added_count }} · 删除 {{ diff.removed_count }} · 修改 {{ diff.changed_count }}</span>
              <button class="link-btn" @click="diff = null">关闭</button>
            </div>
            <p v-if="diff.truncated" class="small tertiary">明细超过 500 条，仅展示前 500 条。</p>
            <div v-if="diff.added.length" class="rf-diff-group">
              <div class="small">新增</div>
              <div v-for="item in diff.added" :key="`a-${item.id}`" class="rf-diff-row">+ {{ item.name }}</div>
            </div>
            <div v-if="diff.removed.length" class="rf-diff-group">
              <div class="small">删除</div>
              <div v-for="item in diff.removed" :key="`r-${item.id}`" class="rf-diff-row">- {{ item.name }}</div>
            </div>
            <div v-if="diff.changed.length" class="rf-diff-group">
              <div class="small">字段修改</div>
              <div v-for="item in diff.changed" :key="`c-${item.id}`" class="rf-diff-row">
                <b>{{ item.name }}</b>
                <span v-for="field in item.fields" :key="field.field" class="rf-diff-field">
                  {{ field.label }}：{{ displayValue(field.before) }} → {{ displayValue(field.after) }}
                </span>
              </div>
            </div>
          </div>
        </section>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { api } from '../../api/http'
import type { CaseReviewWorkspace, CaseVersionDiff } from '../../api/types'

const props = defineProps<{
  show: boolean
  setId: string
  setName?: string
  caseSetStatus?: string
  // 只用 id/name/module 做评论关联展示，避免绑定页面完整的可编辑行类型。
  cases?: Array<{ id: string; name: string; module?: string }>
}>()

const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
  (event: 'restored', caseSetId: string): void
}>()

const message = useMessage()
const dialog = useDialog()

const workspace = ref<CaseReviewWorkspace | null>(null)
const loading = ref(false)
const error = ref('')
const members = ref<Array<{ label: string; value: string }>>([])
const assigneeId = ref<string | null>(null)
const dueAt = ref('')
const requestNote = ref('')
const decisionNote = ref('')
const commentBody = ref('')
const commentCaseId = ref<string | null>(null)
const versionReason = ref('')
const diff = ref<CaseVersionDiff | null>(null)
const starting = ref(false)
const deciding = ref(false)
const commenting = ref(false)
const versioning = ref(false)

const STATE_LABELS: Record<string, string> = {
  draft: '未评审',
  reviewing: '评审中',
  approved: '已通过',
  changes_requested: '待修改',
}
const VERDICT_LABELS: Record<string, string> = {
  pass: '通过',
  needs_fix: '待修改',
  reject: '不通过',
}

const stateLabel = computed(() => STATE_LABELS[workspace.value?.review_state || 'draft'] || '未评审')
const assigneeOptions = computed(() => members.value)
const caseOptions = computed(() =>
  (props.cases || []).map((item) => ({
    label: `${item.module ? `[${item.module}] ` : ''}${item.name}`,
    value: item.id,
  })),
)

async function load(): Promise<void> {
  if (!props.setId) return
  loading.value = true
  error.value = ''
  try {
    workspace.value = await api.caseReviews.get(props.setId)
    diff.value = null
    decisionNote.value = ''
    commentBody.value = ''
    commentCaseId.value = null
    versionReason.value = ''
    if (!members.value.length) {
      try {
        const users = await api.users.list()
        members.value = users
          .filter((user) => !user.disabled)
          .map((user) => ({ label: user.username, value: user.id }))
      } catch {
        members.value = []
      }
    }
  } catch (err: any) {
    workspace.value = null
    error.value = err?.message || '读取评审记录失败'
  } finally {
    loading.value = false
  }
}

async function startReview(): Promise<void> {
  if (!props.setId) return
  starting.value = true
  try {
    workspace.value = await api.caseReviews.createRequest(props.setId, {
      assignee_id: assigneeId.value || undefined,
      due_at: dueAt.value ? new Date(dueAt.value).toISOString() : undefined,
      note: requestNote.value.trim(),
    })
    requestNote.value = ''
    dueAt.value = ''
    message.success('评审已发起')
  } catch (err: any) {
    message.error(err?.message || '发起评审失败')
  } finally {
    starting.value = false
  }
}

async function decide(decision: 'approved' | 'changes_requested'): Promise<void> {
  const request = workspace.value?.active_request
  if (!props.setId || !request) return
  if (decision === 'changes_requested' && !decisionNote.value.trim()) {
    message.warning('要求修改时必须填写原因')
    return
  }
  deciding.value = true
  try {
    workspace.value = await api.caseReviews.decide(props.setId, request.id, {
      decision,
      note: decisionNote.value.trim(),
    })
    decisionNote.value = ''
    message.success(decision === 'approved' ? '评审已通过' : '已要求修改')
  } catch (err: any) {
    message.error(err?.message || '提交评审结论失败')
  } finally {
    deciding.value = false
  }
}

async function addComment(): Promise<void> {
  if (!props.setId || !commentBody.value.trim()) return
  commenting.value = true
  try {
    workspace.value = await api.caseReviews.addComment(props.setId, {
      body: commentBody.value.trim(),
      case_item_id: commentCaseId.value || undefined,
    })
    commentBody.value = ''
    commentCaseId.value = null
    message.success('评论已添加')
  } catch (err: any) {
    message.error(err?.message || '添加评论失败')
  } finally {
    commenting.value = false
  }
}

async function createVersion(): Promise<void> {
  if (!props.setId) return
  if (props.caseSetStatus !== 'generated') {
    message.warning('只有草稿用例集可以手动存版')
    return
  }
  versioning.value = true
  try {
    await api.caseReviews.createVersion(props.setId, versionReason.value.trim())
    versionReason.value = ''
    await load()
    message.success('版本已创建')
  } catch (err: any) {
    message.error(err?.message || '创建版本失败')
  } finally {
    versioning.value = false
  }
}

async function showDiff(version: number): Promise<void> {
  if (!props.setId) return
  try {
    diff.value = await api.caseReviews.diff(props.setId, version)
  } catch (err: any) {
    message.error(err?.message || '读取版本差异失败')
  }
}

function restore(version: number): void {
  if (!props.setId) return
  dialog.warning({
    title: `回滚到 v${version}`,
    content: '将基于该版本创建一个新草稿，不会修改当前用例集或历史版本。',
    positiveText: '创建草稿',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const result = await api.caseReviews.restore(props.setId, version)
        message.success('已创建回滚草稿')
        emit('restored', result.case_set_id)
        emit('update:show', false)
      } catch (err: any) {
        message.error(err?.message || '回滚失败')
      }
    },
  })
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function verdictLabel(value: string): string {
  return VERDICT_LABELS[value] || value || '—'
}

function requestLabel(status: string): string {
  const labels: Record<string, string> = {
    pending: '待评审',
    approved: '已通过',
    changes_requested: '要求修改',
    cancelled: '已取消',
  }
  return labels[status] || status || '—'
}

function caseName(caseId: string): string {
  const item = (props.cases || []).find((entry) => entry.id === caseId)
  return item ? item.name : '已删除用例'
}

function displayValue(value: unknown): string {
  if (value == null || value === '') return '空'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

watch(
  () => props.show,
  (visible) => {
    if (visible) void load()
  },
)

watch(
  () => props.setId,
  () => {
    if (props.show) void load()
  },
)
</script>

<style scoped>
.rf-state {
  padding: 48px 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.rf-error {
  margin-bottom: 10px;
  color: var(--danger, #b91c1c);
}

.rf-summary {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 12px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  background: var(--bg-elevated);
  margin-bottom: 14px;
}

.rf-summary-main {
  display: flex;
  align-items: center;
  gap: 9px;
  flex-wrap: wrap;
}

.rf-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 2px 9px;
  font-size: 11px;
  font-weight: 600;
}

.rf-badge-draft { color: var(--text-secondary); background: rgba(107, 114, 128, 0.12); }
.rf-badge-reviewing { color: #b45309; background: rgba(245, 158, 11, 0.14); }
.rf-badge-approved { color: #15803d; background: rgba(34, 197, 94, 0.14); }
.rf-badge-changes_requested { color: #b91c1c; background: rgba(239, 68, 68, 0.12); }

.rf-section {
  border-top: 1px solid var(--border, #e5e7eb);
  padding: 14px 0;
}

.rf-section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.rf-section-head h4 {
  margin: 0;
  font-size: 14px;
}

.rf-card {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 12px;
  background: var(--bg-main);
}

.rf-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.rf-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 10px;
}

.rf-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.rf-native-input {
  height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border, #d1d5db);
  border-radius: 8px;
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 13px;
}

.rf-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 6px;
}

.rf-note {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.04);
  color: var(--text-secondary);
  font-size: 12.5px;
  line-height: 1.6;
}

.rf-empty {
  padding: 14px 4px;
  color: var(--text-tertiary);
  font-size: 12.5px;
}

.rf-comment-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.rf-comment {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.rf-comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 5px;
}

.rf-comment-body {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.rf-chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
  padding: 1px 7px;
  font-size: 10px;
}

.rf-run {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.rf-run-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.rf-score {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
}

.rf-score.good { color: #2f8f63; }
.rf-score.warn { color: #c08a2e; }
.rf-score.bad { color: #c0504d; }

.rf-run-summary {
  margin: 6px 0 0;
  line-height: 1.6;
}

.rf-details {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.rf-details ul {
  margin: 6px 0 0;
  padding-left: 18px;
  line-height: 1.7;
}

.rf-version-create {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}

.rf-version {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 8px;
  margin-bottom: 6px;
}

.rf-version-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.rf-version-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.rf-diff {
  margin-top: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  background: var(--bg-elevated);
}

.rf-diff-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.rf-diff-group {
  margin-top: 8px;
}

.rf-diff-row {
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.rf-diff-field {
  display: inline-block;
  margin-left: 10px;
  color: var(--text-tertiary);
}

@media (max-width: 700px) {
  .rf-grid {
    grid-template-columns: 1fr;
  }

  .rf-version {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
