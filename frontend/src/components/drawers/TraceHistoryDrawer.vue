<template>
  <n-drawer :show="show" width="min(1000px, 97vw)" @update:show="emit('update:show', $event)">
    <n-drawer-content :title="`历史轨迹 · ${sessionName || '当前会话'}`" closable>
      <p class="trace-intro">
        轨迹来自已持久化事件，只展示模型/工具/审批等元数据，不返回消息正文、工具结果或提示词。
      </p>

      <div v-if="loading" class="trace-state">正在读取历史回合…</div>
      <div v-else-if="error" class="trace-state">
        <p>{{ error }}</p>
        <button class="btn btn-secondary btn-sm" @click="load">重试</button>
      </div>
      <div v-else-if="!turns.length" class="trace-state">当前会话还没有可展示的历史回合。</div>

      <div v-else class="trace-grid">
        <aside class="trace-turns" aria-label="历史回合">
          <button
            v-for="item in turns"
            :key="item.turn"
            class="trace-turn"
            :class="{ active: activeTurn === item.turn }"
            @click="selectTurn(item.turn)"
          >
            <div class="trace-turn-head">
              <b>第 {{ item.turn }} 轮</b>
              <span class="trace-status" :data-status="item.status">{{ statusLabel(item.status) }}</span>
            </div>
            <div class="small tertiary">{{ formatTime(item.started_at) }} · {{ item.event_count }} 事件</div>
            <div class="small tertiary">
              工具 {{ item.tool_calls }} · 模型 {{ item.model_attempts }} · {{ item.total_tokens }} tokens
            </div>
          </button>
        </aside>

        <section class="trace-events">
          <div v-if="detailLoading" class="trace-state">正在读取该回合事件…</div>
          <div v-else-if="detailError" class="trace-state">
            <p>{{ detailError }}</p>
            <button class="btn btn-secondary btn-sm" @click="selectTurn(activeTurn)">重试</button>
          </div>
          <template v-else-if="detail">
            <div class="trace-summary">
              <b>第 {{ detail.turn }} 轮</b>
              <span class="trace-status" :data-status="detail.summary.status">{{ statusLabel(detail.summary.status) }}</span>
              <span class="small tertiary">{{ formatTime(detail.summary.started_at) }} → {{ formatTime(detail.summary.finished_at) }}</span>
              <span class="small tertiary">
                {{ detail.summary.event_count }} 事件 · {{ detail.summary.tool_calls }} 次工具 · {{ detail.summary.total_tokens }} tokens
              </span>
            </div>

            <div v-if="!detail.events.length" class="trace-state">该回合没有可展示的轨迹事件。</div>
            <div v-else class="trace-event-list">
              <div v-for="event in detail.events" :key="event.seq" class="trace-event" :data-type="event.type">
                <span class="trace-event-time">{{ formatTime(event.ts) }}</span>
                <span class="trace-event-type">{{ event.type }}</span>
                <span class="trace-event-name">{{ event.name || '—' }}</span>
                <span class="trace-event-status" :data-status="event.status">{{ statusLabel(event.status) || '—' }}</span>
                <span class="trace-event-meta">
                  <template v-if="event.duration_ms != null">{{ event.duration_ms }}ms</template>
                  <template v-if="event.prompt_tokens || event.completion_tokens">
                    · {{ event.prompt_tokens }}→{{ event.completion_tokens }} tok
                  </template>
                  <template v-if="event.error_code"> · {{ event.error_code }}</template>
                </span>
              </div>
            </div>
          </template>
        </section>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

import { api } from '../../api/http'
import type { TraceTurn, TraceTurnDetail } from '../../api/types'

const props = defineProps<{
  show: boolean
  sessionId: string
  sessionName?: string
}>()

const emit = defineEmits<{
  (event: 'update:show', value: boolean): void
}>()

const turns = ref<TraceTurn[]>([])
const activeTurn = ref(0)
const detail = ref<TraceTurnDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const error = ref('')
const detailError = ref('')

