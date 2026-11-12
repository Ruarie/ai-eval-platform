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
                    <button v-if="p.usages?.includes('agent')" class="link-btn small" @click="handleOpenAgentPrompt(p)">提示词</button>
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
                    <button v-if="p.usages?.includes('agent')" class="link-btn small" @click="handleOpenAgentPrompt(p)">提示词</button>
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
                :disabled="!selectedAgentProfile"
                :title="selectedAgentProfile ? `查看或编辑 ${selectedAgentProfile.name} 的补充提示词` : '请先在大模型协议档页指定 Agent 协议档'"
                @click="handleOpenAgentPrompt()"
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
    </template>

    <!-- ═══════════════════════════════════════════════════════════════
         Tab 5：运行时与主机治理 (Runtime)
         ═══════════════════════════════════════════════════════════════ -->
    <template v-else>
      <div class="panel runtime-governance-panel">
        <!-- 1. 会话与连接参数 -->
        <div class="runtime-section">
          <div class="panel-section-title">WebSocket 会话与连接参数</div>
          <div class="runtime-form-row mt10">
            <div class="runtime-field">
              <label class="field-label">心跳 Ping 间隔 (秒)</label>
              <n-input-number v-model:value="runtimeForm.ws_ping_s" :min="5" :max="300" style="width: 100%" />
            </div>
            <div class="runtime-field">
              <label class="field-label">连接超时断开 (秒)</label>
              <n-input-number v-model:value="runtimeForm.ws_timeout_s" :min="5" :max="300" style="width: 100%" />
            </div>
            <div class="runtime-field">
              <label class="field-label">WS Ticket 授权 TTL (秒)</label>
              <n-input-number :value="300" disabled style="width: 100%" />
              <span class="field-hint">一次性授权票据，固定 5 分钟 (PRD §5.1)</span>
            </div>
          </div>
        </div>

        <div class="runtime-divider"></div>

        <!-- 2. 会话互斥与长任务槽位 -->
        <div class="runtime-section">
          <div class="panel-section-title">会话占槽与并发互斥规则</div>
          <div class="small tertiary mt2 mb10">
            当前会话有进行中任务（含压测子任务）时，主按钮自动禁用，完成后方可开启新长任务 (PRD §3.4)。
          </div>
          <label class="row" style="gap: 10px; align-items: center; cursor: pointer">
            <n-switch v-model:value="runtimeForm.strict_session_slot" />
            <span style="font-weight: 600; font-size: 13.5px">严格会话占槽互斥：压测等长任务执行期间保持槽位独占</span>
          </label>
        </div>

        <div class="runtime-divider"></div>

        <!-- 3. 安全权限等级 -->
        <div class="runtime-section">
          <div class="panel-section-title">全局默认权限等级</div>
          <div class="small tertiary mt2 mb10">
            控制 Agent 会话执行写操作、联网与命令调用的授权策略；单会话可在此基础上自定义调整。
          </div>
          <div class="runtime-tier-select-wrap">
            <n-select
              v-model:value="runtimeForm.permission_tier_default"
              :options="permissionTierOptions"
              style="width: 380px; max-width: 100%;"
            />
          </div>
        </div>

        <div class="runtime-footer mt20">
          <button
            class="btn btn-primary btn-sm"
            :disabled="runtimeSaving"
            @click="saveRuntime"
          >
            {{ runtimeSaving ? '保存中…' : '保存运行时治理参数' }}
          </button>
        </div>
      </div>
    </template>

    <!-- 模态弹窗 -->
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

    <SkillDetailModal
      v-model:show="showSkillModal"
      :skill="selectedSkill"
    />

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

    <AgentPromptModal
      v-model:show="showAgentPromptModal"
      :profile-id="promptProfile?.id || null"
      :profile-name="promptProfile?.name || ''"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage, useDialog, NSelect, NInput, NInputNumber, NSwitch } from 'naive-ui'
import { api } from '../api/http'
import type {
  AgentExpertPromptDocument,
  AgentExpertPromptMetadata,
  AgentSkillDocument,
  AgentSkillMetadata,
  Profile,
  ProfileCheckOut,
} from '../api/types'
import EmptyState from '../components/common/EmptyState.vue'
import { safeBlur } from '../utils/dom'
import GlobalModelSettings from '../components/admin/GlobalModelSettings.vue'
import McpToolsPanel from '../components/admin/McpToolsPanel.vue'
import ProviderLogo, { type ProviderLogoKey } from '../components/ProviderLogo.vue'
import { getModelLogoKey } from '../utils/providerLogo'
import { PROFILE_VENDORS, getProfileVendor } from '../utils/profileVendors'
import ProfileModal from '../components/modals/ProfileModal.vue'
import CheckResultModal from '../components/modals/CheckResultModal.vue'
import SkillDetailModal from '../components/modals/SkillDetailModal.vue'
import { skillKindLabel } from '../agent/skillLabels'
import AgentSkillFileModal from '../components/modals/AgentSkillFileModal.vue'
import AgentExpertPromptModal from '../components/modals/AgentExpertPromptModal.vue'
import AgentPromptModal from '../components/modals/AgentPromptModal.vue'

