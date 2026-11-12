<template>
  <!-- 顶部 Agent 默认模型快速控制栏 -->
  <div class="panel agent-default-bar">
    <div class="agent-default-info">
      <div class="agent-default-badge">Agent 核心驱动</div>
      <div v-if="selectedAgentProfile" class="agent-default-content">
        <ProviderLogo :provider="getModelLogoKey(selectedAgentProfile.model)" :size="20" compact />
        <span class="agent-default-name">{{ selectedAgentProfile.name }}</span>
        <span class="mono agent-default-model">{{ selectedAgentProfile.model }}</span>
        <span class="agent-default-url-tag">{{ selectedAgentProfile.full_url ? '完整 URL' : 'Base URL' }}</span>
      </div>
      <div v-else class="agent-default-content empty">
        <span>未指定默认模型（新对话将使用系统默认配置）</span>
      </div>
    </div>

    <div class="agent-default-controls">
      <n-select
        v-model:value="selectedAgentProfileId"
        class="agent-select-input"
        placeholder="选择 Agent 默认协议档"
        :options="agentProfileOptions"
        :loading="agentProfileSaving"
        :disabled="loading || agentProfileSaving"
        @update:value="handleUpdateAgentProfile"
      />
      <button
        v-if="selectedAgentProfile"
        class="btn btn-secondary btn-sm"
        @click="openModal(selectedAgentProfile)"
      >
        配置模型
      </button>
    </div>
  </div>

  <!-- 协议档列表主面板 -->
  <div class="panel">
    <div class="panel-header-row">
      <div class="panel-title-area">
        <span class="panel-title-text">模型协议档</span>
        <span class="panel-count-pill">{{ filteredProfiles.length }} / {{ profiles.length }}</span>
      </div>

      <div class="panel-actions-area">
        <div class="view-mode-toggle">
          <button
            class="toggle-btn"
            :class="{ active: viewMode === 'cards' }"
            @click="viewMode = 'cards'"
          >
            卡片
          </button>
          <button
            class="toggle-btn"
            :class="{ active: viewMode === 'table' }"
            @click="viewMode = 'table'"
          >
            表格
          </button>
        </div>

        <button class="btn btn-primary btn-sm" @click="openModal(null)">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          <span>新增协议档</span>
        </button>

        <button class="btn btn-secondary btn-sm" :disabled="loading" @click="loadProfiles">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"></polyline>
            <polyline points="1 20 1 14 7 14"></polyline>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
          </svg>
          <span>刷新</span>
        </button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="profile-filters-bar">
      <n-input
        v-model:value="profileSearch"
        clearable
        placeholder="搜索名称、模型标识或端点…"
        class="filter-search-input"
      />
      <n-select
        v-model:value="vendorFilter"
        :options="vendorFilters"
        clearable
        placeholder="全部供应商"
        class="filter-select"
      />
      <n-select
        v-model:value="usageFilter"
        :options="usageFilters"
        clearable
        placeholder="全部用途"
        class="filter-select"
      />
    </div>

    <!-- 加载中 -->
    <p v-if="loading" role="status" class="small tertiary">正在加载协议档…</p>

    <!-- 模式 1：供应商卡片网格 -->
    <div v-if="viewMode === 'cards'" class="vendor-cards-container">
      <div
        v-for="group in vendorGroups"
        :key="group.key"
        class="vendor-group-card"
      >
        <div class="vendor-group-header">
          <div class="vendor-info">
            <div class="vendor-title-row">
              <ProviderLogo :provider="group.logoKey" :size="20" compact />
              <span class="vendor-name">{{ group.name }}</span>
              <span class="vendor-count-badge">{{ group.profiles.length }}</span>
            </div>
            <div class="vendor-url mono" :title="group.base_url">{{ group.base_url }}</div>
          </div>
          <button
            class="btn btn-secondary btn-xs"
            @click="openModalWithVendor(group)"
          >
            + 添加模型
          </button>
        </div>

        <!-- 模型项列表 -->
        <div class="vendor-models-grid">
          <div
            v-for="p in group.profiles"
            :key="p.id"
            class="model-chip-card"
            :class="{ 'is-agent-core': p.id === selectedAgentProfileId }"
          >
            <div class="model-chip-top">
              <div class="model-chip-title-wrap">
                <ProviderLogo class="model-chip-brand" :provider="getModelLogoKey(p.model)" compact :size="18" />
                <span class="model-chip-name" :title="p.name">{{ p.name }}</span>
                <span v-if="p.id === selectedAgentProfileId" class="tag-soft agent-core-tag">核心驱动</span>
              </div>

              <!-- 探活按钮 -->
              <button
                v-if="pingStates[p.id]"
                class="ping-badge"
                :class="pingStates[p.id].ok ? 'ok' : 'err'"
                :disabled="pinging[p.id]"
                title="点击重新测试连通性"
                @click="handlePing(p)"
              >
                {{ pingStates[p.id].ok ? `${pingStates[p.id].latencyMs ?? '—'}ms` : '测试未通过' }}
              </button>
              <button
                v-else
                class="link-btn small"
                :disabled="pinging[p.id]"
                @click="handlePing(p)"
              >
                {{ pinging[p.id] ? '探活中…' : '探活' }}
              </button>
            </div>

            <div class="model-chip-meta">
              <span class="mono model-id-tag" :title="p.model">{{ p.model }}</span>
              <span class="mono protocol-tag">{{ p.protocol }}</span>
              <span v-if="p.full_url" class="url-mode-tag">完整 URL</span>
              <span class="mono window-tag" title="上下文容量">{{ formatContextWindow(p.context_window) }}</span>
            </div>

            <div class="model-chip-bottom">
              <div class="row wrap" style="gap: 4px">
                <span v-if="p.usages?.includes('target')" class="kind-tag kind-benchmark">被测</span>
                <span v-if="p.usages?.includes('judge')" class="kind-tag kind-cases">裁判</span>
                <span v-if="p.usages?.includes('agent')" class="kind-tag kind-rag">Agent</span>
              </div>
              <div class="row" style="gap: 6px">
                <button v-if="p.usages?.includes('agent')" class="link-btn small" @click="emit('open-agent-prompt', p)">提示词</button>
                <button class="link-btn small" @click="openModal(p)">编辑</button>
                <button
                  class="link-btn danger small"
                  :disabled="p.id === selectedAgentProfileId"
                  :title="p.id === selectedAgentProfileId ? '当前档已被指定为 Agent 默认后端，禁止删除' : ''"
                  @click="handleDelete(p)"
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!loading && filteredProfiles.length === 0" class="empty-state-wrap">
        <EmptyState title="暂无匹配的协议档" description="调整搜索条件，或新增供应商协议档。">
          <template #action>
            <button class="btn btn-primary btn-sm" @click="openModal(null)">新增协议档</button>
          </template>
        </EmptyState>
      </div>
    </div>

    <!-- 模式 2：表格视图 -->
    <div v-else class="profile-table-scroll">
      <table class="ds-table">
        <thead>
          <tr>
            <th>协议档名称</th>
            <th style="width: 155px">供应商</th>
            <th style="width: 140px">协议类型</th>
            <th style="width: 160px">模型标识</th>
            <th style="width: 100px">上下文窗口</th>
            <th>请求地址</th>
            <th style="width: 130px">用途</th>
            <th style="width: 110px">连通性</th>
            <th style="width: 180px; text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in filteredProfiles" :key="p.id">
            <td style="font-weight: 600; font-size: 13.5px">
              <span class="row" style="gap: 8px; align-items: center">
                <span>{{ p.name }}</span>
                <span v-if="p.id === selectedAgentProfileId" class="tag-soft agent-core-tag">核心驱动</span>
              </span>
            </td>
            <td>
              <span class="row" style="gap: 6px; align-items: center">
                <ProviderLogo :provider="getProfileVendor(p)" compact :size="18" />
                <span class="provider-cell-name">{{ VENDOR_NAMES[getProfileVendor(p)] }}</span>
              </span>
            </td>
            <td>
              <span class="mono" style="font-size: 12px">{{ p.protocol }}</span>
            </td>
            <td>
              <span class="row model-id-cell">
                <ProviderLogo :provider="getModelLogoKey(p.model)" compact :size="16" />
                <span class="mono">{{ p.model }}</span>
              </span>
            </td>
            <td>
              <span class="mono window-tag">{{ formatContextWindow(p.context_window) }}</span>
            </td>
            <td>
              <span class="mono" style="font-size: 11.5px; color: var(--text-secondary)">{{ p.base_url }}</span>
              <span v-if="p.full_url" class="url-mode-tag">完整 URL</span>
            </td>
            <td>
              <div class="row wrap" style="gap: 4px">
                <span v-if="p.usages?.includes('target')" class="kind-tag kind-benchmark">被测</span>
                <span v-if="p.usages?.includes('judge')" class="kind-tag kind-cases">裁判</span>
                <span v-if="p.usages?.includes('agent')" class="kind-tag kind-rag">Agent</span>
              </div>
            </td>
            <td>
              <button
                v-if="pingStates[p.id]"
                class="ping-badge"
                :class="pingStates[p.id].ok ? 'ok' : 'err'"
                :disabled="pinging[p.id]"
                title="点击重新探活"
                @click="handlePing(p)"
              >
                {{ pingStates[p.id].ok ? `${pingStates[p.id].latencyMs ?? '—'}ms` : '失败' }}
              </button>
              <button v-else class="link-btn small" :disabled="pinging[p.id]" @click="handlePing(p)">
                {{ pinging[p.id] ? '探活中…' : '探活' }}
              </button>
            </td>
            <td style="text-align: right">
              <div class="row" style="justify-content: flex-end; gap: 4px">
                <button class="link-btn small" :disabled="checkingId === p.id" @click="handleCheck(p)">
                  {{ checkingId === p.id ? '检测中…' : '详情' }}
                </button>
                <button v-if="p.usages?.includes('agent')" class="link-btn small" @click="emit('open-agent-prompt', p)">提示词</button>
                <button class="link-btn small" @click="openModal(p)">编辑</button>
                <button
                  class="link-btn danger small"
                  :disabled="p.id === selectedAgentProfileId"
                  :title="p.id === selectedAgentProfileId ? '当前档已被指定为 Agent 默认后端，禁止删除' : ''"
                  @click="handleDelete(p)"
                >
                  删除
                </button>
              </div>
            </td>
          </tr>

          <tr v-if="!loading && filteredProfiles.length === 0">
            <td colspan="9">
              <EmptyState title="暂无匹配的协议档" description="点击右上角新增 OpenAI / Anthropic 协议档">
                <template #action>
                  <button class="btn btn-primary btn-sm" @click="openModal(null)">新增协议档</button>
                </template>
              </EmptyState>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <ProfileModal
    v-model:show="showModal"
    :profile="selectedProfile"
    :initial-data="modalInitialData"
    @success="loadProfiles"
  />

  <CheckResultModal
    v-model:show="showCheckModal"
    :result="checkResult"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { api } from '../../api/http'
