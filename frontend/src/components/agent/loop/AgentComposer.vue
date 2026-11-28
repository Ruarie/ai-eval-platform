<template>
  <div class="loop-composer" :class="{ 'is-busy': busy || draft.submitting }" @dragover.prevent @drop.prevent="drop">
    <div v-if="busy || draft.submitting" class="composer-border-beam" aria-hidden="true"></div>
    <div v-if="draft.files.length" class="draft-files"><AttachmentPreview v-for="file in draft.files" :key="file.key" :attachment="{file_id:file.id,filename:file.filename,size:file.size,content_type:file.content_type,preview_url:file.source,uploading:file.uploading,uploadProgress:file.progress,error:!!file.error}" removable @remove="remove(file)"/></div>
    <textarea ref="input" v-model="draft.content" aria-label="消息" placeholder="输入消息，或拖入附件" aria-keyshortcuts="Enter Shift+Enter" rows="1" @input="resize" @paste="() => nextTick(resize)" @keydown="keydown" />
    <div class="composer-bottom">
      <input ref="picker" type="file" multiple hidden :accept="ui?.attachments.upload_suffixes.join(',')" @change="pick"/>
      <button class="loop-control attach-trigger" aria-label="添加附件" title="添加附件" type="button" :disabled="!ui" @click="picker?.click()"><n-icon :component="AddIcon" :size="17"/></button>
      <n-popover v-model:show="agentOpen" trigger="click" placement="top-start" :show-arrow="false">
        <template #trigger>
          <button class="loop-control model-trigger agent-trigger" type="button" aria-haspopup="dialog" :aria-expanded="agentOpen" :disabled="!agents.length">
            <span class="model-name">{{ agent?.name || '通用助手' }}</span><n-icon :component="ChevronDownIcon" :size="13" class="model-chevron"/>
          </button>
        </template>
        <section class="model-popover" aria-label="选择 Agent 专家">
          <header><strong>本轮专家</strong><p>专家决定工作方法与可用工具，切换后下一轮生效。</p></header>
          <button v-for="item in agents" :key="item.id" class="model-option" :class="{selected:item.id===agent?.id}" type="button" @click="chooseAgent(item.id)">
            <span><strong>{{ item.name }}</strong><small>{{ item.badge }} · {{ item.description }}</small></span><n-icon v-if="item.id===agent?.id" :component="CheckmarkIcon" :size="16"/>
          </button>
        </section>
      </n-popover>
      <n-popover v-model:show="tierOpen" trigger="click" placement="top-start" :show-arrow="false">
        <template #trigger>
          <button
            class="loop-control model-trigger tier-trigger"
            :class="{ 'is-warning': activeTier.warning }"
            type="button"
            aria-haspopup="dialog"
            :aria-expanded="tierOpen"
            :title="`权限档位：${activeTier.title}`"
          >
            <span class="tier-trigger-icon" :class="{ 'is-warning': activeTier.warning }">
              <svg v-if="activeTier.icon === 'hand'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M18 11V6a2 2 0 0 0-4 0v4M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8a6 6 0 0 0 12 0v-3a2 2 0 0 0-4 0" />
              </svg>
              <svg v-else-if="activeTier.icon === 'shield'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <polyline points="9 11 11 13 9 15" />
                <line x1="13" y1="15" x2="15" y2="15" />
              </svg>
              <svg v-else-if="activeTier.icon === 'warning'" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </span>
            <span class="model-name">{{ activeTier.title }}</span>
            <n-icon :component="ChevronDownIcon" :size="13" class="model-chevron" />
          </button>
        </template>
        <section class="tier-popover" aria-label="选择权限档位">
          <div class="tier-list">
            <button
              v-for="item in tierOptions"
              :key="item.value"
              class="tier-option"
              :class="{
                'is-selected': (permissionTier || '') === item.value,
                'is-warning': item.warning
              }"
              type="button"
              @click="chooseTier(item.value)"
            >
              <span class="tier-option-icon" :class="{ 'is-warning': item.warning }">
                <svg v-if="item.icon === 'hand'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M18 11V6a2 2 0 0 0-4 0v4M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8a6 6 0 0 0 12 0v-3a2 2 0 0 0-4 0" />
                </svg>
                <svg v-else-if="item.icon === 'shield'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <polyline points="9 11 11 13 9 15" />
                  <line x1="13" y1="15" x2="15" y2="15" />
                </svg>
                <svg v-else-if="item.icon === 'warning'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <circle cx="12" cy="12" r="3" />
                  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
                </svg>
              </span>
              <span class="tier-option-content">
                <strong class="tier-option-title" :class="{ 'is-warning': item.warning }">{{ item.title }}</strong>
                <small class="tier-option-desc" :class="{ 'is-warning': item.warning }">{{ item.description }}</small>
              </span>
              <span v-if="(permissionTier || '') === item.value" class="tier-option-check">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </span>
            </button>
          </div>
        </section>
      </n-popover>
      <n-popover v-model:show="modelOpen" trigger="click" placement="top-start" :show-arrow="false">
        <template #trigger>
          <button class="loop-control model-trigger" type="button" aria-haspopup="dialog" :aria-expanded="modelOpen" :disabled="!profiles.length">
            <ProviderLogo v-if="profile" :provider="getModelLogoKey(profile.model)" compact/>
            <span class="model-name">{{ profile?.model || '未配置模型' }}</span><n-icon :component="ChevronDownIcon" :size="13" class="model-chevron"/>
          </button>
        </template>
        <section class="model-popover" aria-label="选择 AgentLoop 协议档">
          <header><strong>本轮模型</strong><p>仅列出可用于 AgentLoop 的协议档，切换后下一轮生效。</p></header>
          <button v-for="item in profiles" :key="item.id" class="model-option" :class="{selected:item.id===profile?.id}" type="button" @click="chooseModel(item.id)">
            <ProviderLogo :provider="getModelLogoKey(item.model)" compact/><span><strong>{{ item.name }}</strong><small>{{ item.model }} · {{ protocolLabel(item.protocol) }}</small></span><n-icon v-if="item.id===profile?.id" :component="CheckmarkIcon" :size="16"/>
          </button>
        </section>
      </n-popover>
      <ThinkingControl :model-value="effort" :allowed="profile?.allowed_efforts || []" :model="profile?.model" :note="profile?.reasoning_note" :mode="profile?.reasoning_mode" @update:model-value="value => emit('effort', value)"/>
      <LoopContextMeter :meter="meter"/>
      <button
        class="loop-send"
        :class="{ 'is-busy': busy, 'is-cancelling': cancelling, 'is-ready': ready && draft.content.trim().length > 0 }"
        :aria-label="sendLabel"
        :title="sendLabel"
        :disabled="busy ? !canStop : !ready || !draft.content.trim() || draft.files.some(f => f.uploading || f.error) || draft.submitting"
        type="button"
        @click="handleClickSend"
      >
        <svg
          v-if="busy"
          class="loop-send-icon stop-icon"
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="currentColor"
          aria-hidden="true"
        >
          <rect x="6" y="6" width="12" height="12" rx="2" />
        </svg>
        <svg
          v-else
          class="loop-send-icon send-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
          aria-hidden="true"
        >
          <line x1="12" y1="19" x2="12" y2="5"></line>
          <polyline points="5 12 12 5 19 12"></polyline>
        </svg>
        <span class="sr-only">{{ sendLabel }}</span>
      </button>
    </div>
    <p v-if="draft.pending" class="draft-note">提交结果待同步。<button :disabled="!ready" @click="emit('retry')">使用原请求 ID 重发</button></p>
    <p v-if="notice" class="draft-note" role="status">{{ notice }}</p>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { NIcon, NPopover } from 'naive-ui'
