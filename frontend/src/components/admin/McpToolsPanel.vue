<template>
  <div class="mcp-center-container">
    <!-- 顶部操作栏 -->
    <div class="panel">
      <div class="panel-header-row">
        <div class="panel-title-area">
          <span class="panel-title-text">MCP 服务器与工具清单</span>
          <span class="badge" :class="mcpBadgeClass">{{ mcpBadgeText }}</span>
        </div>

        <div class="panel-actions-area">
          <button
            class="btn btn-secondary btn-sm"
            :disabled="mcpHealthChecking"
            @click="handleRunHealthCheck"
          >
            {{ mcpHealthChecking ? '自检中…' : '健康自检' }}
          </button>
          <button
            class="btn btn-secondary btn-sm"
            @click="handleExportMcpJson"
          >
            导出契约 JSON
          </button>
          <button
            class="btn btn-secondary btn-sm"
            :disabled="mcpLoading"
            @click="handleRefreshMcpTools"
          >
            {{ mcpLoading ? '刷新中…' : '刷新清单' }}
          </button>
          <button
            class="btn btn-sign btn-sm"
            @click="handleOpenAddExternalServer"
          >
            媒体 MCP 说明
          </button>
        </div>
      </div>

      <!-- 通道状态指示横带 -->
      <div class="mcp-channels-strip mt14">
        <div class="channel-chip">
          <span class="status-dot"></span>
          <span class="channel-name">原生工具 (Native)</span>
          <span class="channel-meta mono">{{ nativeTools.length }} 个 · 进程直连</span>
        </div>
        <div class="channel-chip">
          <span class="status-dot" :class="{ 'is-disabled': internalMcpTools.length === 0 }"></span>
          <span class="channel-name">内部 MCP (Tasks)</span>
          <span class="channel-meta mono">{{ internalMcpTools.length }} 个 · 任务桥接</span>
        </div>
        <div class="channel-chip" :class="{ standby: !mediaMcpForm.enabled }">
          <span class="status-dot" :class="{ 'is-disabled': !mediaMcpForm.enabled }"></span>
          <span class="channel-name">媒体 MCP (Streamable HTTP)</span>
          <span class="channel-meta mono">{{ mediaMcpTools.length }} 个 · {{ mediaMcpForm.enabled ? '已启用' : '未启用' }}</span>
        </div>
      </div>

      <div class="media-mcp-config mt14">
        <div class="media-mcp-config-heading">
          <div>
            <div class="panel-section-title">生图与视频 MCP</div>
            <div class="small tertiary mt2">固定通过 Compose 内网 Streamable HTTP 调用；密钥仅在服务端保存，留空不会覆盖已保存密钥。</div>
          </div>
          <span class="badge" :class="mediaMcpForm.enabled ? 'badge-succeeded' : 'badge-warning'">
            {{ mediaMcpForm.enabled ? '已启用' : '未启用' }}
          </span>
        </div>
        <div class="media-mcp-form-grid mt12">
          <label class="runtime-field media-mcp-switch">
            <span class="field-label">启用媒体 MCP</span>
            <n-switch v-model:value="mediaMcpForm.enabled" />
          </label>
          <label class="runtime-field">
            <span class="field-label">兼容模式地址</span>
            <n-input v-model:value="mediaMcpForm.compatible_base_url" placeholder="https://…/compatible-mode/v1" />
          </label>
          <label class="runtime-field">
            <span class="field-label">API Key</span>
            <n-input v-model:value="mediaMcpForm.api_key" type="password" show-password-on="click" placeholder="留空保留已保存密钥" />
          </label>
          <label class="runtime-field">
            <span class="field-label">生图模型</span>
            <n-input v-model:value="mediaMcpForm.image_model" placeholder="qwen-image-3.0-pro" />
          </label>
          <label class="runtime-field">
            <span class="field-label">视频模型</span>
            <n-input v-model:value="mediaMcpForm.video_model" placeholder="happyhorse-1.1-i2v" />
          </label>
          <label class="runtime-field">
            <span class="field-label">MCP 调用超时（秒）</span>
            <n-input-number v-model:value="mediaMcpForm.request_timeout_s" :min="10" :max="600" style="width: 100%" />
          </label>
        </div>
        <div class="row mt12" style="justify-content: space-between; gap: 12px">
          <span class="small tertiary">{{ mediaMcpConfig?.has_api_key ? '已保存 API Key' : '尚未保存 API Key' }} · 视频使用首帧图生模式并异步返回任务 ID</span>
          <button class="btn btn-primary btn-sm" :disabled="mediaMcpSaving || mediaMcpConfigLoading" @click="saveMediaMcpConfig">
            {{ mediaMcpSaving ? '保存中…' : '保存媒体 MCP 配置' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 工具清单过滤与呈现 -->
    <div class="panel">
      <div class="mcp-toolbar">
        <div class="mcp-filter-group">
          <!-- 通道分段器 -->
          <div class="pill-segmented">
            <button
              class="pill-btn"
              :class="{ active: mcpTransportFilter === 'all' }"
              @click="mcpTransportFilter = 'all'"
            >
              全部 ({{ mcpTools.length }})
            </button>
            <button
              class="pill-btn"
              :class="{ active: mcpTransportFilter === 'native' }"
              @click="mcpTransportFilter = 'native'"
            >
              原生 ToolCall ({{ nativeTools.length }})
            </button>
            <button
              class="pill-btn"
              :class="{ active: mcpTransportFilter === 'mcp' }"
              @click="mcpTransportFilter = 'mcp'"
            >
              MCP 工具 ({{ mcpExtTools.length }})
            </button>
            <button
              class="pill-btn"
              :class="{ active: mcpTransportFilter === 'external' }"
              @click="mcpTransportFilter = 'external'"
            >
              接入说明
            </button>
          </div>

          <!-- 权限分段器 -->
          <div v-if="mcpTransportFilter !== 'external'" class="pill-segmented">
            <button
              class="pill-btn"
              :class="{ active: mcpPermFilter === 'all' }"
              @click="mcpPermFilter = 'all'"
            >
              全部权限
            </button>
            <button
              class="pill-btn"
              :class="{ active: mcpPermFilter === 'read' }"
              @click="mcpPermFilter = 'read'"
            >
              只读 ({{ readToolsCount }})
            </button>
            <button
              class="pill-btn"
              :class="{ active: mcpPermFilter === 'write' }"
              @click="mcpPermFilter = 'write'"
            >
              写入 ({{ writeToolsCount }})
            </button>
          </div>

          <!-- 领域分类下拉 -->
          <div v-if="mcpTransportFilter !== 'external'" class="filter-dropdown-wrap">
            <n-select
              v-model:value="mcpDomainFilter"
              size="small"
              :options="domainFilterOptions"
            />
          </div>

          <!-- 搜索框 -->
          <div v-if="mcpTransportFilter !== 'external'" class="filter-search-wrap">
            <n-input
              v-model:value="mcpSearchKeyword"
              size="small"
              placeholder="搜索工具名或说明…"
              clearable
            />
          </div>
        </div>

        <!-- 视图切换 -->
        <div v-if="mcpTransportFilter !== 'external'" class="view-mode-toggle">
          <button
            class="toggle-btn"
            :class="{ active: mcpViewMode === 'cards' }"
            @click="mcpViewMode = 'cards'"
          >
            卡片
          </button>
          <button
            class="toggle-btn"
            :class="{ active: mcpViewMode === 'table' }"
            @click="mcpViewMode = 'table'"
          >
            表格
          </button>
        </div>
      </div>

      <!-- 视图 1：外部网关技术规范说明 -->
      <div v-if="mcpTransportFilter === 'external'" class="external-gateway-panel mt16">
        <div class="ext-hero-box">
          <div style="flex: 1">
            <div class="ext-title">外部 MCP Server 接入规范与隔离说明</div>
            <div class="ext-desc">
              媒体 MCP 使用标准 Streamable HTTP：API 先完成工具目录和权限裁决，再经 Compose 内网连接媒体服务。媒体服务独占上游凭据；生图同步返回临时地址，视频创建只返回异步任务 ID，须再查询状态。
            </div>
          </div>
          <button class="btn btn-sign btn-sm" @click="handleOpenAddExternalServer">
            查看接入边界
          </button>
        </div>

        <div class="ext-grid mt12">
          <div class="ext-card">
            <div class="ext-card-title">通信协议支持</div>
            <div class="ext-card-content">
              • Streamable HTTP：initialize → tools/list → tools/call。<br>
              • 服务发现固定为 Compose 私网 `media-mcp:8002/mcp`，不接受浏览器指定地址。
            </div>
          </div>
          <div class="ext-card">
            <div class="ext-card-title">安全风控门禁</div>
            <div class="ext-card-content">
              • 目录、参数与权限在 API 内完成；媒体服务不向浏览器暴露上游密钥。<br>
              • 视频创建不等待生成完成，查询结果中的临时视频地址需及时使用。
            </div>
          </div>
        </div>
      </div>

      <!-- 视图 2：卡片网格 -->
      <div v-else-if="mcpViewMode === 'cards'" class="mcp-cards-grid mt16">
        <div
          v-for="t in filteredMcpTools"
          :key="t.name"
          class="mcp-card"
          :class="{ 'is-disabled': t.enabled === false }"
        >
          <div class="mcp-card-top">
            <div class="mcp-tool-heading-wrap">
              <div class="mcp-tool-icon-box" :class="`tool-icon-${getToolDomain(t.name).key}`">
                <ToolIcon :name="t.name" :size="20" />
              </div>
              <div class="mcp-tool-heading">
                <div class="mcp-tool-title">{{ t.display_name || t.name }}</div>
                <div class="domain-tag mono">{{ t.name }}</div>
              </div>
            </div>

            <div class="row" style="gap: 4px; flex-shrink: 0">
              <span class="tag-soft">
                {{ t.transport === 'native' ? '原生' : t.category === 'external_mcp' ? '媒体 MCP' : '内部 MCP' }}
              </span>
              <span class="tag-soft" :class="getRiskBadge(t.risk_level).cls">
                {{ getRiskBadge(t.risk_level).label }}
              </span>
            </div>
          </div>

          <div class="mcp-tool-desc">{{ t.desc }}</div>

          <div class="tool-schema-brief">
            <div class="schema-brief-row">
              <span class="brief-k">入参:</span>
              <span class="brief-v mono">{{ getToolParamsPreview(t) }}</span>
            </div>
            <div class="schema-brief-row">
              <span class="brief-k">出参:</span>
              <span class="brief-v mono">{{ getToolOutputsPreview(t) }}</span>
            </div>
          </div>

          <div class="mcp-card-bottom">
            <div class="row" style="gap: 6px; align-items: center">
              <span class="status-dot" :class="{ 'is-disabled': t.enabled === false }"></span>
              <span class="small tertiary">
                {{ t.transport === 'native' ? '原生沙箱' : t.category === 'external_mcp' ? 'Streamable HTTP' : 'InProcess Host' }} · {{ t.timeout_s ?? '15' }}s
              </span>
            </div>
            <button
              class="btn btn-secondary btn-xs"
              @click="handleOpenMcpModal(t)"
            >
              契约详情
            </button>
          </div>
        </div>

        <div v-if="filteredMcpTools.length === 0" class="empty-state-wrap">
          <EmptyState :title="mcpEmptyTitle" :description="mcpEmptyDescription" />
        </div>
      </div>

      <!-- 视图 3：表格视图 -->
      <div v-else class="profile-table-scroll mt16">
        <table class="ds-table">
          <thead>
            <tr>
              <th style="width: 170px">工具名称</th>
              <th style="width: 100px">通道</th>
              <th style="width: 100px">领域</th>
              <th>说明</th>
              <th style="width: 140px">入参概要</th>
              <th style="width: 120px">出参概要</th>
              <th style="width: 90px">权限</th>
              <th style="width: 70px">超时</th>
              <th style="width: 90px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in filteredMcpTools" :key="t.name">
              <td>
                <div class="mcp-table-tool-col">
                  <div class="mcp-table-tool-icon" :class="`tool-icon-${getToolDomain(t.name).key}`">
                    <ToolIcon :name="t.name" :size="15" />
                  </div>
                  <div class="mcp-table-tool-info">
                    <div style="font-weight: 600; font-size: 13px">{{ t.display_name || t.name }}</div>
                    <div class="mono small tertiary" style="font-size: 10.5px">{{ t.name }}</div>
                  </div>
                </div>
              </td>
              <td>
                <span class="tag-soft">
                  {{ t.transport === 'native' ? '原生' : t.category === 'external_mcp' ? '媒体 MCP' : '内部 MCP' }}
                </span>
              </td>
              <td>
                <span class="tag-soft">{{ getToolDomain(t.name).label }}</span>
              </td>
              <td class="small" style="color: var(--text-primary)">{{ t.desc }}</td>
              <td class="mono small" style="color: var(--c-profiles)">{{ getToolParamsPreview(t) }}</td>
              <td class="mono small text-success">{{ getToolOutputsPreview(t) }}</td>
              <td>
                <span class="tag-soft" :class="getRiskBadge(t.risk_level).cls">
                  {{ getRiskBadge(t.risk_level).label }}
                </span>
              </td>
              <td class="mono small">{{ t.timeout_s ? `${t.timeout_s}s` : '—' }}</td>
              <td style="text-align: right">
                <button class="link-btn small" @click="handleOpenMcpModal(t)">
                  详情
                </button>
              </td>
            </tr>

            <tr v-if="filteredMcpTools.length === 0">
              <td colspan="9">
                <EmptyState :title="mcpEmptyTitle" :description="mcpEmptyDescription" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- MCP 工具详情弹窗：随面板一起迁移，父视图不再持有 MCP 弹窗状态。 -->
  <McpToolModal v-model:show="showMcpModal" :tool="selectedMcpTool" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { api } from '../../api/http'
import type { McpHealthCheckResponse, McpTool, MediaMcpConfig } from '../../api/types'
import { safeBlur } from '../../utils/dom'
import EmptyState from '../common/EmptyState.vue'
import McpToolModal from '../modals/McpToolModal.vue'
import ToolIcon from '../agent/loop/ToolIcon.vue'

const message = useMessage()
const dialog = useDialog()

// ═══════════════════════════════════════════════════════════════
// MCP 工具中心状态与交互管理
// ═══════════════════════════════════════════════════════════════
const mcpTools = ref<McpTool[]>([])
const mcpViewMode = ref<'cards' | 'table'>('cards')
const mcpPermFilter = ref<'all' | 'read' | 'write'>('all')
const mcpTransportFilter = ref<'all' | 'native' | 'mcp' | 'external'>('all')
const mcpDomainFilter = ref<string>('all')
const mcpSearchKeyword = ref('')
const mcpLoading = ref(false)
const mcpServerPingState = ref<{ ok: boolean; latencyMs: number | null } | null>(null)

// 全通道健康与连通性自检状态
const mcpHealthResult = ref<McpHealthCheckResponse | null>(null)
const mcpHealthChecking = ref(false)

type McpRequestState = 'idle' | 'loading' | 'success' | 'error'
const mcpRequestState = ref<McpRequestState>('idle')
const mcpRequestError = ref('')
const selectedMcpTool = ref<McpTool | null>(null)
const showMcpModal = ref(false)
const mediaMcpConfig = ref<MediaMcpConfig | null>(null)
const mediaMcpConfigLoading = ref(false)
const mediaMcpSaving = ref(false)
const mediaMcpForm = ref({
  enabled: false,
  compatible_base_url: '',
  api_key: '',
  image_model: 'qwen-image-3.0-pro',
  video_model: 'happyhorse-1.1-i2v',
  request_timeout_s: 180,
})

/** 原生基础工具（transport=native），由 NativeToolExecutor 直连执行 */
const nativeTools = computed(() => mcpTools.value.filter((t) => t.transport === 'native'))
/** 内部 MCP 扩展工具（transport=mcp），通过 MCPClientManager 调用 */
const mcpExtTools = computed(() => mcpTools.value.filter((t) => t.transport === 'mcp'))
const internalMcpTools = computed(() => mcpExtTools.value.filter((t) => t.category !== 'external_mcp'))
const mediaMcpTools = computed(() => mcpExtTools.value.filter((t) => t.category === 'external_mcp'))

const domainFilterOptions = [
  { label: '全部领域', value: 'all' },
  { label: '文件系统', value: 'file' },
  { label: '网络抓取', value: 'web' },
  { label: '沙箱命令', value: 'bash' },
  { label: '任务规划', value: 'plan' },
  { label: '任务调度', value: 'task' },
  { label: '模型资产', value: 'model' },
  { label: '数据集', value: 'dataset' },
  { label: '知识库', value: 'kb' },
  { label: '评测报告', value: 'report' },
  { label: '调度算力', value: 'dispatch' },
  { label: '用例管理', value: 'cases' },
  { label: '音色克隆', value: 'audio' },
  { label: '图像生成', value: 'image' },
]

/** 获取工具业务领域与图标映射 */
function getToolDomain(name: string): { label: string; icon: string; key: string } {
  if (
    name === 'read' ||
    name === 'read_image' ||
    name === 'write' ||
    name === 'edit' ||
    name === 'glob' ||
    name === 'grep' ||
    name === 'list_dir' ||
    name === 'str_replace_editor'
  ) {
    return { label: '文件系统', icon: '', key: 'file' }
  }
  if (name === 'web_search' || name === 'web_fetch') return { label: '网络抓取', icon: '', key: 'web' }
  if (name === 'bash') return { label: '沙箱命令', icon: '', key: 'bash' }
  if (name === 'task' || name === 'ask_user_question') return { label: '任务规划', icon: '', key: 'plan' }
  if (
    name.includes('task.create') ||
    name.includes('task.status') ||
    name.includes('task.cancel') ||
    name.startsWith('Task')
  ) {
    return { label: '任务调度', icon: '', key: 'task' }
  }
  if (name.startsWith('model.')) return { label: '模型资产', icon: '', key: 'model' }
  if (name.startsWith('dataset.')) return { label: '数据集', icon: '', key: 'dataset' }
  if (name.startsWith('kb.')) return { label: '知识库', icon: '', key: 'kb' }
  if (name.startsWith('report.')) return { label: '评测报告', icon: '', key: 'report' }
  if (name.startsWith('dispatch.')) return { label: '调度大盘', icon: '', key: 'dispatch' }
  if (name.startsWith('testcase.')) return { label: '用例管理', icon: '', key: 'cases' }
  if (name.startsWith('audio.')) return { label: '音色克隆', icon: '', key: 'audio' }
  if (name.startsWith('image.') || name.startsWith('video.') || name.includes('.image.generate') || name.includes('.video.')) {
    return { label: '媒体生成', icon: '', key: 'image' }
  }
  return { label: '内置通用', icon: '', key: 'other' }
}

/** 获取风险等级徽标配置 */
function getRiskBadge(risk?: string): { label: string; cls: string } {
  switch (risk) {
    case 'read': return { label: 'READ', cls: 'perm-badge-read' }
    case 'network': return { label: 'NET', cls: 'perm-badge-network' }
    case 'modify': return { label: 'WRITE', cls: 'perm-badge-write' }
    case 'code': return { label: 'CODE', cls: 'perm-badge-code' }
    case 'long': return { label: 'LONG', cls: 'perm-badge-write' }
    default: return { label: 'WRITE', cls: 'perm-badge-write' }
  }
}

const readToolsCount = computed(() => mcpTools.value.filter((t) => t.permission === 'read').length)
const writeToolsCount = computed(() => mcpTools.value.filter((t) => t.permission === 'write').length)
const disabledMcpToolsCount = computed(() => mcpTools.value.filter((t) => t.enabled === false).length)

const mcpBadgeClass = computed(() => {
  return mcpRequestState.value === 'success' && mcpTools.value.length > 0
    ? 'badge-succeeded'
    : 'badge-warning'
})

const mcpBadgeText = computed(() => {
  if (mcpRequestState.value === 'idle') return '尚未检查'
  if (mcpRequestState.value === 'loading') return '检查中…'
  if (mcpRequestState.value === 'error') return '接口不可用'
  if (mcpTools.value.length === 0) return '清单为空'
  return disabledMcpToolsCount.value ? `${disabledMcpToolsCount.value} 项未挂载` : '清单正常'
})

const mcpEmptyTitle = computed(() => {
  if (mcpRequestState.value === 'loading') return '正在读取工具清单'
  if (mcpRequestState.value === 'error') return '工具清单接口调用失败'
  if (mcpRequestState.value === 'success' && mcpTools.value.length === 0) {
    return '接口已连通，暂无工具'
  }
  return '未找到匹配的工具'
})

const mcpEmptyDescription = computed(() => {
  if (mcpRequestState.value === 'loading') return '正在调用 GET /api/mcp/all-tools，请稍候…'
  if (mcpRequestState.value === 'error') return mcpRequestError.value || '请确认登录状态与 API 服务是否正常。'
  if (mcpRequestState.value === 'success' && mcpTools.value.length === 0) {
    return '请点击"刷新清单"重新加载全量工具列表。'
  }
  return '请尝试清空搜索条件或重置筛选器'
})

function getToolParamsPreview(t: McpTool): string {
  const schema = t.parameters_schema
  if (!schema || !schema.properties) return '无参数'
  const req: string[] = Array.isArray(schema.required) ? schema.required : []
  const keys = Object.keys(schema.properties)
  if (keys.length === 0) return '无参数'
  return keys
    .slice(0, 3)
    .map((k) => (req.includes(k) ? `${k}*` : k))
    .join(', ') + (keys.length > 3 ? ` +${keys.length - 3}` : '')
}

function getToolOutputsPreview(t: McpTool): string {
  const schema = t.output_schema
  if (!schema || !schema.properties) return 'summary'
  const keys = Object.keys(schema.properties)
  if (keys.length === 0) return 'summary'
  return keys.slice(0, 2).join(', ') + (keys.length > 2 ? ` +${keys.length - 2}` : '')
}

const filteredMcpTools = computed(() => {
  return mcpTools.value.filter((t) => {
    if (mcpTransportFilter.value === 'native' && t.transport !== 'native') return false
    if (mcpTransportFilter.value === 'mcp' && t.transport !== 'mcp') return false
    if (mcpTransportFilter.value === 'external') return false
    if (mcpPermFilter.value !== 'all' && t.permission !== mcpPermFilter.value) return false
    if (mcpDomainFilter.value !== 'all') {
      const domain = getToolDomain(t.name)
      if (domain.key !== mcpDomainFilter.value) return false
    }
    if (mcpSearchKeyword.value.trim()) {
      const kw = mcpSearchKeyword.value.toLowerCase().trim()
      const matchName = t.name.toLowerCase().includes(kw)
      const matchDisplayName = (t.display_name || '').toLowerCase().includes(kw)
      const matchDesc = t.desc.toLowerCase().includes(kw)
      const matchDomain = getToolDomain(t.name).label.toLowerCase().includes(kw)
      if (!matchName && !matchDisplayName && !matchDesc && !matchDomain) return false
    }
    return true
  })
})

/** 将脱敏服务端配置投影到可编辑表单，Key 输入框始终保持空白。 */
function applyMediaMcpConfig(config: MediaMcpConfig) {
  mediaMcpConfig.value = config
  mediaMcpForm.value = {
    enabled: config.enabled,
    compatible_base_url: config.compatible_base_url,
    api_key: '',
    image_model: config.image_model,
    video_model: config.video_model,
    request_timeout_s: config.request_timeout_s,
  }
}

async function saveMediaMcpConfig() {
  mediaMcpSaving.value = true
  try {
    const saved = await api.mcp.updateMediaConfig({
      enabled: mediaMcpForm.value.enabled,
      compatible_base_url: mediaMcpForm.value.compatible_base_url.trim(),
      api_key: mediaMcpForm.value.api_key.trim() || undefined,
      image_model: mediaMcpForm.value.image_model.trim(),
      video_model: mediaMcpForm.value.video_model.trim(),
      request_timeout_s: mediaMcpForm.value.request_timeout_s,
    })
    applyMediaMcpConfig(saved)
    await handleRefreshMcpTools()
    message.success('媒体 MCP 配置已保存')
  } catch (err: any) {
    message.error(err.message || '媒体 MCP 配置保存失败')
  } finally {
    mediaMcpSaving.value = false
  }
}

async function handleRunHealthCheck() {
  mcpHealthChecking.value = true
  try {
    const res = await api.mcp.healthCheck()
    mcpHealthResult.value = res
    message.success(`自检完成 · 耗时 ${res.total_latency_ms}ms · 原生(${res.summary.native_tools_count}) · 内部 MCP(${res.summary.internal_mcp_tools_count}) · 媒体(${res.summary.external_mcp_servers_count})`)
  } catch (err: any) {
    message.error(`健康自检失败: ${err.message || '网络连接异常'}`)
  } finally {
    mcpHealthChecking.value = false
  }
}

async function handleRefreshMcpTools() {
  mcpLoading.value = true
  mediaMcpConfigLoading.value = true
  mcpRequestState.value = 'loading'
  mcpRequestError.value = ''
  const start = performance.now()
  try {
    const [res, healthRes, mediaConfig] = await Promise.all([
      api.mcp.tools(),
      api.mcp.healthCheck().catch(() => null),
      api.mcp.mediaConfig().catch(() => null),
    ])
    if (!res || !Array.isArray(res.items)) {
      throw new Error('工具清单接口返回格式不正确')
    }
    const latency = Math.round(performance.now() - start)
    mcpTools.value = res.items
    mcpRequestState.value = 'success'
    mcpServerPingState.value = { ok: true, latencyMs: Math.max(1, latency) }
    if (healthRes) {
      mcpHealthResult.value = healthRes
    }
    if (mediaConfig) {
      applyMediaMcpConfig(mediaConfig)
    }
    if (mcpTools.value.length > 0) {
      message.success(`已加载 ${mcpTools.value.length} 个工具 · ${mcpServerPingState.value.latencyMs}ms`)
    }
  } catch (err: any) {
    mcpRequestState.value = 'error'
    mcpRequestError.value = err.message || '调用 /api/mcp/all-tools 接口失败'
    mcpTools.value = []
    mcpServerPingState.value = { ok: false, latencyMs: null }
    message.error(mcpRequestError.value)
  } finally {
    mcpLoading.value = false
    mediaMcpConfigLoading.value = false
  }
}

function handleOpenMcpModal(tool: McpTool) {
  safeBlur()
  selectedMcpTool.value = tool
  showMcpModal.value = true
}

function handleExportMcpJson() {
  safeBlur()
  try {
    const payload = JSON.stringify(mcpTools.value, null, 2)
    navigator.clipboard.writeText(payload)
    message.success('已复制 MCP 工具契约 JSON')
  } catch {
    message.info('请在安全上下文中复制契约')
  }
}

function handleOpenAddExternalServer() {
  safeBlur()
  dialog.info({
    title: '媒体 MCP · 架构边界说明',
    content:
      '当前仅接入平台部署的 media-mcp 服务。API 固定通过 Compose 私网地址建立 Streamable HTTP 会话，媒体服务独占上游凭据；浏览器无法添加任意第三方 Server 或直接调用模型端点。',
    positiveText: '了解边界',
  })
}

onMounted(handleRefreshMcpTools)
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   MCP 服务器与工具清单
   ═══════════════════════════════════════════════════════════════ */
.mcp-center-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mcp-channels-strip {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.channel-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  padding: 8px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  flex: 1 1 200px;
}
.channel-chip.standby {
  opacity: 0.8;
}
.channel-name {
  font-weight: 600;
  color: var(--text-primary, #111827);
}
.channel-meta {
  font-size: 11.5px;
  color: var(--text-tertiary, #9ca3af);
  margin-left: auto;
}
.media-mcp-config {
  padding: 14px;
  border: 1px solid var(--c-profiles, rgba(22, 151, 122, 0.2));
  border-radius: 10px;
  background: var(--t-profiles, rgba(22, 151, 122, 0.05));
}
.media-mcp-config-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.media-mcp-form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 12px;
}
.media-mcp-form-grid .runtime-field {
  width: auto;
}
.media-mcp-switch {
  justify-content: center;
}
@media (max-width: 900px) {
  .media-mcp-form-grid {
    grid-template-columns: repeat(2, minmax(180px, 1fr));
  }
}
@media (max-width: 560px) {
  .media-mcp-form-grid {
    grid-template-columns: 1fr;
  }
}

.mcp-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.mcp-filter-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex: 1;
}
.pill-segmented {
  display: inline-flex;
  background: var(--bg-elevated, #f3f4f6);
  padding: 3px;
  border-radius: 8px;
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
}
.pill-btn {
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-secondary, #6b7280);
  transition: all 0.15s ease;
  white-space: nowrap;
}
.pill-btn.active {
  background: var(--bg-card, #ffffff);
  color: var(--c-profiles, #1f5947);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.filter-dropdown-wrap {
  width: 130px;
}
.filter-search-wrap {
  flex: 0 1 200px;
  min-width: 140px;
}

/* MCP 卡片网格 */
.mcp-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}
.mcp-card {
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--bg-card, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.mcp-card:hover {
  transform: translateY(-2px);
  border-color: var(--c-profiles, rgba(22, 151, 122, 0.45));
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
}
.mcp-card.is-disabled {
  opacity: 0.7;
}
.mcp-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.mcp-tool-heading-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}
.mcp-tool-icon-box {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--bg-elevated, #f3f4f6);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  color: var(--c-profiles, #16977a);
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.mcp-card:hover .mcp-tool-icon-box {
  transform: scale(1.05);
}

/* 领域/分类色彩徽标容器 */
.tool-icon-file {
  color: #10b981;
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.22);
}
.tool-icon-web {
  color: #3b82f6;
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.22);
}
.tool-icon-bash {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.08);
  border-color: rgba(245, 158, 11, 0.22);
}
.tool-icon-plan,
.tool-icon-task {
  color: #8b5cf6;
  background: rgba(139, 92, 246, 0.08);
  border-color: rgba(139, 92, 246, 0.22);
}
.tool-icon-model {
  color: #6366f1;
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.22);
}
.tool-icon-dataset {
  color: #06b6d4;
  background: rgba(6, 182, 212, 0.08);
  border-color: rgba(6, 182, 212, 0.22);
}
.tool-icon-kb {
  color: #14b8a6;
  background: rgba(20, 184, 166, 0.08);
  border-color: rgba(20, 184, 166, 0.22);
}
.tool-icon-report {
  color: #ec4899;
  background: rgba(236, 72, 153, 0.08);
  border-color: rgba(236, 72, 153, 0.22);
}
.tool-icon-dispatch {
  color: #0ea5e9;
  background: rgba(14, 165, 233, 0.08);
  border-color: rgba(14, 165, 233, 0.22);
}
.tool-icon-cases {
  color: #84cc16;
  background: rgba(132, 204, 22, 0.08);
  border-color: rgba(132, 204, 22, 0.22);
}
.tool-icon-image {
  color: #a855f7;
  background: rgba(168, 85, 247, 0.08);
  border-color: rgba(168, 85, 247, 0.22);
}
.tool-icon-audio {
  color: #eab308;
  background: rgba(234, 179, 8, 0.08);
  border-color: rgba(234, 179, 8, 0.22);
}
.tool-icon-other {
  color: var(--c-profiles, #16977a);
  background: var(--t-profiles, rgba(22, 151, 122, 0.08));
  border-color: rgba(22, 151, 122, 0.22);
}

/* 表格列工具图标 */
.mcp-table-tool-col {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mcp-table-tool-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
}
.mcp-table-tool-info {
  min-width: 0;
}

.mcp-tool-heading {
  min-width: 0;
  flex: 1;
}
.mcp-tool-title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.domain-tag {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
}
.mcp-tool-desc {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  line-height: 1.5;
  min-height: 36px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tool-schema-brief {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.05));
  border-radius: 6px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
}
.schema-brief-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.brief-k {
  color: var(--text-tertiary, #9ca3af);
  font-weight: 600;
  flex-shrink: 0;
}
.brief-v {
  color: var(--text-primary, #111827);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.mcp-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
  margin-top: auto;
}

/* 权限与风险等级微标 */
.perm-badge-read {
  color: var(--accent-success, #10b981);
}
.perm-badge-write {
  color: var(--accent-warning, #f59e0b);
}
.perm-badge-network {
  color: #3b82f6;
}
.perm-badge-code {
  color: #f59e0b;
}

/* 外部网关规格卡片 */
.external-gateway-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ext-hero-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 16px;
  background: var(--t-profiles, rgba(22, 151, 122, 0.06));
  border: 1px solid var(--c-profiles, rgba(22, 151, 122, 0.2));
  border-radius: 10px;
  flex-wrap: wrap;
}
.ext-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  margin-bottom: 4px;
}
.ext-desc {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  line-height: 1.5;
  max-width: 800px;
}
.ext-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}
.ext-card {
  padding: 12px 14px;
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
}
.ext-card-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary, #111827);
  margin-bottom: 6px;
}
.ext-card-content {
  font-size: 11.5px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.6;
}

/* ═══════════════════════════════════════════════════════════════


/* 以下为面板骨架样式：父视图 scoped 样式不会作用到子组件，随组件携带一份。 */
/* 通用面板标题与操作栏 */
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
.panel-actions-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
/* 视图切换按钮 */
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
.panel-section-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  margin-bottom: 4px;
}
/* ═══════════════════════════════════════════════════════════════
   通用辅助类
   ═══════════════════════════════════════════════════════════════ */
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-success, #10b981);
  display: inline-block;
  flex-shrink: 0;
}
.status-dot.is-disabled {
  background: var(--text-tertiary, #9ca3af);
}
.empty-state-wrap {
  grid-column: 1 / -1;
  width: 100%;
}
.btn-xs {
  font-size: 11.5px;
  padding: 3px 8px;
  border-radius: 5px;
}
</style>
