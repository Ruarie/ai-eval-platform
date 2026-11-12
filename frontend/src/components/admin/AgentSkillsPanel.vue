<template>
  <div class="skills-center-container">
    <!-- 顶部操作栏 -->
    <div class="panel">
      <div class="panel-header-row">
        <div class="panel-title-area">
          <span class="panel-title-text">Agent 技能编排</span>
          <span class="tag-soft">统一 SKILL.md · 内置技能与专家角色</span>
        </div>

        <div class="panel-actions-area">
          <button
            class="btn btn-secondary btn-sm"
            @click="handleExportSkillsJson"
          >
            导出配置
          </button>
          <button
            class="btn btn-sign btn-sm"
            :disabled="!agentProfile"
            :title="agentProfile ? `查看或编辑 ${agentProfile.name} 的补充提示词` : '请先在大模型协议档页指定 Agent 协议档'"
            @click="emit('open-agent-prompt')"
          >
            Agent 提示词
          </button>
        </div>
      </div>
    </div>

    <!-- 技能列表 -->
    <div class="panel">
      <div class="skills-toolbar">
        <div class="skills-filter-group">
          <div class="filter-search-wrap">
            <n-input
              v-model:value="skillSearchKeyword"
              size="small"
              placeholder="搜索技能名称、类型或说明…"
              clearable
            />
          </div>
        </div>

        <div class="view-mode-toggle">
          <button
            class="toggle-btn"
            :class="{ active: skillViewMode === 'cards' }"
            @click="skillViewMode = 'cards'"
          >
            卡片
          </button>
          <button
            class="toggle-btn"
            :class="{ active: skillViewMode === 'table' }"
            @click="skillViewMode = 'table'"
          >
            表格
          </button>
        </div>
      </div>

      <div v-if="skillsLoading" class="expert-prompt-loading">正在读取技能目录…</div>
      <div v-else-if="skillsError" class="expert-prompt-loading error">
        {{ skillsError }}
        <button class="btn btn-secondary btn-sm" @click="loadAgentSkills">重试</button>
      </div>

      <!-- 卡片视图：字段只来自 GET /api/admin/skills 的轻量目录 -->
      <div v-else-if="skillViewMode === 'cards'" class="skills-cards-grid mt16">
        <div
          v-for="s in filteredSkills"
          :key="s.id"
          class="skill-card-v2"
        >
          <div class="skill-card-top">
            <div class="skill-card-heading">
              <div class="skill-card-name">{{ s.name }}</div>
              <div class="skill-scenario-tag">{{ skillKindLabel(s.kind) }}</div>
            </div>
            <span class="tag-soft">{{ s.enabled ? '已启用' : '已停用' }}</span>
          </div>

          <div class="skill-card-desc">{{ s.summary }}</div>

          <div class="skill-tuning-chips">
            <div class="tuning-chip">
              <span class="tuning-k">版本</span>
              <span class="tuning-v mono">{{ s.version }}</span>
            </div>
            <div class="tuning-chip">
              <span class="tuning-k">标识</span>
              <span class="tuning-v mono">{{ s.id }}</span>
            </div>
          </div>

          <div class="skill-card-bottom">
            <span class="small tertiary mono">SKILL.md</span>
            <div class="row" style="gap: 6px">
              <button class="btn btn-secondary btn-xs" @click="handleOpenSkillModal(s)">目录详情</button>
              <button class="btn btn-sign btn-xs" @click="handleOpenSkillFile(s)">预览 / 编辑</button>
            </div>
          </div>
        </div>

        <div v-if="filteredSkills.length === 0" class="empty-state-wrap">
          <EmptyState title="未找到匹配的 Agent 技能" description="请尝试清空搜索条件，或确认运行时技能目录可读" />
        </div>
      </div>

      <!-- 表格视图 -->
      <div v-else class="profile-table-scroll mt16">
        <table class="ds-table">
          <thead>
            <tr>
              <th style="width: 180px">技能名称</th>
              <th style="width: 120px">类型</th>
              <th>说明</th>
              <th style="width: 90px">版本</th>
              <th style="width: 90px">状态</th>
              <th style="width: 120px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in filteredSkills" :key="s.id">
              <td>
                <div style="font-weight: 600; font-size: 13px">{{ s.name }}</div>
                <div class="mono small tertiary" style="font-size: 10px">{{ s.id }}</div>
              </td>
              <td><span class="tag-soft">{{ skillKindLabel(s.kind) }}</span></td>
              <td class="small" style="color: var(--text-primary)">{{ s.summary }}</td>
              <td class="mono small">{{ s.version }}</td>
              <td>
                <span class="badge" :class="s.enabled ? 'badge-succeeded' : 'badge-cancelled'">
                  {{ s.enabled ? '已启用' : '已停用' }}
                </span>
              </td>
              <td style="text-align: right">
                <div class="row" style="justify-content: flex-end; gap: 4px">
                  <button class="link-btn small" @click="handleOpenSkillModal(s)">详情</button>
                  <button class="link-btn small" @click="handleOpenSkillFile(s)">编辑</button>
                </div>
              </td>
            </tr>

            <tr v-if="filteredSkills.length === 0">
              <td colspan="6">
                <EmptyState title="未找到匹配的 Agent 技能" description="请尝试清空搜索条件，或确认运行时技能目录可读" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 专家提示词与技能文件分区展示，避免把角色工作方法混入 SKILL.md。 -->
    <div class="panel expert-prompt-panel">
      <div class="panel-header-row">
        <div class="panel-title-area">
          <span class="panel-title-text">专家提示词</span>
          <span class="tag-soft">按专家角色生效 · {{ expertPromptItems.length }} 位专家</span>
        </div>
        <div class="small tertiary">编辑后从下一个会话回合开始生效</div>
      </div>

      <div v-if="expertPromptsLoading" class="expert-prompt-loading">正在读取专家目录…</div>
      <div v-else-if="expertPromptsError" class="expert-prompt-loading error">
        {{ expertPromptsError }}
        <button class="btn btn-secondary btn-sm" @click="loadExpertPromptMetadata">重试</button>
      </div>
      <div v-else class="expert-prompt-grid mt16">
        <article v-for="expert in expertPromptItems" :key="expert.id" class="expert-prompt-card">
          <div class="skill-card-top">
            <div class="skill-card-heading">
              <div class="skill-card-name">{{ expert.name }}</div>
              <div class="skill-scenario-tag">{{ expert.badge }} · {{ expert.id }}</div>
            </div>
            <span class="tag-soft" :class="{ 'expert-overridden': expert.overridden }">
              {{ expert.overridden ? '已定制' : expert.prompt_available ? '内置基线' : '无附加提示词' }}
            </span>
          </div>
          <div class="skill-card-desc expert-prompt-desc">{{ expert.description }}</div>
          <div class="expert-prompt-card-bottom">
            <span class="small tertiary">{{ expert.prompt_available ? '可查看与编辑专家工作方法' : '默认角色沿用平台核心提示词' }}</span>
            <button
              class="btn btn-sign btn-xs"
              :disabled="!expert.prompt_available"
              :title="expert.prompt_available ? `查看或编辑 ${expert.name} 的提示词` : '该默认角色没有额外专家提示词'"
              @click="handleOpenExpertPrompt(expert)"
            >
              {{ expert.prompt_available ? '查看 / 编辑' : '无需配置' }}
            </button>
          </div>
        </article>
      </div>
    </div>
  </div>

  <!-- 技能相关弹窗随面板迁移，父视图只保留协议档弹窗。 -->
  <SkillDetailModal v-model:show="showSkillModal" :skill="selectedSkill" />
  <AgentSkillFileModal
    v-model:show="showSkillFileModal"
    :skill-id="selectedSkillFileId"
    @saved="handleSkillFileSaved"
  />
  <AgentExpertPromptModal
    v-model:show="showExpertPromptModal"
    :expert-id="selectedExpertPrompt?.id || null"
    :expert-name="selectedExpertPrompt?.name || ''"
    @saved="handleExpertPromptSaved"
  />
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'