import AddIcon from 'naive-ui/es/_internal/icons/Add'
import CheckmarkIcon from 'naive-ui/es/_internal/icons/Checkmark'
import ChevronDownIcon from 'naive-ui/es/_internal/icons/ChevronDown'
import { api } from '../../../api/http'
import { createRequestId } from '../../../utils/requestId'
import type { ConversationMetrics, Effort, LoopAgent, LoopMeter, LoopProfile, LoopUi } from '../../../api/agentLoopTypes'
import type { DraftFile, LoopDraft } from '../../../agent/loop/store'
import AttachmentPreview from '../AttachmentPreview.vue'
import ProviderLogo from '../../ProviderLogo.vue'
import { getModelLogoKey } from '../../../utils/providerLogo'
import ThinkingControl from './ThinkingControl.vue'
import LoopContextMeter from './LoopContextMeter.vue'

const props = withDefaults(defineProps<{
  draft: LoopDraft
  ui: LoopUi | null
  profile: LoopProfile | null
  profiles: LoopProfile[]
  agent: LoopAgent | null
  agents: LoopAgent[]
  effort: Effort | null
  meter?: LoopMeter | null
  metrics?: ConversationMetrics
  busy: boolean
  cancelling: boolean
  canStop: boolean
  ready: boolean
  permissionTier?: string | null
}>(), {
  permissionTier: '',
  metrics: () => ({ inputTokens: 0, outputTokens: 0, modelLatencyMs: 0, outputTokensPerSecond: null, cacheReadTokens: 0, cacheHitRate: null })
})
const emit = defineEmits<{
  submit: []
  stop: []
  retry: []
  effort: [Effort]
  model: [string]
  agent: [string]
  updatePermissionTier: [string]
}>()
const picker = ref<HTMLInputElement>(), input = ref<HTMLTextAreaElement>(), notice = ref('')
const modelOpen = ref(false), agentOpen = ref(false), tierOpen = ref(false)