import type { Profile, ProfileCheckOut } from '../../api/types'
import { safeBlur } from '../../utils/dom'
import { PROFILE_VENDORS, getProfileVendor } from '../../utils/profileVendors'
import { getModelLogoKey } from '../../utils/providerLogo'
import ProviderLogo, { type ProviderLogoKey } from '../ProviderLogo.vue'
import CheckResultModal from '../modals/CheckResultModal.vue'
import ProfileModal from '../modals/ProfileModal.vue'

const emit = defineEmits<{
  (event: 'agent-profile-change', profile: Profile | null): void
  (event: 'open-agent-prompt', profile: Profile): void
}>()

const message = useMessage()
const dialog = useDialog()

// ═══════════════════════════════════════════════════════════════
// 大模型协议档 (Profiles)
// ═══════════════════════════════════════════════════════════════
const viewMode = ref<'cards' | 'table'>('cards')
const profiles = ref<Profile[]>([])
const profileSearch = ref('')
const vendorFilter = ref<string | null>(null)
const usageFilter = ref<string | null>(null)

const filteredProfiles = computed(() => profiles.value.filter(p => {
  const text = profileSearch.value.trim().toLowerCase()
  return (!text || `${p.name} ${p.model} ${p.base_url}`.toLowerCase().includes(text))
    && (!vendorFilter.value || getProfileVendor(p) === vendorFilter.value)
    && (!usageFilter.value || p.usages?.includes(usageFilter.value as any))
}))