import { api } from '../../api/http'
import type {
  AgentExpertPromptDocument,
  AgentExpertPromptMetadata,
  AgentSkillDocument,
  AgentSkillMetadata,
  Profile,
} from '../../api/types'
import { skillKindLabel } from '../../agent/skillLabels'
import { safeBlur } from '../../utils/dom'
import EmptyState from '../common/EmptyState.vue'
import AgentExpertPromptModal from '../modals/AgentExpertPromptModal.vue'
import AgentSkillFileModal from '../modals/AgentSkillFileModal.vue'
import SkillDetailModal from '../modals/SkillDetailModal.vue'

defineProps<{ agentProfile: Profile | null }>()
const emit = defineEmits<{ (event: 'open-agent-prompt'): void }>()

const message = useMessage()

// ═══════════════════════════════════════════════════════════════
// Agent 技能编排 (Skills & Prompts)
// ═══════════════════════════════════════════════════════════════
const skillViewMode = ref<'cards' | 'table'>('cards')
const skillSearchKeyword = ref('')
const skillItems = ref<AgentSkillMetadata[]>([])
const skillsLoading = ref(false)
const skillsError = ref('')
const selectedSkill = ref<AgentSkillMetadata | null>(null)
let skillCatalogRequest = 0
const showSkillModal = ref(false)
const selectedSkillFileId = ref<string | null>(null)
const showSkillFileModal = ref(false)
const expertPromptItems = ref<AgentExpertPromptMetadata[]>([])
const expertPromptsLoading = ref(false)
const expertPromptsError = ref('')
const selectedExpertPrompt = ref<AgentExpertPromptMetadata | null>(null)
const showExpertPromptModal = ref(false)
let expertPromptRequest = 0