interface TierOption {
  value: string
  title: string
  description: string
  icon: 'hand' | 'shield' | 'warning' | 'inherit'
  warning?: boolean
}

const tierOptions: TierOption[] = [
  {
    value: 'tier1',
    title: '请求批准',
    description: '编辑外部文件和使用互联网时始终询问',
    icon: 'hand',
  },
  {
    value: 'tier2',
    title: '帮我批准',
    description: '仅对检测到的风险操作请求批准',
    icon: 'shield',
  },
  {
    value: 'tier3',
    title: '完全访问权限',
    description: '可不受限制地访问互联网和沙箱工作区',
    icon: 'warning',
    warning: true,
  },
  {
    value: '',
    title: '继承全局默认',
    description: '沿用系统设置的权限档位',
    icon: 'inherit',
  },
]

const activeTier = computed(() => {
  const cur = props.permissionTier || ''
  return tierOptions.find(t => t.value === cur) || tierOptions[3]
})

function chooseTier(value: string) {
  tierOpen.value = false
  emit('updatePermissionTier', value)
}
const sendLabel = computed(() => props.busy ? (props.cancelling ? '正在取消' : '停止执行') : props.draft.submitting ? '正在提交' : '发送')
const protocolLabels: Record<string, string> = { openai_chat: 'OpenAI 兼容', openai_responses: 'Responses', anthropic_messages: 'Anthropic' }
function handleClickSend() {
  if (props.busy) { emit('stop'); return }
  emit('submit')
}
/** IME 选词不提交；运行中的 Enter 保留下一轮草稿。 */
function keydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault()
    if (!props.busy && props.ready && props.draft.content.trim() && !props.draft.submitting && !props.draft.files.some(f => f.uploading || f.error)) {
      emit('submit')
    }
  }
}
function resize() {
  const el = input.value
  if (!el) return
  if (!props.draft.content) {
    el.style.height = ''
    el.style.overflowY = 'hidden'
    return
  }
  el.style.height = 'auto'
  const scrollH = el.scrollHeight
  const targetH = Math.min(200, Math.max(52, scrollH))
  el.style.height = `${targetH}px`
  el.style.overflowY = scrollH > 200 ? 'auto' : 'hidden'
}
watch([() => props.draft, () => props.draft?.content], () => {
  nextTick(resize)
}, { immediate: true })
function focus() { nextTick(() => { input.value?.focus(); resize() }) }
function chooseModel(id: string) { modelOpen.value = false; emit('model', id) }
function chooseAgent(id: string) { agentOpen.value = false; emit('agent', id) }
function protocolLabel(protocol: string) { return protocolLabels[protocol] || protocol }
defineExpose({ focus })
/** Tombstone 先标记再移除；迟到上传只结束请求，不能复活草稿引用。 */
function remove(file: DraftFile) { file.removed = true; URL.revokeObjectURL(file.source); props.draft.files = props.draft.files.filter(f => f.key !== file.key) }
async function upload(files: File[]) {
  // 新建/切换会话时能力尚在读取，不能把此时拖入的文件误报为不支持的类型。
  if (!props.ui) { notice.value = '正在读取附件能力，请稍后重试'; return }
  const draft = props.draft
  for (const file of files) {
    const caps = props.ui?.attachments, suffix = '.' + file.name.split('.').pop()?.toLowerCase()
    if (!caps || !caps.upload_suffixes.includes(suffix) || file.size > caps.max_bytes || (caps.image_suffixes.includes(suffix) && file.size > caps.max_image_bytes)) { notice.value = `附件 ${file.name} 不符合服务端类型或大小限制`; continue }
    const value: DraftFile = { key: createRequestId(), filename: file.name, size: file.size, content_type: file.type, source: URL.createObjectURL(file), uploading: true, progress: 0, removed: false }
    draft.files.push(value)
    // 操作响应式代理，上传回调仍然绑定原会话草稿。
    const staged = draft.files[draft.files.length - 1]
    try { const result = await api.files.upload(file, progress => { if (!staged.removed) staged.progress = progress }); if (!staged.removed) Object.assign(staged, { id: result.id, uploading: false, progress: 100 }) }
    catch { if (!staged.removed) { staged.uploading = false; staged.error = '上传失败，请移除后重试' } }
  }
}
function pick(event: Event) { const el = event.target as HTMLInputElement; void upload(Array.from(el.files || [])); el.value = '' }
function drop(event: DragEvent) { void upload(Array.from(event.dataTransfer?.files || [])) }
</script>
<style scoped>
.loop-composer {
  position: relative;
  padding: 10px 10px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  background: var(--bg-card);
  transition: border-color .15s ease, box-shadow .15s ease;
}