const vendorFilters = computed(() => [...PROFILE_VENDORS.map(v => ({label:v.name,value:v.key})), {label:'其它已有协议档',value:'custom'}])
const usageFilters = [{label:'Agent',value:'agent'},{label:'被测模型',value:'target'},{label:'裁判模型',value:'judge'}]

const loading = ref(false)
const selectedAgentProfileId = ref<string | null>(null)
const lastSavedAgentProfileId = ref<string | null>(null)
const agentProfileSaving = ref(false)
const selectedAgentProfile = computed(() => (
  profiles.value.find((profile) => profile.id === selectedAgentProfileId.value) || null
))

const showModal = ref(false)
const selectedProfile = ref<Profile | null>(null)
const showCheckModal = ref(false)
const checkResult = ref<ProfileCheckOut | null>(null)
const checkingId = ref<string | null>(null)

interface PingState {
  ok: boolean
  latencyMs: number | null
}
const pingStates = ref<Record<string, PingState>>({})
const pinging = ref<Record<string, boolean>>({})

const agentProfileOptions = computed(() =>
  profiles.value.filter(p => p.usages?.includes('agent')).map((p) => ({ label: `${p.name} (${p.model})`, value: p.id })),
)

interface VendorGroup {
  key: string
  name: string
  logoKey: ProviderLogoKey
  base_url: string
  full_url: boolean
  protocol: any
  profiles: Profile[]
}