async function load(): Promise<void> {
  if (!props.sessionId) return
  loading.value = true
  error.value = ''
  try {
    turns.value = await api.traces.turns(props.sessionId, 30)
    if (turns.value.length) {
      await selectTurn(activeTurn.value && turns.value.some((t) => t.turn === activeTurn.value) ? activeTurn.value : turns.value[0].turn)
    } else {
      activeTurn.value = 0
      detail.value = null
    }
  } catch (err: any) {
    turns.value = []
    error.value = err?.message || '加载历史轨迹失败'
  } finally {
    loading.value = false
  }
}

async function selectTurn(turn: number): Promise<void> {
  if (!props.sessionId || !turn) return
  activeTurn.value = turn
  detailLoading.value = true
  detailError.value = ''
  try {
    detail.value = await api.traces.turn(props.sessionId, turn)
  } catch (err: any) {
    detail.value = null
    detailError.value = err?.message || '加载回合轨迹失败'
  } finally {
    detailLoading.value = false
  }
}

function formatTime(value?: number | null): string {
  if (value == null) return '—'
  const date = new Date(value * 1000)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('zh-CN', { hour12: false })
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    running: '进行中',
    completed: '完成',
    finished: '完成',
    failed: '失败',
    cancelled: '取消',
    called: '已调用',
    succeeded: '成功',
    waiting: '等待确认',
    resolved: '已处理',
  }
  return labels[status] || status || ''
}

watch(
  () => props.show,
  (visible) => {
    if (visible) void load()
  },
)

watch(
  () => props.sessionId,
  () => {
    if (props.show) void load()
  },
)
</script>

<style scoped>
.trace-intro {
  margin: 0 0 12px;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.trace-state {
  padding: 40px 12px;
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
}

.trace-grid {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 14px;
  min-height: 420px;
}

.trace-turns {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 620px;
  overflow-y: auto;
  padding-right: 4px;
}

.trace-turn {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-main);
  padding: 8px 10px;
  text-align: left;
  cursor: pointer;
}

.trace-turn.active {
  border-color: var(--accent-ai);
  background: color-mix(in srgb, var(--accent-ai) 6%, var(--bg-main));
}

.trace-turn-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 3px;
}

.trace-status {
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  background: var(--bg-elevated);
  color: var(--text-secondary);
}

.trace-status[data-status='completed'],
.trace-status[data-status='finished'],
.trace-status[data-status='succeeded'] { color: #15803d; background: rgba(34, 197, 94, 0.12); }
.trace-status[data-status='failed'] { color: #b91c1c; background: rgba(239, 68, 68, 0.1); }
.trace-status[data-status='running'],
.trace-status[data-status='called'],
.trace-status[data-status='waiting'] { color: #b45309; background: rgba(245, 158, 11, 0.12); }

.trace-events {
  min-width: 0;
}

.trace-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-elevated);
  margin-bottom: 10px;
  font-size: 12px;
}

.trace-event-list {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  max-height: 560px;
  overflow-y: auto;
}

.trace-event {
  display: grid;
  grid-template-columns: 150px 150px minmax(80px, 1fr) 74px minmax(100px, 160px);
  gap: 8px;
  align-items: baseline;
  padding: 7px 10px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: 11.5px;
}

.trace-event:last-child {
  border-bottom: none;
}

.trace-event-time {
  color: var(--text-tertiary);
  font-family: var(--font-mono);
  font-size: 10px;
}

.trace-event-type {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-size: 10.5px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-event-name {
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.trace-event-status {
  color: var(--text-tertiary);
  font-size: 10px;
}

.trace-event-status[data-status='failed'] { color: #b91c1c; }
.trace-event-status[data-status='succeeded'],
.trace-event-status[data-status='completed'] { color: #15803d; }

.trace-event-meta {
  color: var(--text-tertiary);
  font-size: 10px;
  text-align: right;
}

@media (max-width: 800px) {
  .trace-grid {
    grid-template-columns: 1fr;
  }
  .trace-turns {
    max-height: 180px;
  }
  .trace-event {
    grid-template-columns: 1fr;
    gap: 2px;
  }
  .trace-event-meta {
    text-align: left;
  }
}
</style>