const filteredSkills = computed(() => {
  const keyword = skillSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return skillItems.value
  return skillItems.value.filter((skill) => {
    const kind = `${skill.kind} ${skillKindLabel(skill.kind)}`.toLowerCase()
    return skill.name.toLowerCase().includes(keyword)
      || skill.id.toLowerCase().includes(keyword)
      || skill.summary.toLowerCase().includes(keyword)
      || kind.includes(keyword)
  })
})

/** 打开技能页时读取目录头部，不把工作流正文留在列表状态里。 */
async function loadAgentSkills() {
  const request = ++skillCatalogRequest
  skillsLoading.value = true
  skillsError.value = ''
  try {
    const items = await api.admin.listAgentSkills()
    if (request === skillCatalogRequest) skillItems.value = items
  } catch (error: any) {
    if (request !== skillCatalogRequest) return
    skillItems.value = []
    skillsError.value = error?.message || '技能目录读取失败'
  } finally {
    if (request === skillCatalogRequest) skillsLoading.value = false
  }
}

function handleOpenSkillModal(skill: AgentSkillMetadata) {
  safeBlur()
  selectedSkill.value = skill
  showSkillModal.value = true
}

function handleOpenSkillFile(skill: AgentSkillMetadata) {
  safeBlur()
  selectedSkillFileId.value = skill.id
  showSkillFileModal.value = true
}

/** 保存后用文件头部回写卡片，避免列表仍显示旧的启用状态或摘要。 */
function handleSkillFileSaved(saved: AgentSkillDocument) {
  const metadata = saved.metadata
  skillItems.value = skillItems.value.map((item) => (item.id === metadata.id ? metadata : item))
  if (selectedSkill.value?.id === metadata.id) selectedSkill.value = metadata
}

/** 仅在打开 Agent 技能页时读取专家目录，列表不携带任何提示词正文。 */
async function loadExpertPromptMetadata() {
  const request = ++expertPromptRequest
  expertPromptsLoading.value = true
  expertPromptsError.value = ''
  try {
    const items = await api.admin.listAgentExpertPrompts()
    if (request === expertPromptRequest) expertPromptItems.value = items
  } catch (error: any) {
    if (request !== expertPromptRequest) return
    expertPromptItems.value = []
    expertPromptsError.value = error?.message || '专家目录读取失败'
  } finally {
    if (request === expertPromptRequest) expertPromptsLoading.value = false
  }
}

