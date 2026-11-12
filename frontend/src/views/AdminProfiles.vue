<template>
  <div class="profiles-page">
    <!-- 顶部 Tab 导航栏 -->
    <div class="tabs-nav-bar">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="profile-tab-btn"
        :class="{ active: activeTab === t.key }"
        @click="switchTab(t.key)"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 1：大模型协议档 (Profiles)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-if="activeTab === 'profiles'">
      <AgentProfilesPanel
        @agent-profile-change="defaultAgentProfile = $event"
        @open-agent-prompt="handleOpenAgentPrompt"
      />
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 2：向量与重排模型 (RAG)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-else-if="activeTab === 'rag_models'">
      <GlobalModelSettings />
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 3：MCP 服务器与工具清单 (MCP)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-else-if="activeTab === 'mcp'">
      <McpToolsPanel />
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 4：Agent 技能编排 (Skills)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-else-if="activeTab === 'skills'">
      <AgentSkillsPanel :agent-profile="defaultAgentProfile" @open-agent-prompt="handleOpenAgentPrompt(defaultAgentProfile)" />
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 5：运行时与主机治理 (Runtime)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-else>
      <RuntimeGovernancePanel />
    </template>

    <!-- 模态弹窗 -->
    <AgentPromptModal
      v-model:show="showAgentPromptModal"
      :profile-id="promptProfile?.id || null"
      :profile-name="promptProfile?.name || ''"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMessage } from 'naive-ui'

import type { Profile } from '../api/types'
import { safeBlur } from '../utils/dom'
import AgentProfilesPanel from '../components/admin/AgentProfilesPanel.vue'
import AgentSkillsPanel from '../components/admin/AgentSkillsPanel.vue'
import GlobalModelSettings from '../components/admin/GlobalModelSettings.vue'
import McpToolsPanel from '../components/admin/McpToolsPanel.vue'
import RuntimeGovernancePanel from '../components/admin/RuntimeGovernancePanel.vue'
import AgentPromptModal from '../components/modals/AgentPromptModal.vue'

const message = useMessage()

// 5 Tab 架构：profiles / rag_models / mcp / skills / runtime
type TabKey = 'profiles' | 'rag_models' | 'mcp' | 'skills' | 'runtime'
// 提示词弹窗与默认 Agent 协议档：协议档面板通过事件回传，技能面板复用同一份。
const showAgentPromptModal = ref(false)
const promptProfile = ref<Profile | null>(null)
const defaultAgentProfile = ref<Profile | null>(null)

function handleOpenAgentPrompt(profile: Profile | null) {
  if (!profile) {
    message.warning('请先指定 Agent 协议档')
    return
  }
  safeBlur()
  promptProfile.value = profile
  showAgentPromptModal.value = true
}

const tabs: { key: TabKey; label: string }[] = [
  { key: 'profiles', label: '模型协议档' },
  { key: 'rag_models', label: '向量与重排 (RAG)' },
  { key: 'mcp', label: 'MCP 与工具' },
  { key: 'skills', label: 'Agent 技能' },
  { key: 'runtime', label: '运行时治理' },
]
const activeTab = ref<TabKey>('profiles')

/** 切换 Tab：各面板自行加载数据，这里只切换视图。 */
function switchTab(key: TabKey) {
  activeTab.value = key
}

// ═══════════════════════════════════════════════════════════════
// 运行时治理
// ═══════════════════════════════════════════════════════════════

</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   全局页面骨架与自适应容器
   ═══════════════════════════════════════════════════════════════ */
.profiles-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

/* 导航 Tabs */
.tabs-nav-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  overflow-x: auto;
  white-space: nowrap;
  padding: 4px;
  background: var(--bg-card, #ffffff);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 10px;
  box-sizing: border-box;
  -webkit-overflow-scrolling: touch;
}
.tabs-nav-bar::-webkit-scrollbar {
  height: 0;
}
.profile-tab-btn {
  padding: 8px 16px;
  border-radius: 7px;
  border: none;
  background: transparent;
  color: var(--text-secondary, #6b7280);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
  white-space: nowrap;
}
.profile-tab-btn:hover {
  color: var(--text-primary, #111827);
  background: var(--bg-elevated, rgba(0, 0, 0, 0.03));
}
.profile-tab-btn.active {
  background: var(--t-profiles, rgba(22, 151, 122, 0.1));
  color: var(--c-profiles, #1f5947);
  font-weight: 600;
}

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

/* ═══════════════════════════════════════════════════════════════
   Tab 2：向量与重排模型 (RAG)
   ═══════════════════════════════════════════════════════════════ */
.rag-models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
}
.rag-model-card {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.rag-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
}
.rag-type-pill {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #111827);
}
.rag-model-sub {
  font-size: 11.5px;
  color: var(--text-tertiary, #9ca3af);
}
.key-status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 500;
}
.key-status-badge.ok {
  background: rgba(16, 185, 129, 0.1);
  color: var(--accent-success, #10b981);
}
.key-status-badge.none {
  background: var(--bg-card, #ffffff);
  color: var(--text-tertiary, #9ca3af);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
}
.rag-check-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
}
.rag-check-feedback {
  font-size: 11.5px;
}
.rag-check-feedback.success {
  color: var(--accent-success, #10b981);
  font-weight: 500;
}
.rag-check-feedback.fail {
  color: var(--accent-error, #ef4444);
}

/* ═══════════════════════════════════════════════════════════════
   MCP 面板迁移后仍被其它 Tab 复用的规则
   ═══════════════════════════════════════════════════════════════ */
.media-mcp-form-grid .runtime-field {
  width: auto;
}
.filter-search-wrap {
  flex: 0 1 200px;
  min-width: 140px;
}

/* ═══════════════════════════════════════════════════════════════
/* ═══════════════════════════════════════════════════════════════
   Tab 5：运行时治理（面板已拆分，保留其它 Tab 复用的规则）
   ═══════════════════════════════════════════════════════════════ */
.panel-section-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  margin-bottom: 4px;
}
.runtime-field .field-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-primary, #111827);
}
.runtime-field .field-hint {
  font-size: 11px;
  color: var(--text-tertiary, #9ca3af);
  margin-top: 2px;
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
.btn-xs {
  font-size: 11.5px;
  padding: 3px 8px;
  border-radius: 5px;
}
.link-btn.small {
  font-size: 12px;
}
</style>