const message = useMessage()
const dialog = useDialog()

// 5 Tab 架构：profiles / rag_models / mcp / skills / runtime
type TabKey = 'profiles' | 'rag_models' | 'mcp' | 'skills' | 'runtime'
const tabs: { key: TabKey; label: string }[] = [
  { key: 'profiles', label: '模型协议档' },
  { key: 'rag_models', label: '向量与重排 (RAG)' },
  { key: 'mcp', label: 'MCP 与工具' },
  { key: 'skills', label: 'Agent 技能' },
  { key: 'runtime', label: '运行时治理' },
]
const activeTab = ref<TabKey>('profiles')

/** 切换 Tab 时触发对应真实后端接口加载 */
function switchTab(key: TabKey) {
  activeTab.value = key
  if (key === 'profiles') {
    loadProfiles()
  } else if (key === 'skills') {
    loadAgentSkills()
    loadExpertPromptMetadata()
  }
}

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

// ═══════════════════════════════════════════════════════════════
// 运行时治理
// ═══════════════════════════════════════════════════════════════
const runtimeForm = ref({
  ws_ping_s: 15,
  ws_timeout_s: 45,
  strict_session_slot: true,
  permission_tier_default: 'tier1',
})
const runtimeSaving = ref(false)

const permissionTierOptions = [
  { label: '档1 请求批准（每次写操作与命令需逐次确认）', value: 'tier1' },
  { label: '档2 帮我批准（工作区写入自动，破坏性命令需确认）', value: 'tier2' },
  { label: '档3 完全访问（全部自动，灾难性命令一律拦截）', value: 'tier3' },
]

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
const showAgentPromptModal = ref(false)
const promptProfile = ref<Profile | null>(null)
const selectedAgentProfile = computed(() => (
  profiles.value.find((profile) => profile.id === selectedAgentProfileId.value) || null
))

function handleOpenAgentPrompt(profile?: Profile) {
  const target = profile || selectedAgentProfile.value
  if (!target) {
    message.warning('请先指定 Agent 协议档')
    return
  }
  safeBlur()
  promptProfile.value = target
  showAgentPromptModal.value = true
}

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
      if (settings?.runtime) runtimeForm.value = { ...runtimeForm.value, ...settings.runtime }
      if (settings?.permission_tier_default) {
        runtimeForm.value.permission_tier_default = settings.permission_tier_default
      }
    }
  } catch (err: any) {
    message.error(err.message || '加载配置失败')
  } finally {
    loading.value = false
  }
}

async function saveRuntime() {
  runtimeSaving.value = true
  try {
    await api.admin.updateSettings({
      runtime: {
        ws_ping_s: runtimeForm.value.ws_ping_s,
        ws_timeout_s: runtimeForm.value.ws_timeout_s,
        strict_session_slot: runtimeForm.value.strict_session_slot,
      },
      permission_tier_default: runtimeForm.value.permission_tier_default,
    } as any)
    message.success('运行时治理参数已更新')
  } catch (err: any) {
    message.error(err.message || '运行时参数保存失败')
  } finally {
    runtimeSaving.value = false
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

onMounted(() => {
  loadProfiles()
})
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
.media-mcp-form-grid .runtime-field {
  width: auto;
}
.filter-search-wrap {
  flex: 0 1 200px;
  min-width: 140px;
}

   Tab 4：Agent 技能编排
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
   Tab 5：运行时治理
   ═══════════════════════════════════════════════════════════════ */
.runtime-governance-panel {
  padding: 22px 26px;
  display: flex;
  flex-direction: column;
}
.panel-section-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  margin-bottom: 4px;
}
.runtime-section {
  display: flex;
  flex-direction: column;
}
.runtime-divider {
  height: 1px;
  background: var(--border-subtle, rgba(0, 0, 0, 0.06));
  margin: 20px 0;
}
.runtime-form-row {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  flex-wrap: wrap;
}
.runtime-field {
  width: 240px;
  display: flex;
  flex-direction: column;
  gap: 4px;
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
.runtime-tier-select-wrap {
  max-width: 380px;
}
.runtime-footer {
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
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
.link-btn.small {
  font-size: 12px;
}
</style>