const VENDOR_NAMES: Record<ProviderLogoKey, string> = {
  gemini: 'Google Gemini',
  nvidia: 'NVIDIA NIM',
  mimo: 'Xiaomi Mimo',
  openai: 'OpenAI',
  newapi: 'New API',
  anthropic: 'Anthropic Claude',
  deepseek: 'DeepSeek',
  stepfun: 'StepFun (阶跃星辰)',
  siliconflow: 'SiliconFlow (硅基流动)',
  qwen: '阿里百炼',
  volcengine: '火山引擎',
  qianfan: 'Baidu Qianfan (百度千帆)',
  hunyuan: 'Tencent Hunyuan (腾讯混元)',
  grok: 'xAI Grok',
  groq: 'Groq',
  ollama: 'Ollama (本地私有)',
  zhipu: 'GLM · 智谱',
  moonshot: 'Kimi · 月之暗面',
  minimax: 'MiniMax',
  mistral: 'Mistral AI',
  together: 'Together AI',
  custom: '自定义端点 / 内部代理',
}

const vendorGroups = computed<VendorGroup[]>(() => {
  const groups: Record<string, VendorGroup> = {}

  for (const p of filteredProfiles.value) {
    const logoKey = getProfileVendor(p)
    const key = `${logoKey}:${p.base_url}:${p.protocol}:${p.full_url ?? false}`
    const vName = VENDOR_NAMES[logoKey] || '自定义端点 / 内部代理'

    if (!groups[key]) {
      groups[key] = {
        key,
        name: vName,
        logoKey,
        base_url: p.base_url,
        full_url: p.full_url ?? false,
        protocol: p.protocol,
        profiles: [],
      }
    }
    groups[key].profiles.push(p)
  }

  return Object.values(groups)
})