.loop-composer:hover {
  border-color: color-mix(in srgb, var(--accent-ai) 30%, var(--border-subtle));
}

.loop-composer:focus-within {
  border-color: var(--accent-ai);
  box-shadow: var(--focus-ring);
}

.loop-composer textarea {
  display: block;
  width: 100%;
  min-height: 52px;
  max-height: min(200px, 50dvh);
  padding: 5px 6px;
  border: 0;
  resize: none;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-size: 15px;
  line-height: 1.6;
}

.loop-composer textarea::placeholder { color: var(--text-tertiary); }
.loop-composer textarea:focus-visible { box-shadow: none; }

.composer-bottom {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  min-width: 0;
  min-height: 34px;
  padding-top: 2px;
}

.loop-control {
  display: inline-flex;
  flex: 0 0 auto;
  min-width: 0;
  min-height: 32px;
  align-items: center;
  padding: 4px 6px;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  cursor: pointer;
}

.loop-control:hover:not(:disabled), .loop-control[aria-expanded='true'] {
  background: var(--bg-elevated);
  color: var(--text-primary);
}

.loop-control:disabled { cursor: default; opacity: .55; }

.attach-trigger {
  justify-content: center;
  width: 32px;
  padding: 0;
  background: var(--bg-elevated);
}

.model-trigger { max-width: min(230px, 45%); gap: 4px; }
.model-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-chevron { flex-shrink: 0; color: var(--text-tertiary); }