/** 只有声明专属提示词的专家才开放预览与编辑，默认角色不产生额外人格层。 */
function handleOpenExpertPrompt(expert: AgentExpertPromptMetadata) {
  if (!expert.prompt_available) return
  safeBlur()
  selectedExpertPrompt.value = expert
  showExpertPromptModal.value = true
}

/** 保存成功后仅回写目录状态，不把提示词正文保留在技能页状态中。 */
function handleExpertPromptSaved(document: AgentExpertPromptDocument) {
  // 保存结果比先前发起的目录读取更新，禁止迟到快照覆盖已定制状态。
  expertPromptRequest += 1
  expertPromptsLoading.value = false
  expertPromptsError.value = ''
  expertPromptItems.value = expertPromptItems.value.map((item) => (
    item.id === document.expert_id ? { ...item, overridden: document.overridden } : item
  ))
}

/** 导出当前已加载的技能目录，不包含工作流正文。 */
async function handleExportSkillsJson() {
  safeBlur()
  if (skillsLoading.value) {
    message.info('技能目录仍在读取')
    return
  }
  if (!skillItems.value.length) {
    message.info('当前没有可导出的技能目录')
    return
  }
  try {
    const payload = JSON.stringify(skillItems.value, null, 2)
    await navigator.clipboard.writeText(payload)
    message.success('已复制技能配置 JSON')
  } catch {
    message.info('请在安全上下文中复制配置')
  }
}

onMounted(() => {
  loadAgentSkills()
  loadExpertPromptMetadata()
})
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   Agent 技能编排
   ═══════════════════════════════════════════════════════════════ */
.skills-center-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.skills-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.skills-filter-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  flex: 1;
}
.skills-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.skill-card-v2 {
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-card, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.skill-card-v2:hover {
  transform: translateY(-2px);
  border-color: var(--c-profiles, rgba(22, 151, 122, 0.45));
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
}
.skill-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}
.skill-card-heading {
  min-width: 0;
  flex: 1;
}
.skill-card-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #111827);
}
.skill-scenario-tag {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  margin-top: 2px;
}
.skill-card-desc {
  font-size: 12px;
  color: var(--text-secondary, #4b5563);
  line-height: 1.5;
  min-height: 36px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.skill-tuning-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.tuning-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: var(--bg-elevated, #f3f4f6);
  border-radius: 4px;
  font-size: 10.5px;
}
.tuning-k {
  color: var(--text-tertiary, #9ca3af);
}
.tuning-v {
  color: var(--c-profiles, #1f5947);
  font-weight: 600;
}
.skill-cmds-row,
.skill-tools-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}
.cmd-label,
.tools-label {
  color: var(--text-tertiary, #9ca3af);
  flex-shrink: 0;
}
.cmd-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--t-profiles, rgba(22, 151, 122, 0.08));
  color: var(--c-profiles, #1f5947);
}
.tool-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--bg-elevated, #f3f4f6);
  color: var(--text-secondary, #4b5563);
}
.skill-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
  margin-top: auto;
}
.expert-prompt-panel {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.expert-prompt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}
.expert-prompt-card {
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 16px;
  background: var(--bg-card, #ffffff);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.expert-prompt-desc {
  min-height: 36px;
}
.expert-prompt-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
  margin-top: auto;
}
.expert-overridden {
  color: var(--c-profiles, #1f5947);
  background: var(--t-profiles, rgba(22, 151, 122, 0.1));
}
.expert-prompt-loading {
  padding: 28px 16px;
  text-align: center;
  color: var(--text-secondary, #6b7280);
}
.expert-prompt-loading.error {
  color: var(--accent-error, #dc2626);
}

/* ═══════════════════════════════════════════════════════════════

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
.profile-table-scroll {
  overflow-x: auto;
  width: 100%;
  -webkit-overflow-scrolling: touch;
}
.profile-table-scroll table {
  min-width: 900px;
  width: 100%;
}
.filter-search-wrap {
  flex: 0 1 200px;
  min-width: 140px;
}
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
</style>