function formatContextWindow(tokens?: number): string {
  if (!tokens || tokens === 200000) return '200k'
  if (tokens >= 1000000) return `${(tokens / 1000000).toFixed(0)}M`
  return `${(tokens / 1000).toFixed(0)}k`
}

const modalInitialData = ref<{ vendorKey?: string; base_url?: string; full_url?: boolean; protocol?: any; name?: string } | null>(null)

function openModal(profile: Profile | null) {
  safeBlur()
  selectedProfile.value = profile ? JSON.parse(JSON.stringify(profile)) : null
  modalInitialData.value = null
  showModal.value = true
}

function openModalWithVendor(group: VendorGroup) {
  safeBlur()
  selectedProfile.value = null
  modalInitialData.value = {
    vendorKey: group.logoKey !== 'custom' ? group.logoKey : undefined,
    base_url: group.base_url,
    full_url: group.full_url,
    protocol: group.protocol,
    name: group.name,
  }
  showModal.value = true
}

// ═══════════════════════════════════════════════════════════════
// 全局向量与重排模型 (RAG)
// ═══════════════════════════════════════════════════════════════

async function loadProfiles() {
  loading.value = true
  try {
    const [pListRes, settingsRes] = await Promise.allSettled([
      api.profiles.list(),
      api.admin.getSettings(),
    ])
    if (pListRes.status === 'fulfilled') {
      profiles.value = pListRes.value || []
    } else {
      message.error('协议档加载失败，请重试')
    }
    if (settingsRes.status === 'rejected') {
      message.error('默认模型设置加载失败，请重试')
    }
    if (settingsRes.status === 'fulfilled') {
      const settings = settingsRes.value
      selectedAgentProfileId.value = settings?.agent_profile_id || null
      lastSavedAgentProfileId.value = selectedAgentProfileId.value
    }
  } catch (err: any) {
    message.error(err.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}


async function handleUpdateAgentProfile(profileId: string) {
  agentProfileSaving.value = true
  try {
    await api.admin.updateSettings({ agent_profile_id: profileId })
    lastSavedAgentProfileId.value = profileId
    message.success('Agent 默认模型已指定')
  } catch (err: any) {
    selectedAgentProfileId.value = lastSavedAgentProfileId.value
    message.error(err.message || '设置失败')
  } finally {
    agentProfileSaving.value = false
  }
}

async function handlePing(p: Profile) {
  if (pinging.value[p.id]) return
  pinging.value[p.id] = true
  try {
    const res = await api.profiles.check(p.id)
    pingStates.value[p.id] = { ok: !!res.ok, latencyMs: res.latency_ms ?? null }
    if (res.ok) {
      message.success(`[${p.name}] 连通正常 · ${res.latency_ms ?? '—'}ms`)
    } else {
      message.error(`[${p.name}] ${res.message || res.error || '本次连通测试未通过'}`)
    }
  } catch (err: any) {
    pingStates.value[p.id] = { ok: false, latencyMs: null }
    message.error(`[${p.name}] ${err.message || '连通测试失败'}`)
  } finally {
    delete pinging.value[p.id]
  }
}

async function handleCheck(p: Profile) {
  safeBlur()
  checkingId.value = p.id
  try {
    const res = await api.profiles.check(p.id)
    checkResult.value = res
    showCheckModal.value = true
  } catch (err: any) {
    checkResult.value = { ok: false, error: err.message || '连接失败' }
    showCheckModal.value = true
  } finally {
    checkingId.value = null
  }
}

function handleDelete(p: Profile) {
  dialog.warning({
    title: `删除协议档「${p.name}」？`,
    content: '删除后，依赖此协议档的评测任务将无法再次发起。',
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.profiles.delete(p.id)
        message.success('协议档已删除')
        loadProfiles()
      } catch (err: any) {
        message.error(err.message || '删除失败')
      }
    },
  })
}


