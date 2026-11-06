<template>
  <n-drawer :show="show" width="min(760px, 94vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`AI 评审 · ${setName || '当前用例集'}`" closable>
      <div v-if="loading" class="review-state">
        正在评审 {{ caseCount || '全部' }} 条用例（覆盖 / 可执行性 / 重复 / 分布），通常需要 20–60 秒…
      </div>

      <div v-else-if="error" class="review-state">
        <div class="review-error">{{ error }}</div>
        <button class="btn btn-secondary btn-sm" @click="run">重试</button>
      </div>

      <template v-else-if="review">
        <div class="review-head">
          <div class="score-block">
            <span class="score" :class="`score-${review.verdict}`">{{ review.score }}</span>
            <span class="verdict">{{ verdictLabel }}</span>
          </div>
          <div class="head-meta">
            <span class="small tertiary">
              评审 {{ review.case_count }} 条用例 · {{ reviewedAt }}
              <template v-if="review.source_truncated">（需求超过 2 万字，仅评审前 2 万字）</template>
            </span>
            <button class="btn btn-secondary btn-sm" @click="run">重新评审</button>
          </div>
        </div>

        <p v-if="review.summary" class="review-summary">{{ review.summary }}</p>

        <div class="dimensions">
          <div v-for="item in dimensions" :key="item.key" class="dimension">
            <div class="dim-head">
              <span class="small">{{ item.label }}</span>
              <span class="mono small" :class="item.tone">{{ item.score }}</span>
            </div>
            <div class="dim-bar"><i :style="{ width: `${item.score}%` }" :class="item.tone"></i></div>
            <p v-if="item.note" class="small tertiary dim-note">{{ item.note }}</p>
          </div>
        </div>

        <div v-if="review.issues.length" class="issue-block">
          <div class="issue-title">发现 {{ review.issues.length }} 个问题</div>
          <div v-for="(issue, index) in review.issues" :key="index" class="issue">
            <div class="issue-head">
              <span class="chip">{{ typeLabel(issue.type) }}</span>
              <span class="issue-case">{{ issue.case || '（缺失）' }}</span>
            </div>
            <p class="issue-detail">{{ issue.detail }}</p>
            <p v-if="issue.fix" class="issue-fix"><b>建议：</b>{{ issue.fix }}</p>
          </div>
        </div>
        <div v-else class="issue-block">
          <div class="issue-title good">未发现明显问题</div>
        </div>
      </template>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '../../api/http'

const props = defineProps<{
  show: boolean
  setId: string
  setName?: string
  caseCount?: number
}>()

const emit = defineEmits<{ (event: 'update:show', value: boolean): void }>()

type Review = Awaited<ReturnType<typeof api.cases.reviewSet>>

const DIMENSION_LABELS: Record<string, string> = {
  coverage: '覆盖度',
  executability: '可执行性',
  dedup: '去重与冗余',
  distribution: '策略分布',
}
const TYPE_LABELS: Record<string, string> = {
  coverage: '覆盖',
  executability: '可执行性',
  dedup: '重复',
  distribution: '分布',
}
const VERDICT_LABELS: Record<string, string> = {
  pass: '通过',
  needs_fix: '待修改',
  reject: '不通过',
}

const review = ref<Review | null>(null)
const loading = ref(false)
const error = ref('')

async function run(): Promise<void> {
  if (!props.setId) return
  loading.value = true
  error.value = ''
  try {
    review.value = await api.cases.reviewSet(props.setId)
  } catch (err) {
    review.value = null
    error.value = err instanceof Error ? err.message : '评审失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

watch(
  () => props.show,
  (visible) => {
    if (visible) void run()
  },
)

const verdictLabel = computed(() => VERDICT_LABELS[review.value?.verdict || ''] || '—')

const dimensions = computed(() => {
  const source = review.value?.dimensions || {}
  return Object.keys(DIMENSION_LABELS).map((key) => {
    const score = Math.max(0, Math.min(100, source[key]?.score ?? 0))
    return {
      key,
      label: DIMENSION_LABELS[key],
      score,
      note: source[key]?.note || '',
      tone: score >= 80 ? 'good' : score >= 60 ? 'warn' : 'bad',
    }
  })
})

const reviewedAt = computed(() => {
  const value = review.value?.reviewed_at
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
})

function typeLabel(type: string): string {
  return TYPE_LABELS[type] || type || '其它'
}
</script>

<style scoped>
.review-state {
  padding: 48px 20px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
  line-height: 1.7;
}

.review-error {
  color: var(--danger, #d9534f);
  margin-bottom: 10px;
}

.review-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}

.score-block {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.score {
  font-size: 34px;
  font-weight: 700;
  line-height: 1;
}

.score-pass { color: #2f8f63; }
.score-needs_fix { color: #c08a2e; }
.score-reject { color: #c0504d; }

.verdict {
  font-size: 13px;
  color: var(--text-secondary);
}

.head-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}

.review-summary {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  background: rgba(15, 23, 42, 0.04);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 14px;
}

.dimensions {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.dimension {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
}

.dim-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.dim-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.dim-bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
}

.dim-bar i.good { background: #2f8f63; }
.dim-bar i.warn { background: #c08a2e; }
.dim-bar i.bad { background: #c0504d; }

.dim-note {
  margin: 6px 0 0;
  line-height: 1.6;
}

.issue-block {
  border-top: 1px solid var(--border, #e5e7eb);
  padding-top: 12px;
}

.issue-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
}

.issue-title.good {
  color: #2f8f63;
}

.issue {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 10px;
}

.issue-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.issue-case {
  font-size: 13px;
  font-weight: 500;
  word-break: break-all;
}

.issue-detail {
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-secondary);
  margin: 0 0 4px;
}

.issue-fix {
  font-size: 12.5px;
  line-height: 1.65;
  color: #2f6b52;
  margin: 0;
}
</style>