.model-popover, .tier-popover {
  width: min(318px, calc(100vw - 36px));
  max-height: min(420px, 55dvh);
  overflow: auto;
  padding: 4px;
}

.model-popover header { padding: 6px 8px 8px; }
.model-popover header strong { color: var(--text-primary); font-size: 13px; }
.model-popover header p { margin: 3px 0 0; color: var(--text-secondary); font-size: 11.5px; line-height: 1.5; }
.tier-list { display: grid; gap: 2px; }

.model-option, .tier-option {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--text-primary);
  text-align: start;
  cursor: pointer;
}

.model-option:hover, .tier-option:hover { background: var(--bg-elevated); }

.model-option.selected, .tier-option.is-selected {
  border-color: color-mix(in srgb, var(--accent-ai) 22%, var(--border-subtle));
  background: var(--t-agent);
}

.model-option > span, .tier-option-content { display: grid; flex: 1; min-width: 0; gap: 2px; }
.model-option strong, .model-option small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-option strong, .tier-option-title { font-size: 13px; line-height: 1.35; }
.model-option small, .tier-option-desc { color: var(--text-secondary); font-size: 11.5px; line-height: 1.4; }
.model-option > .n-icon, .tier-option-check { flex-shrink: 0; color: var(--c-agent); }

.tier-trigger-icon, .tier-option-icon, .tier-option-check { display: inline-flex; flex-shrink: 0; align-items: center; }
.tier-option-icon { width: 22px; color: var(--text-secondary); }
.tier-trigger.is-warning, .tier-option-icon.is-warning, .tier-option-title.is-warning { color: var(--accent-warning); }

.loop-send {
  display: inline-flex;
  flex: 0 0 36px;
  width: 36px;
  height: 34px;
  align-items: center;
  justify-content: center;
  margin-inline-start: auto;
  padding: 0;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--accent-solid);
  color: #fff;
  cursor: pointer;
}

.loop-send:not(:disabled):hover {
  background: color-mix(in srgb, var(--accent-solid) 90%, var(--text-primary));
}

.loop-send:disabled {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
  cursor: not-allowed;
}

.loop-send.is-cancelling { cursor: wait; }
.loop-send-icon { display: block; flex-shrink: 0; }

.draft-files { display: flex; flex-wrap: wrap; gap: 6px; padding: 2px 2px 5px; }
.draft-note { margin: 6px 5px 1px; color: var(--text-secondary); font-size: 11px; }

.draft-note button {
  padding: 0 4px;
  border: 0;
  background: transparent;
  color: var(--c-agent);
  text-decoration: underline;
  cursor: pointer;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* 生成中以细线标记输入区，同时保留可见的停止按钮。 */
.loop-composer.is-busy { border-color: color-mix(in srgb, var(--accent-ai) 42%, var(--border-subtle)); }

.composer-border-beam {
  position: absolute;
  inset: -1px 14px auto;
  height: 2px;
  overflow: hidden;
  background: var(--t-agent);
  pointer-events: none;
}

.composer-border-beam::before {
  content: '';
  display: block;
  width: 35%;
  height: 100%;
  background: linear-gradient(90deg, transparent, var(--accent-ai), transparent);
  animation: composer-progress 2.7s ease-in-out infinite;
}

@keyframes composer-progress {
  from { transform: translateX(-100%); }
  to { transform: translateX(287%); }
}

@media (max-width: 560px) {
  .loop-composer { padding: 7px; }
  .loop-composer textarea { font-size: 16px; }
}

@media (prefers-reduced-motion: reduce) {
  .loop-composer { transition: none; }
  .composer-border-beam::before { animation: none; }
}

@media (forced-colors: active) {
  .loop-composer textarea:focus-visible { outline: 2px solid CanvasText; }
}
</style>