// 默认 Agent 协议档变化时同步给父视图（技能面板也要用）。
watch(selectedAgentProfile, (profile) => emit('agent-profile-change', profile), { immediate: true })

onMounted(loadProfiles)
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   Tab 1：大模型协议档
   ═══════════════════════════════════════════════════════════════ */
/* Agent 默认模型横向控制条 */
.agent-default-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px;
  padding: 12px 18px;
}
.agent-default-info {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1 1 320px;
}
.agent-default-badge {
  font-size: 11px;
  font-weight: 700;
  color: var(--c-profiles, #1f5947);
  background: var(--t-profiles, rgba(22, 151, 122, 0.1));
  border: 1px solid var(--c-profiles, rgba(22, 151, 122, 0.2));
  padding: 3px 8px;
  border-radius: 6px;
  white-space: nowrap;
}
.agent-default-content {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-wrap: wrap;
}
.agent-default-content.empty {
  color: var(--text-tertiary, #9ca3af);
  font-size: 12.5px;
}
.agent-default-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  white-space: nowrap;
}
.agent-default-model {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  background: var(--bg-elevated, #f3f4f6);
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
}
.agent-default-url-tag {
  font-size: 10.5px;
  color: var(--text-tertiary, #9ca3af);
}
.agent-default-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}
.agent-select-input {
  width: 260px;
}
@media (max-width: 640px) {
  .agent-default-controls {
    width: 100%;
  }
  .agent-select-input {
    flex: 1;
    width: auto;
  }
  .vendor-models-grid {
    grid-template-columns: 1fr;
  }
}

/* 协议档筛选工具条 */
.profile-filters-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0 16px;
  flex-wrap: wrap;
}
.filter-search-input {
  flex: 1 1 240px;
  min-width: 180px;
}
.filter-select {
  flex: 0 1 170px;
  min-width: 130px;
}

/* 供应商卡片容器与自适应网格 */
.vendor-cards-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.vendor-group-card {
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 14px;
  background: var(--bg-card, #ffffff);
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.vendor-group-card:hover {
  border-color: rgba(217, 119, 6, 0.3);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.04);
}
.vendor-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
  padding-bottom: 10px;
}
.vendor-info {
  min-width: 0;
  flex: 1;
}
.vendor-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.vendor-name {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.vendor-count-badge {
  font-size: 11px;
  background: var(--t-profiles, #fef3c7);
  color: var(--c-profiles, #b45309);
  padding: 1.5px 7px;
  border-radius: 10px;
  font-weight: 600;
  border: 1px solid rgba(180, 83, 9, 0.15);
}
.vendor-url {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 内部模型芯片网格与动态流光动效 */
@keyframes pulse-border {
  0%, 100% {
    border-color: rgba(217, 119, 6, 0.65);
    box-shadow: 0 0 12px rgba(217, 119, 6, 0.15);
  }
  50% {
    border-color: rgba(245, 158, 11, 0.95);
    box-shadow: 0 0 20px rgba(245, 158, 11, 0.28);
  }
}

.vendor-models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
  width: 100%;
}
.model-chip-card {
  background: var(--bg-card, #ffffff);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: relative;
  min-width: 0;
  box-sizing: border-box;
  transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}
.model-chip-card:hover {
  transform: translateY(-2px);
  border-color: rgba(217, 119, 6, 0.45);
  box-shadow: 0 6px 20px -2px rgba(217, 119, 6, 0.12);
}
.model-chip-card.is-agent-core {
  background: var(--t-profiles);
  border: 1.5px solid var(--c-profiles);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(217, 119, 6, 0.15);
  animation: pulse-border 3.2s ease-in-out infinite;
}
.model-chip-card.is-agent-core:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px -2px rgba(217, 119, 6, 0.25);
}
.model-chip-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.model-chip-title-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}
.model-chip-brand {
  flex: 0 0 auto;
}
.model-chip-name {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.provider-cell-name {
  overflow: hidden;
  color: var(--text-secondary, #4b5563);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-id-cell {
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.model-id-cell .mono {
  min-width: 0;
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.agent-core-tag {
  background: var(--bg-main);
  color: var(--c-profiles);
  border: 1px solid var(--c-profiles);
  border-radius: 999px;
  padding: 1.5px 8px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.model-chip-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  flex-wrap: wrap;
}
.model-id-tag {
  background: var(--bg-elevated, #f3f4f6);
  padding: 2px 7px;
  border-radius: 5px;
  font-weight: 600;
  color: var(--text-secondary, #374151);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.model-chip-card.is-agent-core .model-id-tag {
  background: var(--bg-main);
  border-color: var(--border-subtle);
  color: var(--text-primary);
}
.protocol-tag {
  color: var(--text-tertiary, #9ca3af);
}
.model-chip-card.is-agent-core .protocol-tag {
  color: var(--text-tertiary);
}
.url-mode-tag {
  border-radius: 4px;
  background: var(--t-profiles, rgba(22, 151, 122, 0.1));
  color: var(--c-profiles, #1f5947);
  padding: 1px 5px;
  font-size: 10.5px;
  font-family: var(--font-mono);
}
.window-tag {
  padding: 1px 6px;
  background: var(--bg-elevated, #f3f4f6);
  color: var(--text-secondary, #4b5563);
  border-radius: 4px;
  font-size: 11px;
}
.model-chip-card.is-agent-core .window-tag {
  background: var(--bg-main);
  color: var(--text-secondary);
  border: 1px solid var(--border-subtle);
}
.model-chip-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.04));
  margin-top: 4px;
}
.model-chip-card.is-agent-core .model-chip-bottom {
  border-top-color: rgba(217, 119, 6, 0.2);
}
.model-chip-bottom .link-btn {
  color: #047857;
  font-size: 12px;
  font-weight: 500;
  transition: color 0.15s ease;
}
.model-chip-bottom .link-btn:hover {
  color: #065f46;
}
.model-chip-bottom .link-btn.danger {
  color: #9ca3af;
}
.model-chip-bottom .link-btn.danger:hover {
  color: #ef4444;
}

/* 探活轻量化胶囊 */
.ping-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 5px;
  cursor: pointer;
  white-space: nowrap;
  border: 1px solid transparent;
}
.ping-badge.ok {
  background: rgba(16, 185, 129, 0.1);
  color: var(--accent-success, #10b981);
  border-color: rgba(16, 185, 129, 0.25);
}
.ping-badge.err {
  background: rgba(239, 68, 68, 0.1);
  color: var(--accent-error, #ef4444);
  border-color: rgba(239, 68, 68, 0.25);
}

/* 表格响应式滚动 */
.profile-table-scroll {
  overflow-x: auto;
  width: 100%;
  -webkit-overflow-scrolling: touch;
}
.profile-table-scroll table {
  min-width: 900px;
  width: 100%;
}


/* 面板骨架样式：scoped 样式不跨组件生效，随组件携带一份。 */
.panel-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.panel-title-area {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.panel-title-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  letter-spacing: -0.01em;
}
.panel-count-pill {
  font-size: 11.5px;
  font-family: var(--font-mono);
  color: var(--text-tertiary, #9ca3af);
  background: var(--bg-elevated, #f3f4f6);
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
}
.panel-actions-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.view-mode-toggle {
  display: inline-flex;
  background: var(--bg-elevated, #f3f4f6);
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
}
.toggle-btn {
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
  transition: all 0.15s ease;
}
.toggle-btn.active {
  background: var(--bg-card, #ffffff);
  color: var(--c-profiles, #1f5947);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.empty-state-wrap {
  grid-column: 1 / -1;
  width: 100%;
}
</style>
