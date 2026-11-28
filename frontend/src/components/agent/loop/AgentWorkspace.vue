<template>
  <div class="loop-workspace">
    <header class="loop-toolbar">
      <div class="loop-session-heading"><slot name="session-heading" /></div>
      <div class="loop-tabs">
        <div class="workspace-tab-group" role="group" aria-label="会话视图">
          <button class="workspace-tab" type="button" :class="{active:tab==='chat'}" :aria-pressed="tab==='chat'" @click="tab='chat'">对话</button>
          <button class="workspace-tab" type="button" :class="{active:tab==='trace'}" :aria-pressed="tab==='trace'" :disabled="!state" @click="tab='trace'">
            轨迹 <small v-if="state?.cursor" class="trace-tab-count" aria-hidden="true">{{ state.cursor }}</small>
          </button>
        </div>
        <div class="loop-tabs-actions">
          <slot name="session-actions" />
          <span v-if="sessionId" class="loop-status" role="status">
            <i :class="{running:busy}" aria-hidden="true" />{{ status }}
          </span>
          <button ref="runtimeButton" class="loop-runtime-btn" type="button" :aria-expanded="runtimeOpen" aria-controls="agent-runtime-panel" @click="toggleRuntime">运行信息</button>
        </div>
      </div>
    </header>
    <p v-if="connectionState && connectionState.connection !== 'online'" class="loop-notice" role="status">{{ connectionState.connection === 'connecting' ? '正在同步会话…' : '连接中断，状态待同步。' }}<button @click="store.clients.get(sessionId)?.connect()">重新连接</button></p>
    <p v-if="connectionState?.error || error" class="loop-notice error" role="alert">{{ connectionState?.error || error }}</p>
    <CollaborationPanel v-if="sessionId" :session-id="sessionId" :can-control="canControl" />
    <div class="loop-content">
      <div ref="chatCenter" class="loop-center">
        <section v-if="tab==='chat'" ref="chatShell" class="loop-chat-shell" :class="{ 'is-resizing': isResizing, 'is-empty': !rows.length, 'has-interaction': !!activeInteractionDrawer }" :style="chatShellStyle" aria-label="对话内容区域" :aria-busy="restoringConversation">
          <div v-if="showEmptyPrompts" class="loop-empty-hero">
            <h1 class="hero-tagline">准备测试什么？</h1>
            <p class="hero-subline">描述测试目标，或上传需求文档让 Agent 起草用例。</p>
          </div>
          <p v-else-if="restoringConversation" class="loop-loading" role="status">正在读取会话记录…</p>

          <!-- 对话消息滚动区：有消息时正常滚动展示；空状态隐藏以保持居中 -->
          <div ref="scroller" class="loop-conversation" :class="{ 'is-empty': !rows.length }" role="log" aria-label="对话消息" @scroll="trackScroll">
          <button v-if="shown < rows.length" class="history-more" @click="shown+=80">显示更早的 {{ Math.min(80, rows.length-shown) }} 条记录</button>
          <template v-for="row in visibleRows" :key="row.key">
            <article v-if="row.role==='user'" class="loop-message user"><header>你</header><div class="history-files"><AttachmentPreview v-for="file in attachments[row.key] || []" :key="file.file_id" :attachment="file"/></div><p>{{ row.content }}</p></article>
            <section v-else-if="'status' in row && 'name' in row && isTaskTool((row as ToolRun).name)" class="turn-process-tool">
              <p class="turn-segment-label process">执行过程 · 工具调用</p>
              <TaskRunCard :tool="row as ToolRun" :task="taskForTool(row as ToolRun)" :interactions="interactions(row)" :can-control="canControl" :online="!!state?.ready" @respond="respond"/>
            </section>
            <!-- task 成功由看板展示；非成功终态保留结果卡，避免更新失败后无处查看原因。 -->
            <section v-else-if="'status' in row && 'name' in row && ((row as ToolRun).name !== 'task' || ((row as ToolRun).event === 'tool.result' && (row as ToolRun).status !== 'succeeded'))" class="turn-process-tool">
              <p class="turn-segment-label process">执行过程 · 工具调用</p>
              <ToolRunCard :tool="row as ToolRun" :interactions="interactions(row)" :can-control="canControl" :online="!!state?.ready" @respond="respond"/>
            </section>
            <!-- task 工具由任务规划看板展示，不能落入助手分支生成虚假的响应占位。 -->
            <template v-else-if="!('status' in row && 'name' in row)">
              <!-- 媒体产物按轮次紧邻最终总结展示，避免图片或视频被折叠在执行过程卡中。 -->
              <section v-if="isSummaryAssistantRow(row) && mediaPreviewsForSummary(row.key).length" class="turn-media-results" aria-label="本轮生成结果">
                <p class="turn-segment-label summary">生成结果</p>
                <MediaResultPreview v-for="(preview, index) in mediaPreviewsForSummary(row.key)" :key="`${preview.kind}:${preview.upstreamTaskId || preview.videoUrl || preview.imageUrls.join(',')}:${index}`" :preview="preview"/>
              </section>
              <article class="loop-message assistant" :class="{ 'is-continuation': !isFirstAssistantInTurn(row), 'is-process': isProcessAssistantRow(row), 'is-turn-summary': isSummaryAssistantRow(row) }">
                <header v-if="isFirstAssistantInTurn(row) || isSummaryAssistantRow(row) || isProcessAssistantRow(row)" class="assistant-header">
                  <div class="assistant-identity">
                    <template v-if="isFirstAssistantInTurn(row)">
                      <ProviderLogo v-if="row.request_summary?.model" :provider="getModelLogoKey(row.request_summary.model)" :size="18"/>
                      <strong>{{ row.request_summary?.model || '助手' }}</strong>
                      <time v-if="formatTimestamp(row.timestamp)" :datetime="row.timestamp">{{ formatTimestamp(row.timestamp) }}</time>
                      <small v-if="row.request_summary">第 {{ row.correlation.turn ?? '—' }} 轮 · {{ row.request_summary.reasoning_effort }} · step {{ row.correlation.step }}</small>
                    </template>
                    <span v-if="isSummaryAssistantRow(row) && !responseParts(row).some(part => part.phase === 'commentary')" class="turn-segment-label summary">本轮总结</span>
                    <span v-else class="turn-segment-label process">执行过程 · step {{ row.correlation.step ?? '—' }}</span>
                  </div>
                </header>
                <ReasoningBlock v-if="row.reasoning && ui?.permissions.reasoning" :content="row.reasoning" :ended="row.ended" :interrupted="row.interrupted" :summary-mode="row.request_summary?.protocol === 'openai_responses'"/>
                <template v-if="row.text">
                  <section v-for="part in responseParts(row)" :key="part.output_index" :data-response-phase="part.phase || undefined">
                    <p v-if="part.phase === 'commentary'" class="turn-segment-label process">过程说明</p>
                    <p v-else-if="part.phase === 'final_answer' && isSummaryAssistantRow(row) && responseParts(row).some(item => item.phase === 'commentary')" class="turn-segment-label summary">本轮总结</p>
                    <MarkdownView :content="part.text" :file-links="artifactLinks(filesForRow(row))"/>
                  </section>
                </template>
                <p v-else-if="!row.ended" class="muted">正在响应…</p>
                <div v-if="isSummaryAssistantRow(row) && filesForRow(row).length" class="generated-files" aria-label="本轮生成文件">
                  <a v-for="file in filesForRow(row)" :key="file.path" :href="file.url">下载 {{ file.path }}</a>
                </div>
                <small v-if="row.interrupted || row.error_code || row.error_message" class="attempt-error">
                  {{ row.interrupted ? '本次输出已中断' : `${row.error_code ? `[${row.error_code}] ` : ''}${row.error_message || '模型调用未完成'}` }}
                </small>
              </article>
            </template>
            <!-- 总结操作固定置于整轮末尾：复制、重新生成、引用记忆、Token、用时。 -->
            <div v-if="turnSummaryByLastRowKey.get(row.key)" class="turn-end-toolbar" aria-label="本轮总结操作与指标">
              <div class="turn-end-actions">
                <button
                  class="assistant-action"
                  type="button"
                  title="复制回答"
                  aria-label="复制回答"
                  :disabled="!turnSummaryByLastRowKey.get(row.key)!.summaryText"
                  @click="copy(turnSummaryByLastRowKey.get(row.key)!.summaryText)"
                >
                  <n-icon :component="FileIcon" :size="15"/>
                </button>
                <button
                  class="assistant-action"
                  type="button"
                  title="重新生成"
                  aria-label="重新生成"
                  :disabled="busy || draft.submitting || !!draft.pending"
                  @click="regenerate(turnSummaryByLastRowKey.get(row.key)!.summaryRow)"
                >
                  <n-icon :component="RetryIcon" :size="15"/>
                </button>
                <button
                  class="assistant-action"
                  type="button"
                  title="引用为参考记忆"
                  aria-label="引用为参考记忆"
                  :disabled="!turnSummaryByLastRowKey.get(row.key)!.summaryText"
                  @click="quoteMemory(turnSummaryByLastRowKey.get(row.key)!.summaryText)"
                >
                  <n-icon :component="BackwardIcon" :size="15"/>
                </button>
              </div>
              <div class="turn-end-metrics assistant-metrics">
                <span v-if="turnSummaryByLastRowKey.get(row.key)!.totalTokens !== null" class="turn-end-metric">
                  <n-icon :component="FileIcon" :size="13"/>
                  {{ formatTokens(turnSummaryByLastRowKey.get(row.key)!.totalTokens) }} token
                </span>
                <span v-if="turnSummaryByLastRowKey.get(row.key)!.totalLatencyMs !== null" class="turn-end-metric">
                  <n-icon :component="TimeIcon" :size="13"/>
                  {{ formatDuration(turnSummaryByLastRowKey.get(row.key)!.totalLatencyMs) }}
                </span>
              </div>
            </div>
          </template>
          <p v-if="!busy && state?.phase && ['max_tokens','max_steps','cancelled','service_restart','interrupted','error'].includes(state.phase)" class="loop-notice">{{ finishLabels[state.phase] }}</p>
          </div>
          <div class="loop-composer-wrap">
            <button v-if="!atBottom && !activeInteractionDrawer" class="jump-bottom" type="button" @click="scrollBottom">↓ 回到最新</button>
            <div class="composer-top-bar" :style="workspacePopoverOpen ? { marginBottom: `${workspacePopoverSpace}px` } : undefined">
              <n-popover
                ref="workspacePopoverRef"
                :show="workspacePopoverOpen"
                trigger="click"
                placement="bottom-start"
                :show-arrow="false"
                :animated="false"
                :flip="false"
                :content-style="{ padding: '0' }"
                class="workspace-popover-layer"
                @update:show="handleWorkspacePopoverVisibility"
              >
                <template #trigger>
                  <button
                    type="button"
                    class="composer-ws-btn"
                    :class="{ 'has-ws': !!activeWorkspaceId, 'is-draft': !sessionId, 'is-open': workspacePopoverOpen }"
                    :title="activeWorkspaceId ? `当前绑定工作区：${activeWorkspaceName}` : '点击选择或新建沙箱工作区（可选）'"
                    aria-haspopup="dialog"
                    :aria-expanded="workspacePopoverOpen"
                  >
                    <span class="ws-btn-folder-icon" aria-hidden="true">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                      </svg>
                    </span>
                    <span class="ws-btn-name">{{ activeWorkspaceId ? activeWorkspaceName : '绑定工作区' }}</span>
                    <span class="ws-btn-arrow" aria-hidden="true">
                      <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 4.5l3 3 3-3" />
                      </svg>
                    </span>
                  </button>
                </template>

                <div v-if="workspacePopoverOpen" ref="workspacePopoverCard" :key="workspacePopoverEpoch" class="ws-popover-card">
                  <header class="ws-popover-header">
                    <div class="ws-popover-title">
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                      </svg>
                      <span>沙箱工作区</span>
                    </div>
                    <span v-if="sessionId" class="ws-popover-badge">已绑定会话</span>
                    <span v-else-if="activeWorkspaceId" class="ws-popover-badge is-active">已预选</span>
                    <span v-else class="ws-popover-badge-draft">可选</span>
                  </header>

                  <p v-if="sessionId" class="ws-popover-tip">
                    当前会话已绑定此工作区{{ activeWorkspaceName ? `「${activeWorkspaceName}」` : '' }}，创建后不可更改。如需切换工作区，请新建会话。
                  </p>
                  <p v-else class="ws-popover-tip">
                    选择绑定的沙箱工作区（可选）。绑定后模型的文件读写与终端命令将在此工作区内隔离执行。
                  </p>

                  <template v-if="!sessionId">
                    <div v-if="loadingWorkspaces" class="ws-popover-loading">加载工作区中…</div>
                    <div v-else class="ws-popover-list">
                      <!-- 选项 1：不绑定工作区（默认沙箱） -->
                      <button
                        type="button"
                        class="ws-popover-item"
                        :class="{ 'is-selected': !activeWorkspaceId }"
                        @click="handleSelectWorkspace(null)"
                      >
                        <span class="ws-item-folder">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <circle cx="12" cy="12" r="10"></circle>
                            <line x1="4.93" y1="4.93" x2="19.07" y2="19.07"></line>
                          </svg>
                        </span>
                        <span class="ws-item-name">不绑定工作区（默认沙箱）</span>
                        <span v-if="!activeWorkspaceId" class="ws-item-check">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </span>
                      </button>

                      <!-- 工作区列表项 -->
                      <button
                        v-for="ws in workspaces"
                        :key="ws.id"
                        type="button"
                        class="ws-popover-item"
                        :class="{ 'is-selected': ws.id === activeWorkspaceId }"
                        @click="handleSelectWorkspace(ws)"
                      >
                        <span class="ws-item-folder">
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                          </svg>
                        </span>
                        <span class="ws-item-name" :title="ws.name">{{ ws.name }}</span>
                        <span v-if="ws.id === activeWorkspaceId" class="ws-item-check">
                          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                          </svg>
                        </span>
                      </button>

                      <div v-if="workspaces.length === 0" class="ws-popover-empty">
                        暂无自定义工作区，可在下方新建
                      </div>
                    </div>

                    <footer class="ws-popover-footer">
                      <input
                        v-model="newWorkspaceName"
                        class="ws-popover-input"
                        placeholder="新建工作区名称…"
                        :disabled="creatingWorkspace"
                        maxlength="80"
                        @keydown.enter.prevent="handleCreateWorkspace"
                      />
                      <button
                        type="button"
                        class="ws-popover-create-btn"
                        :disabled="creatingWorkspace || !newWorkspaceName.trim()"
                        @click="handleCreateWorkspace"
                      >
                        {{ creatingWorkspace ? '创建中…' : '新建' }}
                      </button>
                    </footer>
                  </template>
                </div>
              </n-popover>
            </div>
            <TaskStateDrawer :plan="taskPlan" />
            <!-- 交互抽屉锚定输入框上沿，不参与纵向流，避免长题目把输入框挤出可视区域。 -->
            <div class="composer-anchor">
              <Transition name="composer-interaction">
                <InteractionDrawer
                  v-if="activeInteractionDrawer"
                  :key="activeInteractionDrawer.key"
                  class="composer-interaction-drawer"
                  :interaction="activeInteractionDrawer"
                  :can-control="canControl"
                  :online="!!state?.ready"
                  @respond="respond"
                />
              </Transition>
              <AgentComposer ref="composer" :draft="draft" :ui="ui" :profile="selectedProfile" :profiles="ui?.profiles || []" :effort="effort" :meter="summary?.context_meter" :metrics="conversationMetrics" :busy="busy" :cancelling="!!state?.cancelling" :can-stop="canControl && !!state?.ready && !state?.cancelling" :ready="ready" :agent="selectedAgent" :agents="ui?.agents || []" :permission-tier="sessionTier" @effort="setEffort" @submit="submit" @stop="stop" @retry="retry" @model="selectProfile" @agent="selectAgent" @update-permission-tier="handleTierChange"/>
            </div>
          </div>
          <!-- 空状态时的提示词卡片（位于输入框下方，点击填充草稿） -->
          <div v-if="showEmptyPrompts" class="loop-empty-prompts" role="group" aria-label="常用任务">
            <button
              v-for="prompt in prompts"
              :key="prompt.label"
              class="empty-prompt-card"
              type="button"
              @click="fill(prompt.content)"
            >
              <span class="prompt-icon" aria-hidden="true">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
                  <path :d="prompt.icon" />
                </svg>
              </span>
              <span class="prompt-text">
                <strong>{{ prompt.label }}</strong>
                <span>{{ prompt.description }}</span>
              </span>
              <svg class="prompt-arrow" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M5 12h14m-5-5 5 5-5 5" />
              </svg>
            </button>
          </div>
          <div v-if="canResizeChat" class="loop-width-edge loop-width-edge-left" @pointerenter="previewContentResize('left', $event)" @pointermove="moveContentResizePreview('left', $event)" @pointerleave="hideContentResizePreview('left')">
            <button class="loop-width-handle" :class="{ 'is-visible': hoverResizeEdge === 'left' || (isResizing && resizeEdge === 'left'), 'is-active': isResizing && resizeEdge === 'left' }" :style="resizeHandleStyle('left')" type="button" aria-label="向左拖拽调整对话内容宽度" aria-orientation="vertical" role="separator" :aria-valuemin="minimumChatWidth" :aria-valuemax="maximumChatWidth" :aria-valuenow="Math.round(renderedChatWidth)" @pointerdown="beginContentResize($event, 'left')" @keydown="adjustContentWidthByKey($event, 'left')">
              <span aria-hidden="true"></span>
            </button>
          </div>
          <div v-if="canResizeChat" class="loop-width-edge loop-width-edge-right" @pointerenter="previewContentResize('right', $event)" @pointermove="moveContentResizePreview('right', $event)" @pointerleave="hideContentResizePreview('right')">
            <button class="loop-width-handle" :class="{ 'is-visible': hoverResizeEdge === 'right' || (isResizing && resizeEdge === 'right'), 'is-active': isResizing && resizeEdge === 'right' }" :style="resizeHandleStyle('right')" type="button" aria-label="向右拖拽调整对话内容宽度" aria-orientation="vertical" role="separator" :aria-valuemin="minimumChatWidth" :aria-valuemax="maximumChatWidth" :aria-valuenow="Math.round(renderedChatWidth)" @pointerdown="beginContentResize($event, 'right')" @keydown="adjustContentWidthByKey($event, 'right')">
              <span aria-hidden="true"></span>
            </button>
          </div>
        </section>
        <TraceWorkspace v-else-if="state && trace" :state="state" :trace="trace"/>
      </div>
      <aside v-if="runtimeOpen" id="agent-runtime-panel" class="loop-runtime" aria-labelledby="agent-runtime-title" @keydown.esc.stop="closeRuntime">
        <header class="runtime-heading">
          <h2 id="agent-runtime-title">运行信息</h2>
          <button ref="runtimeClose" class="runtime-close" type="button" aria-label="关闭运行信息" @click="closeRuntime">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="m6 6 12 12M18 6 6 18" />
            </svg>
          </button>
        </header>
        <dl>
          <dt>状态</dt><dd>{{ status }}</dd>
          <dt>会话</dt><dd>{{ sessionId || '未发送的草稿' }}</dd>
          <dt>实际模型</dt><dd>{{ summary?.model || '尚无实际请求' }}</dd>
          <dt>思考档位</dt><dd>{{ summary?.reasoning_effort || '未知' }}</dd>
          <dt>协议档版本</dt><dd>{{ summary?.profile_version || '未知' }}</dd>
        </dl>
        <template v-if="state?.facts.length">
          <h3>最近活动</h3>
          <ul class="runtime-events">
            <li v-for="event in state.facts.slice(-5)" :key="event.cursor">{{ event.type }}</li>
          </ul>
        </template>
        <h3 v-if="tasks.length">后台任务</h3>
        <div v-for="task in tasks" :key="task.key" class="runtime-task">
          <router-link to="/tasks">{{ task.key }}</router-link>
          <p>{{ task.status || '等待状态' }}</p>
          <p v-if="task.progress">{{ JSON.stringify(task.progress) }}</p>
          <router-link v-if="task.report_id" :to="`/reports/${task.report_id}`">查看报告</router-link>
        </div>
        <p v-for="execution in quarantined" :key="execution.key" class="loop-notice">执行范围受限 · {{ execution.reason || '等待对账' }}</p>
      </aside>
    </div>
    <div v-if="tab==='trace'" class="loop-composer-wrap loop-trace-composer" :class="{ 'has-interaction': !!activeInteractionDrawer }">
      <div class="composer-top-bar">
        <button
          type="button"
          class="composer-ws-btn"
          :class="{ 'has-ws': !!activeWorkspaceId, 'is-draft': !sessionId }"
          :title="activeWorkspaceId ? `当前绑定工作区：${activeWorkspaceName}` : '点击选择或新建沙箱工作区（可选）'"
          @click="handleOpenWorkspacePopover"
        >
          <span class="ws-btn-folder-icon" aria-hidden="true">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
            </svg>
          </span>
          <span class="ws-btn-name">{{ activeWorkspaceId ? activeWorkspaceName : '绑定工作区' }}</span>
          <span class="ws-btn-arrow" aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 4.5l3 3 3-3" />
            </svg>
          </span>
        </button>
      </div>
      <TaskStateDrawer :plan="taskPlan" />
      <!-- Trace 面板复用同一输入框锚点，保证交互不会撑高页面。 -->
      <div class="composer-anchor">
        <Transition name="composer-interaction">
          <InteractionDrawer
            v-if="activeInteractionDrawer"
            :key="activeInteractionDrawer.key"
            class="composer-interaction-drawer"
            :interaction="activeInteractionDrawer"
            :can-control="canControl"
            :online="!!state?.ready"
            @respond="respond"
          />
        </Transition>
        <AgentComposer ref="composer" :draft="draft" :ui="ui" :profile="selectedProfile" :profiles="ui?.profiles || []" :effort="effort" :meter="summary?.context_meter" :metrics="conversationMetrics" :busy="busy" :cancelling="!!state?.cancelling" :can-stop="canControl && !!state?.ready && !state?.cancelling" :ready="ready" :agent="selectedAgent" :agents="ui?.agents || []" :permission-tier="sessionTier" @effort="setEffort" @submit="submit" @stop="stop" @retry="retry" @model="selectProfile" @agent="selectAgent" @update-permission-tier="handleTierChange"/>
      </div>
    </div>
    <!-- 页面最底部指标栏：只有开始对话后（rows.length > 0）且有 conversationMetrics 时显示 -->
    <footer v-if="rows.length && conversationMetrics" class="conversation-metrics loop-bottom-metrics" aria-label="会话模型总用量指标">
      <span title="全会话平均 Token 生成速度">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m12 14 4-4"/>
          <path d="M3.34 19a10 10 0 1 1 17.32 0"/>
        </svg>
        生成token速度 {{ formatSpeed(conversationMetrics.outputTokensPerSecond) }}
      </span>
      <span title="全会话 Prompt 缓存命中率">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3"/>
        </svg>
        缓存命中率 {{ formatRate(conversationMetrics.cacheHitRate) }}
      </span>
      <span title="全会话累计输入与输出 Token 统计">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="16" y1="13" x2="8" y2="13"></line>
          <line x1="16" y1="17" x2="8" y2="17"></line>
        </svg>
        输入 {{ formatTokens(conversationMetrics.inputTokens) }} · 输出 {{ formatTokens(conversationMetrics.outputTokens) }}
      </span>
    </footer>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { NIcon, NPopover, useMessage } from 'naive-ui'
import BackwardIcon from 'naive-ui/es/_internal/icons/Backward'
import FileIcon from 'naive-ui/es/_internal/icons/File'
import RetryIcon from 'naive-ui/es/_internal/icons/Retry'
import TimeIcon from 'naive-ui/es/_internal/icons/Time'
import http, { ApiError, api } from '../../../api/http'
import { createAgentUiRefresh } from '../../../agent/loop/uiRefresh'
import { createRequestId } from '../../../utils/requestId'
import type { AttachmentReference, AgentSession } from '../../../api/types'
import type { ConversationMetrics, Data, Effort, InteractionRecord, LoopAgent, LoopProfile, LoopRecord, LoopUi, TaskPlanDisplay, ToolRun } from '../../../api/agentLoopTypes'
import { conversationRows, identity } from '../../../agent/loop/reducer'
import type { LoopStore } from '../../../agent/loop/store'
import { useAuthStore } from '../../../stores/auth'
import { getModelLogoKey } from '../../../utils/providerLogo'
import { copyText } from '../../../utils/clipboard'
import ProviderLogo from '../../ProviderLogo.vue'
import MarkdownView from '../MarkdownView.vue'
import { artifactLinks, responseParts, writtenFiles } from '../../../agent/loop/responsePresentation'
import AttachmentPreview from '../AttachmentPreview.vue'
import CollaborationPanel from './CollaborationPanel.vue'
import AgentComposer from './AgentComposer.vue'
import InteractionDrawer from './InteractionDrawer.vue'
import TaskStateDrawer from './TaskStateDrawer.vue'
import ToolRunCard from './ToolRunCard.vue'
import TaskRunCard from './TaskRunCard.vue'
import ReasoningBlock from './ReasoningBlock.vue'
import TraceWorkspace from './TraceWorkspace.vue'
import MediaResultPreview from './MediaResultPreview.vue'
import { isTaskTool } from '../../../agent/loop/taskPresentation'
import { calculateTurnSummaries, formatDuration, formatTokens, getTurnIdentifier, type TurnSummary } from '../../../agent/loop/turnSummary'
import { mediaPreviewsFor, type MediaPreview } from '../../../agent/loop/mediaPresentation'
import { assistantKeysByTurn, conversationMetricsFrom, effortPreferenceKey, finishLabels, firstAssistantInTurn, latestRequestSummary, phaseStatusText, pickAgent, pickProfile, preferenceKey, taskForToolRow } from '../../../agent/loop/workspaceDerived'

const props = withDefaults(
  defineProps<{
    sessionId: string
    session?: AgentSession | null
    store: LoopStore
    createSession: (workspaceId?: string, preparedTicket?: Promise<string>, permissionTier?: string, initialTitle?: string) => Promise<string>
  }>(),
  {
    session: null
  }
)
const auth = useAuthStore(), tab = ref('chat')
const message = useMessage()
const workspaces = ref<Array<{ id: string; name: string }>>([])
const loadingWorkspaces = ref(false)
const workspacePopoverOpen = ref(false)
const workspacePopoverEpoch = ref(0)
const workspacePopoverRef = ref<{ syncPosition: () => void } | null>(null)
const workspacePopoverCard = ref<HTMLElement | null>(null)
const workspacePopoverSpace = ref(0)
const draftWorkspaceId = ref<string | null>(null)
const draftWorkspaceName = ref<string>('')
const newWorkspaceName = ref('')
const creatingWorkspace = ref(false)

const sessionTier = ref<string>('')
watch(() => props.session?.permission_tier, (value) => { sessionTier.value = value || '' }, { immediate: true })
async function handleTierChange(value: string) {
  sessionTier.value = value || ''
  if (!props.sessionId) return
  const tier = (value || null) as 'tier1' | 'tier2' | 'tier3' | null
  try {
    await api.sessions.updatePermissionTier(props.sessionId, tier)
    message.success('本会话权限档位已更新')
  } catch (err: any) {
    message.error(err?.message || '权限档位更新失败')
  }
}

const activeWorkspaceId = computed<string | null>(() => {
  if (props.sessionId) {
    return props.session?.workspace_id || null
  }
  return draftWorkspaceId.value
})

const activeWorkspaceName = computed<string>(() => {
  if (props.sessionId) {
    return props.session?.workspace_name || (props.session?.workspace_id ? '工作区' : '')
  }
  return draftWorkspaceName.value || (draftWorkspaceId.value ? '工作区' : '')
})

async function loadWorkspaces(autoSelect = true) {
  if (loadingWorkspaces.value) return
  loadingWorkspaces.value = true
  try {
    const payload = await api.workspaces.list()
    const items = Array.isArray(payload) ? payload : (payload as any)?.items || []
    workspaces.value = items.map((item: any) => ({
      id: String(item.id),
      name: String(item.name)
    }))
    if (!props.sessionId && !draftWorkspaceId.value && workspaces.value.length > 0 && autoSelect) {
      const savedWsId = localPreference('last-workspace')
      if (savedWsId) {
        const matched = workspaces.value.find(ws => ws.id === savedWsId)
        if (matched) {
          draftWorkspaceId.value = matched.id
          draftWorkspaceName.value = matched.name
        }
      }
    }
  } catch {
    // 忽略加载异常
  } finally {
    loadingWorkspaces.value = false
  }
}

function handleOpenWorkspacePopover() {
  handleWorkspacePopoverVisibility(!workspacePopoverOpen.value)
}

/** 统一由 Naive Popover 回调驱动开关，避免点击触发器时被双重翻转。 */
function handleWorkspacePopoverVisibility(open: boolean) {
  workspacePopoverOpen.value = open
  if (open) {
    workspacePopoverEpoch.value += 1
    syncWorkspacePopoverLayout()
  } else {
    workspacePopoverSpace.value = 0
  }
  if (open && !workspaces.value.length) {
    void loadWorkspaces(false)
  }
}

/** 面板按实际高度预留空间，避免固定 356px 在短面板下留下大块空白。 */
function syncWorkspacePopoverLayout() {
  void nextTick(() => {
    if (!workspacePopoverOpen.value) return
    const height = workspacePopoverCard.value?.offsetHeight || 0
    workspacePopoverSpace.value = height ? height + 12 : 0
    void nextTick(() => workspacePopoverRef.value?.syncPosition())
  })
}

watch([workspacePopoverOpen, loadingWorkspaces, () => workspaces.value.length], () => {
  if (workspacePopoverOpen.value) syncWorkspacePopoverLayout()
})

function handleSelectWorkspace(ws: { id: string; name: string } | null) {
  if (props.sessionId) {
    workspacePopoverOpen.value = false
    return
  }
  if (!ws) {
    draftWorkspaceId.value = null
    draftWorkspaceName.value = ''
    try { localStorage.removeItem(`last-workspace:${auth.user?.id}`) } catch { /* 忽略 */ }
    workspacePopoverOpen.value = false
    return
  }
  draftWorkspaceId.value = ws.id
  draftWorkspaceName.value = ws.name
  try { localStorage.setItem(`last-workspace:${auth.user?.id}`, ws.id) } catch { /* 忽略 */ }
  workspacePopoverOpen.value = false
}

async function handleCreateWorkspace() {
  const name = newWorkspaceName.value.trim()
  if (!name || creatingWorkspace.value || props.sessionId) return
  creatingWorkspace.value = true
  try {
    const created = await api.workspaces.create(name)
    const newWs = { id: String(created.id), name: String(created.name) }
    workspaces.value.unshift(newWs)
    draftWorkspaceId.value = newWs.id
    draftWorkspaceName.value = newWs.name
    try { localStorage.setItem(`last-workspace:${auth.user?.id}`, newWs.id) } catch { /* 忽略 */ }
    newWorkspaceName.value = ''
    workspacePopoverOpen.value = false
    message.success('工作区已创建并选中')
  } catch (err: any) {
    message.error(err?.message || '创建工作区失败')
  } finally {
    creatingWorkspace.value = false
  }
}

const runtimeOpen = ref(false), error = ref(''), effort = ref<Effort | null>(null)
const runtimeButton = ref<HTMLButtonElement>(), runtimeClose = ref<HTMLButtonElement>()

function closeRuntime() {
  runtimeOpen.value = false
  void nextTick(() => runtimeButton.value?.focus())
}

function toggleRuntime() {
  if (runtimeOpen.value) {
    closeRuntime()
    return
  }
  runtimeOpen.value = true
  void nextTick(() => runtimeClose.value?.focus())
}

const ui = ref<LoopUi | null>(null), selectedProfileId = ref(''), selectedAgentId = ref(''), shown = ref(80), attachments = ref<Record<string, AttachmentReference[]>>({})
const composer = ref<InstanceType<typeof AgentComposer>>(), scroller = ref<HTMLElement>(), chatShell = ref<HTMLElement>(), atBottom = ref(true)
const chatCenter = ref<HTMLElement>(), chatCenterWidth = ref(0)
type ResizeEdge = 'left' | 'right'
const chatWidth = ref<number | null>(null), isResizing = ref(false), resizeEdge = ref<ResizeEdge | null>(null), hoverResizeEdge = ref<ResizeEdge | null>(null)
const resizeHandleOffsets = ref<Record<ResizeEdge, number>>({ left: 110, right: 110 })
const minimumChatWidth = 520
const defaultChatWidth = 820
const chatOuterGutters = 40
const chatWidthStorageKey = 'agent-loop:chat-shell-width:v3'
// 空闲连接重开时，先完成服务端授权与回放，再展示保留的历史正文。
const connectionState = computed(() => props.store.sessions[props.sessionId])
const restoringConversation = computed(() => props.store.restoring.has(props.sessionId))
const state = computed(() => restoringConversation.value ? undefined : connectionState.value), trace = computed(() => props.store.traces[props.sessionId])
const draft = computed(() => props.store.draft(props.sessionId || 'draft'))
const rows = computed(() => state.value ? conversationRows(state.value) : [])
const showEmptyPrompts = computed(() => !rows.value.length && !restoringConversation.value)
const visibleRows = computed(() => rows.value.slice(-shown.value))
/** 只读取 task_plan.updated 的会话快照；工具调用草稿与失败结果不能改变抽屉。 */
const taskPlan = computed<TaskPlanDisplay | null>(() => state.value?.taskPlan || null)

/** 轮次分组与首条判定抽离到 workspaceDerived（纯函数可单测）；此处仅保留 computed 缓存。 */
const firstAssistantKeyByTurn = computed<Map<string, string>>(() => assistantKeysByTurn(rows.value))

/** 绑定范围来自会话元数据，成功文件路径来自持久工具回执。 */
function filesForRow(row: LoopRecord) {
  return writtenFiles(rows.value, row, props.session?.workspace_id, props.session?.scope_path)
}

function isFirstAssistantInTurn(row: LoopRecord): boolean {
  return firstAssistantInTurn(row, firstAssistantKeyByTurn.value)
}

const busy = computed(() => !!state.value?.activeTurn)
/** 草稿协议档可独立于平台默认项选择；后端在提交时再次校验。 */
const selectedProfile = computed<LoopProfile | null>(() => pickProfile(ui.value, selectedProfileId.value))
/** 草稿专家可独立选择；后端按会话最近一轮记忆并在提交时复核（未知 ID 回落默认专家）。 */
const selectedAgent = computed<LoopAgent | null>(() => pickAgent(ui.value, selectedAgentId.value))
const ready = computed(() => !!selectedProfile.value && !!effort.value && (props.sessionId ? !!state.value?.ready : !!ui.value?.enabled))
const canControl = computed(() => !!state.value?.controlled && !!ui.value?.permissions.interactions)
/** 同一会话只展示当前待处理的工具审批或补充问题，历史卡保留在事实流而不占聊天高度。 */
const activeInteractionDrawer = computed<InteractionRecord | null>(() => {
  const pending = Object.values(state.value?.interactions || {})
    .filter(interaction => !interaction.resolved && (interaction.kind === 'approval' || interaction.kind === 'question'))
    .sort((left, right) => left.first_cursor - right.first_cursor)
  return pending[0] || null
})
const summary = computed(() => latestRequestSummary(state.value?.attempts))
/** 仅聚合已提交的上游 usage；缺字段代表上游未返回，不能当作零或自行估算。 */
const conversationMetrics = computed<ConversationMetrics>(() => conversationMetricsFrom(state.value?.attempts, state.value?.summaryUsage))
const tasks = computed(() => Object.values(state.value?.tasks || {}))
/** 从脱敏参数/结果解析 task_id，再关联实时 Worker 事实，不能靠工具名称猜测任务。 */
function taskForTool(tool: ToolRun): LoopRecord | null {
  return taskForToolRow(tool, state.value?.tasks)
}
const quarantined = computed(() => Object.values(state.value?.executions || {}).filter(e => e.event === 'execution.quarantined'))
/** finishLabels / phaseLabels / status 文案与 workspaceDerived 同源（模板与状态条共用）。 */
const status = computed(() => phaseStatusText(state.value))
const prompts = [
  { label: '生成测试用例', description: '梳理场景与边界条件', content: '根据需求文档生成测试用例草稿', icon: 'M9 5h6m-8 0H5v16h14V5h-2M9 3h6v4H9zM8 13l2 2 5-5' },
  { label: '检查工作区文件', description: '查看内容与可处理项', content: '查看工作区文件，说明可以如何处理', icon: 'M3 7V5a1 1 0 0 1 1-1h5l2 3h9a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Zm0 3h18' },
  { label: '查找参考资料', description: '整理结论和可核对来源', content: '查询资料并给出可核对的来源', icon: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 4 4' },
]
const chatShellStyle = computed(() => ({ '--chat-width': `${chatWidth.value || defaultChatWidth}px` }))
const maximumChatWidth = computed(() => Math.max(0, chatCenterWidth.value - chatOuterGutters))
const canResizeChat = computed(() => maximumChatWidth.value > minimumChatWidth)
const renderedChatWidth = computed(() => Math.min(chatWidth.value || defaultChatWidth, maximumChatWidth.value))
// 侧栏折叠或运行信息展开均会改变可用宽度，观察实际容器以同步键盘与指针的调整范围。
watch(chatCenter, (element, _, onCleanup) => {
  if (!element) return
  const observer = new ResizeObserver(([entry]) => { chatCenterWidth.value = entry.contentRect.width })
  observer.observe(element)
  onCleanup(() => observer.disconnect())
}, { flush: 'post' })
let resizeStartX = 0, resizeStartWidth = 0
const resizeHandleHeight = 100
/** 合并重复能力读取，首次加载即时执行；后台刷新保留当前有效配置。 */
const uiRefresh = createAgentUiRefresh(
  async (sid, signal) => {
    const { data } = await http.get<LoopUi>(sid ? `/api/sessions/${sid}/agent-ui` : '/api/sessions/agent-ui', { signal })
    return data
  },
  data => {
    ui.value = data
    const savedProfileId = localPreference('agent-profile')
    const profile = data.profiles.find(item => item.id === selectedProfileId.value)
      || data.profiles.find(item => item.id === savedProfileId)
      || data.profile
      || null
    selectedProfileId.value = profile?.id || ''
    restoreEffort(profile)
    // 专家优先沿用会话记忆（data.agent 由后端按最近一轮解析），草稿回落本地偏好与默认专家。
    const savedAgentId = localPreference('agent-expert')
    const agentList = data.agents || []
    const agent = agentList.find(item => item.id === selectedAgentId.value)
      || agentList.find(item => item.id === data.agent)
      || agentList.find(item => item.id === savedAgentId)
      || agentList.find(item => item.default)
      || null
    selectedAgentId.value = agent?.id || ''
    if (!data.permissions.reasoning && state.value) { for (const a of Object.values(state.value.attempts)) { a.reasoning = ''; delete a.reasoning_preview }; for (const event of state.value.facts) delete event.data.reasoning_preview }
    if (trace.value) {
      trace.value.denied = !data.permissions.trace
      if (!data.permissions.trace) { trace.value.events = []; trace.value.seen.clear(); trace.value.seq = -1; trace.value.catalog = null }
    }
    if (!data.permissions.interactions && state.value) for (const i of Object.values(state.value.interactions)) { delete i.nonce; delete i.spec_hash; i.restricted = true }
  },
  () => { ui.value = null; error.value = '读取会话能力失败，请确认权限和服务状态' },
)
function refreshUi() { return uiRefresh.refresh(auth.user?.id || '', props.sessionId) }
function refreshUiOnFocus() { return uiRefresh.refresh(auth.user?.id || '', props.sessionId, true) }
/** 本地偏好只保存协议档 ID 和思考档位，不保存 API 端点、凭据或服务端配置。 */
function localPreference(key: string) { try { return localStorage.getItem(preferenceKey(key, auth.user?.id)) } catch { return null } }
let effortProfileKey = ''
function restoreEffort(profile: LoopProfile | null) {
  if (!profile) { effort.value = null; return }
  let saved: string | null = null
  try { saved = localStorage.getItem(effortPreferenceKey(profile, auth.user?.id)) } catch { /* 隐私模式下保留内存偏好。 */ }
  // 首次切到另一个供应商使用该模型默认值，避免普通模型的 off 覆盖 Claude 默认开启。
  const key = effortPreferenceKey(profile, auth.user?.id)
  const previous = saved || (effortProfileKey === key ? effort.value : null)
  effortProfileKey = key
  effort.value = previous && profile.allowed_efforts.includes(previous as Effort) ? previous as Effort : profile.default_effort
  if (previous && previous !== effort.value) error.value = '当前协议档不支持原思考档位，已恢复默认值'
}
function setEffort(value: Effort) {
  effort.value = value
  const profile = selectedProfile.value
  if (profile) try { localStorage.setItem(effortPreferenceKey(profile, auth.user?.id), value) } catch { /* 本地存储不可用不影响发送。 */ }
}
/** 切换只影响下一轮；已经发出的 attempt 永远读取其持久 request_summary。 */
function selectProfile(id: string) {
  const profile = ui.value?.profiles.find(item => item.id === id)
  if (!profile) return
  selectedProfileId.value = profile.id
  try { localStorage.setItem(`agent-profile:${auth.user?.id}`, profile.id) } catch { /* 本地存储不可用不影响发送。 */ }
  restoreEffort(profile)
}
/** 专家切换同样只影响下一轮；会话内选择由后端按最近一轮记忆，本地仅作草稿偏好。 */
function selectAgent(id: string) {
  const agent = ui.value?.agents.find(item => item.id === id)
  if (!agent) return
  selectedAgentId.value = agent.id
  try { localStorage.setItem(`agent-expert:${auth.user?.id}`, agent.id) } catch { /* 本地存储不可用不影响发送。 */ }
}
watch([() => props.sessionId, () => auth.user?.id], ([newSid]) => { ui.value = null; attachments.value = {}; shown.value = 80; tab.value='chat'; props.store.focus(props.sessionId, props.session?.active_task?.id); void refreshUi(); if (!newSid) void loadWorkspaces(true) }, { immediate: true })
// 轨迹订阅属于当前可见面板；切会话/卸载仅退订诊断，不关闭执行中的控制连接。
watch([tab, () => props.sessionId, () => ui.value?.permissions.trace], ([view, sid, permitted], _, cleanup) => {
  if (!sid || view !== 'trace' || !permitted) return
  const client = props.store.clients.get(sid)
  client?.trace(true, props.store.traces[sid]?.seq ?? -1)
  cleanup(() => client?.trace(false))
})
watch(() => state.value?.cursor, () => { if (atBottom.value) void nextTick(scrollBottom); void hydrateAttachments() })
const refreshTimer = setInterval(() => { if (document.visibilityState === 'visible') void refreshUi() }, 30000)
window.addEventListener('focus', refreshUiOnFocus)
try {
  const savedWidth = Number(localStorage.getItem(chatWidthStorageKey))
  if (Number.isFinite(savedWidth) && savedWidth >= minimumChatWidth) chatWidth.value = savedWidth
} catch { /* 本地存储不可用时使用默认宽度。 */ }
onBeforeUnmount(() => { uiRefresh.cancel(); props.store.focus(''); clearInterval(refreshTimer); window.removeEventListener('focus', refreshUiOnFocus); finishContentResize() })
function interactions(row: LoopRecord) { return Object.values(state.value?.interactions || {}).filter(i => identity({session_id:props.sessionId,correlation:i.correlation},true) === row.key) }
function fill(text: string) { draft.value.content = text; composer.value?.focus() }
function trackScroll() { const el=scroller.value; if(el) atBottom.value=el.scrollHeight-el.scrollTop-el.clientHeight<100 }
function scrollBottom() { const el=scroller.value; if(el) el.scrollTop=el.scrollHeight; atBottom.value=true }
/** 将固定高度的边缘阴影线定位到鼠标所在的纵向位置。 */
function updateResizeHandleOffset(edge: ResizeEdge, event: PointerEvent) {
  const rect = chatShell.value?.getBoundingClientRect()
  if (!rect) return
  resizeHandleOffsets.value[edge] = Math.min(Math.max(0, event.clientY - rect.top - resizeHandleHeight / 2), Math.max(0, rect.height - resizeHandleHeight))
}
/** 仅当鼠标进入左右边缘命中区时，显示随鼠标纵向移动的细玻璃阴影线。 */
function previewContentResize(edge: ResizeEdge, event: PointerEvent) {
  if (event.pointerType === 'touch' || isResizing.value) return
  hoverResizeEdge.value = edge
  updateResizeHandleOffset(edge, event)
}
function moveContentResizePreview(edge: ResizeEdge, event: PointerEvent) {
  if (event.pointerType === 'touch' || isResizing.value || hoverResizeEdge.value !== edge) return
  updateResizeHandleOffset(edge, event)
}
function hideContentResizePreview(edge: ResizeEdge) {
  if (!isResizing.value && hoverResizeEdge.value === edge) hoverResizeEdge.value = null
}
function resizeHandleStyle(edge: ResizeEdge) { return { top: `${resizeHandleOffsets.value[edge]}px` } }
/** 两侧边缘都可拖拽；外扩和内收只改变宽度，壳层始终保持页面居中。 */
function beginContentResize(event: PointerEvent, edge: ResizeEdge) {
  if (event.pointerType === 'touch' || event.button !== 0 || !chatShell.value) return
  event.preventDefault()
  resizeEdge.value = edge
  hoverResizeEdge.value = edge
  updateResizeHandleOffset(edge, event)
  resizeStartX = event.clientX
  resizeStartWidth = chatShell.value.getBoundingClientRect().width
  chatWidth.value = resizeStartWidth
  isResizing.value = true
  window.addEventListener('pointermove', resizeContent)
  window.addEventListener('pointerup', finishContentResize)
  window.addEventListener('pointercancel', finishContentResize)
  window.addEventListener('blur', finishContentResize)
}
function resizeContent(event: PointerEvent) {
  const upper = maximumChatWidth.value
  const direction = resizeEdge.value === 'right' ? 1 : -1
  chatWidth.value = Math.min(upper, Math.max(minimumChatWidth, resizeStartWidth + direction * (event.clientX - resizeStartX)))
  if (resizeEdge.value) updateResizeHandleOffset(resizeEdge.value, event)
}
function finishContentResize() {
  if (!isResizing.value) return
  isResizing.value = false
  resizeEdge.value = null
  hoverResizeEdge.value = null
  window.removeEventListener('pointermove', resizeContent)
  window.removeEventListener('pointerup', finishContentResize)
  window.removeEventListener('pointercancel', finishContentResize)
  window.removeEventListener('blur', finishContentResize)
  try { if (chatWidth.value) localStorage.setItem(chatWidthStorageKey, String(Math.round(chatWidth.value))) } catch { /* 本地存储失败不影响本次调整。 */ }
}
/** 键盘用户可用方向键从当前侧边缘放大或缩小居中的共享壳层。 */
function adjustContentWidthByKey(event: KeyboardEvent, edge: ResizeEdge) {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const outward = (edge === 'left' && event.key === 'ArrowLeft') || (edge === 'right' && event.key === 'ArrowRight')
  chatWidth.value = Math.min(maximumChatWidth.value, Math.max(minimumChatWidth, renderedChatWidth.value + (outward ? 24 : -24)))
  try { localStorage.setItem(chatWidthStorageKey, String(Math.round(chatWidth.value))) } catch { /* 本地存储失败不影响本次调整。 */ }
}
/** 使用兼容复制方案，HTTP 或受限浏览器仍可复制已生成回答。 */
async function copy(text: string) {
  if (!text) return
  if (await copyText(text)) {
    message.success('已复制回答到剪贴板')
  } else {
    error.value = '复制失败，请检查浏览器剪贴板权限'
  }
}
function formatSpeed(value: number | null): string {
  return value === null ? '—' : `${formatTokens(value)}/s`
}
function formatRate(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(value >= 10 ? 0 : 1)}%`
}
/** formatTokens / formatDuration 与 turnSummary 同源（顶部导入），消除双份实现。 */
function formatTimestamp(value?: string): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(date)
}
/** 引用只写入下一轮草稿，供模型参考；不会伪造为服务端持久记忆。 */
function quoteMemory(text: string) {
  if (!text) return
  const quote = `[引用对话记忆]\n${text}\n[/引用对话记忆]`
  draft.value.content = draft.value.content.trim() ? `${draft.value.content}\n\n${quote}` : quote
  composer.value?.focus()
  message.success('已引用到输入框')
}
function originalUserMessage(row: LoopRecord): LoopRecord | undefined {
  return rows.value.filter(item => item.role === 'user').reverse().find(item =>
    (row.correlation.turn_id && item.correlation.turn_id === row.correlation.turn_id)
    || (row.correlation.turn !== undefined && item.correlation.turn === row.correlation.turn),
  )
}
/** 重新生成复用该回答所属的原用户内容与附件引用，仍走新的幂等提交命令。 */
function regenerate(row: LoopRecord) {
  const source = originalUserMessage(row)
  if (!source?.content) { error.value = '未找到可重新生成的原始对话'; return }
  const refs = Array.isArray(source.attachment_refs) ? source.attachment_refs.map(item => typeof item === 'string' ? item : item?.file_id).filter((item): item is string => typeof item === 'string') : []
  void submit({ content: String(source.content), attachmentRefs: refs })
}

/** 每轮对话聚合后的操作与统计信息，仅在轮次到达结尾时挂载在轮次最后一行展示。 */
const turnSummaryByLastRowKey = computed<Map<string, TurnSummary>>(() =>
  calculateTurnSummaries(rows.value, {
    activeTurnId: state.value?.activeTurn,
    isBusy: busy.value,
    sessionId: props.sessionId,
    summaryUsage: state.value?.summaryUsage,
  }),
)

/** 服务端仅将工具调用身份公开为持久字段；页面按此边界分离 ReAct 过程和最终总结。 */
const summaryAssistantRowKeys = computed<Set<string>>(() =>
  new Set([...turnSummaryByLastRowKey.value.values()].map(summary => summary.summaryRow.key))
)

/** 将本轮完成的媒体工具结果放到总结消息之前，保持过程卡只呈现调用事实。 */
const mediaPreviewsBySummaryRowKey = computed<Map<string, MediaPreview[]>>(() => {
  const previewsBySummary = new Map<string, MediaPreview[]>()
  const toolsByTurn = new Map<string, ToolRun[]>()
  for (const row of rows.value) {
    if (!('status' in row && 'name' in row)) continue
    const tool = row as ToolRun
    const turnKey = getTurnIdentifier(tool)
    const tools = toolsByTurn.get(turnKey) || []
    tools.push(tool)
    toolsByTurn.set(turnKey, tools)
  }
  for (const summary of turnSummaryByLastRowKey.value.values()) {
    const previews = mediaPreviewsFor(toolsByTurn.get(summary.turnKey) || [])
    if (previews.length) previewsBySummary.set(summary.summaryRow.key, previews)
  }
  return previewsBySummary
})

function mediaPreviewsForSummary(rowKey: string): MediaPreview[] {
  return mediaPreviewsBySummaryRowKey.value.get(rowKey) || []
}

function isSummaryAssistantRow(row: LoopRecord): boolean {
  return row.role !== 'user' && !('status' in row && 'name' in row) && summaryAssistantRowKeys.value.has(row.key)
}

function isProcessAssistantRow(row: LoopRecord): boolean {
  return row.role !== 'user' && !('status' in row && 'name' in row) && !isSummaryAssistantRow(row)
}

function formatSessionTitle(rawText: string): string {
  if (!rawText) return '新会话'
  let cleaned = rawText.trim()
  // 剥除 [引用对话记忆] ... [/引用对话记忆]
  cleaned = cleaned.replace(/\[引用对话记忆\][\s\S]*?\[\/引用对话记忆\]/g, '').trim()
  // 剥除其他 [引用...] 标签
  cleaned = cleaned.replace(/^\[[^\]]+\]\s*/g, '').trim()
  // 剥除 markdown 标题符 # 或列表符 * -
  cleaned = cleaned.replace(/^[#*\-\s]+/g, '').trim()
  // 压缩连续空白
  cleaned = cleaned.replace(/\s+/g, ' ')
  // 剥离首尾引号
  cleaned = cleaned.replace(/^["'“”‘’]+|["'“”‘’]+$/g, '')
  if (!cleaned) return '新会话'
  return cleaned.slice(0, 24)
}

/** 冻结输入/附件/effort 与幂等 ID；未受理时保留可恢复草稿。 */
async function submit(override?: { content: string; attachmentRefs: string[] }) {
  if (!ready.value || busy.value || draft.value.submitting) return
  const source = draft.value, selectedEffort=effort.value, profile=selectedProfile.value
  if (!selectedEffort || !profile) return
  source.submitting = true; error.value = ''
  if (state.value) state.value.error = ''
  const content=override?.content ?? source.content, refs=override?.attachmentRefs ?? source.files.filter(f=>!f.removed && f.id).map(f=>f.id!)
  try {
    let sid=props.sessionId
    // 短票与 REST 建会没有依赖关系，先并行领取可缩短新会话的首次发送等待。
    let preparedTicket: Promise<string> | undefined
    if(!sid) {
      preparedTicket=api.auth.getWsTicket().then(({ticket})=>ticket)
      // 建会失败时仍消费此 Promise 的拒绝，避免后台短票请求产生未处理异常。
      void preparedTicket.catch(()=>undefined)
      const initialTitle = formatSessionTitle(content)
      sid=await props.createSession(activeWorkspaceId.value || undefined, preparedTicket, sessionTier.value || undefined, initialTitle)
      if(!sid) throw new Error()
      props.store.drafts[sid]=source
      delete props.store.drafts.draft
    } else if (props.session && (!props.session.title || props.session.title === '新会话')) {
      const newTitle = formatSessionTitle(content)
      if (newTitle && newTitle !== '新会话') {
        props.session.title = newTitle
        void api.sessions.updateTitle(sid, newTitle).catch(() => {})
      }
    }
    const client=props.store.open(sid, preparedTicket)
    source.pending ??= client.command('turn.submit',{client_message_id:createRequestId(),content,attachment_refs:refs,profile_id:profile.id,reasoning_effort:selectedEffort,agent_id:selectedAgent.value?.id})
    // 只有首次订阅完成后才发送；超时取消等待，不能在以后重连时偷偷补发。
    if (!props.store.sessions[sid].ready) await new Promise<void>((resolve, reject) => {
      const unwatch = watch(() => props.store.sessions[sid]?.ready, ok => {
        if (ok) { clearTimeout(timer); unwatch(); resolve() }
      })
      const timer = setTimeout(() => { unwatch(); reject(new Error('连接超时')) }, 15000)
    })
    if (!client.send(source.pending)) throw new Error('连接中断')
    props.store.sessions[sid].controlled = true
  } catch (exc) {
    source.submitting = false
    error.value = exc instanceof ApiError ? `${exc.message}，草稿已保留`
      : source.pending ? '消息尚未确认发送，请连接恢复后使用原请求 ID 重发，草稿已保留'
      : '无法创建或发送会话，草稿已保留'
  }
}
/** 重试保留原请求及正文，只有实际写入 socket 才显示发送中。 */
function retry() {
  if (draft.value.pending && state.value?.ready && props.store.send(props.sessionId, draft.value.pending)) {
    draft.value.submitting = true; error.value = ''; state.value.error = ''
  }
}
function stop() { if(!canControl.value || !state.value?.activeTurn) return; const client=props.store.clients.get(props.sessionId)!; const command=client.command('turn.cancel',{turn_id:state.value.activeTurn}); if(client.send(command)) { state.value.cancelling=true; draft.value.cancelRequestId=command.request_id } }
function respond(interaction: InteractionRecord, values: Data) {
  if(!canControl.value || !state.value?.ready || interaction.submitting) return
  const c=interaction.correlation
  const data={interaction_id:interaction.interaction_id,turn_id:c.turn_id,turn:c.turn,attempt_id:c.attempt_id,call_id:c.call_id,nonce:interaction.nonce,...values,...(interaction.kind==='task_confirmation'?{spec_hash:interaction.spec_hash}:{})}
  const client=props.store.clients.get(props.sessionId)!, command=client.command(`${interaction.kind}.respond`,data)
  if(client.send(command)){interaction.submitting=true;draft.value.pending=command;draft.value.pendingInteraction=interaction.key}
}
/** 文件元数据只取授权接口，不信任历史里的任意 URL。 */
async function hydrateAttachments() {
  const sid=props.sessionId
  for(const row of rows.value.filter(r=>r.role==='user' && r.attachment_refs?.length)){
    if(attachments.value[row.key])continue
    attachments.value[row.key]=[]
    const values=await Promise.all((row.attachment_refs as any[]).map(async item=>{const id=typeof item==='string'?item:item.file_id;try{const {data}=await http.get(`/api/files/${encodeURIComponent(id)}`);return {file_id:id,filename:data.filename,size:data.size,content_type:data.content_type,content_url:`/api/files/${encodeURIComponent(id)}/content`} as AttachmentReference}catch{return null}}))
    if(sid===props.sessionId)attachments.value[row.key]=values.filter((v):v is AttachmentReference=>v!==null)
  }
}
</script>
<style>
.loop-control{background:transparent;color:inherit;border:1px solid transparent;border-radius:7px;padding:7px 9px;font-size:12px;cursor:pointer}.loop-control:hover{background:#eaf3ee}.loop-primary{background:#174a3a!important;color:#fff!important}.loop-workspace button:focus-visible,.loop-workspace input:focus-visible,.loop-workspace summary:focus-visible{outline:2px solid #16977a;outline-offset:2px}
</style>
<style scoped>
.generated-files{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}.generated-files a{padding:6px 10px;border:1px solid #d5e5db;border-radius:8px;color:#175a40;text-decoration:none;overflow-wrap:anywhere}

.loop-workspace {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  container-type: inline-size;
  background: var(--bg-main);
}

.loop-toolbar {
  display: flex;
  flex: 0 0 auto;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 16px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-main);
}

.loop-session-heading {
  flex: 1 1 125px;
  min-width: 0;
}

.loop-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
}

.workspace-tab-group {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-elevated);
}

.workspace-tab {
  min-height: 28px;
  padding: 0 9px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.workspace-tab:hover:not(:disabled) { color: var(--text-primary); }

.workspace-tab.active {
  background: var(--t-agent);
  color: var(--c-agent);
  font-weight: 650;
}

.workspace-tab:disabled { opacity: .55; cursor: default; }

.trace-tab-count {
  margin-inline-start: 2px;
  padding: 1px 4px;
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-secondary);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
}

.loop-tabs-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
}

.loop-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}

.loop-status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
}

.loop-status .running { background: var(--accent-success); }

.loop-runtime-btn {
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-main);
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.loop-runtime-btn:hover, .loop-runtime-btn[aria-expanded='true'] {
  background: var(--t-agent);
  color: var(--c-agent);
}

.loop-content {
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
}

.loop-center {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.loop-conversation {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 24px 5px;
  scrollbar-gutter: stable both-edges;
}

.loop-message {
  min-width: 0;
  margin: 0 0 22px;
  overflow-wrap: anywhere;
}

.loop-message header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.loop-message header small { color: var(--text-tertiary); font-weight: 400; }
.assistant-identity { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.assistant-identity strong { font-weight: 650; }
.assistant-identity time { color: var(--text-tertiary); font-size: 11px; font-weight: 400; font-variant-numeric: tabular-nums; }
.loop-message.assistant.is-continuation { margin-top: 12px; }

.loop-message.user {
  width: fit-content;
  max-width: min(100%, 680px);
  margin-inline-start: auto;
  padding: 12px 16px;
  border-radius: var(--radius-xl);
  background: var(--t-agent);
  color: var(--text-primary);
}

.loop-message.user header { margin-bottom: 4px; color: var(--c-agent); }
.loop-message.user p { margin: 0; white-space: pre-wrap; line-height: 1.65; }
.history-files { display: flex; flex-wrap: wrap; gap: 8px; }

.loop-composer-wrap {
  position: relative;
  width: 100%;
  max-width: 950px;
  margin: 0 auto;
  padding: 10px 20px 18px;
}

.loop-runtime {
  flex: 0 0 240px;
  width: 240px;
  min-width: 0;
  overflow: auto;
  padding: 14px;
  border-left: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
  color: var(--text-primary);
  font-size: 12px;
}

.runtime-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border-subtle);
}

.runtime-heading h2 { margin: 0; font-size: 15px; }

.runtime-close {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  padding: 0;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-main);
  color: var(--text-secondary);
  cursor: pointer;
}

.runtime-close:hover { color: var(--text-primary); }

.loop-runtime dl, .loop-runtime h3 { margin: 14px 0 6px; }
.loop-runtime h3 { font-size: 13px; }
.loop-runtime dt { color: var(--text-secondary); }
.loop-runtime dd { margin: 3px 0 12px; overflow-wrap: anywhere; }
.runtime-events { margin: 0; padding-inline-start: 16px; color: var(--text-secondary); overflow-wrap: anywhere; }
.runtime-task { padding-block: 8px; border-bottom: 1px solid var(--border-subtle); overflow-wrap: anywhere; }
.runtime-task p { margin: 3px 0; }

.loop-notice {
  margin: 5px 10px;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--accent-warning) 9%, var(--bg-main));
  color: var(--accent-warning);
  font-size: 12px;
}

.loop-notice.error { background: var(--t-error); color: var(--c-error); }
.loop-notice button, .history-more { border: 0; background: transparent; text-decoration: underline; cursor: pointer; }

.jump-bottom {
  position: absolute;
  top: 2px;
  right: 0;
  z-index: 2;
  transform: translateY(-100%);
  padding: 6px 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  background: var(--bg-main);
  color: var(--text-secondary);
  cursor: pointer;
}

.jump-bottom:hover { color: var(--text-primary); }
.muted { color: var(--text-tertiary); }

@container (max-width: 700px) {
  .loop-toolbar { padding: 8px 12px; gap: 4px; }
  .loop-session-heading, .loop-tabs { flex-basis: 100%; }
  .loop-tabs { justify-content: space-between; gap: 4px 8px; }
  .loop-tabs-actions { gap: 4px; }
  .loop-runtime {
    position: absolute;
    z-index: 30;
    inset: 0 0 0 auto;
    max-width: calc(100% - 24px);
    box-shadow: -12px 0 26px color-mix(in srgb, var(--text-primary) 10%, transparent);
  }
}


.attempt-error { display: block; margin-top: 8px; color: #a24d43; line-height: 1.5; }

/* ReAct 过程与本轮总结使用服务端持久的工具调用字段分段，避免混入可操作回答。 */
.loop-message.assistant.is-process { margin-bottom: 12px; }
.loop-message.assistant.is-turn-summary { margin-top: 16px; }
.turn-process-tool { margin: 0 0 12px; }
.turn-media-results { margin: 0 0 12px; }
.turn-media-results > .turn-segment-label { margin: 0 0 2px; }
.turn-media-results :deep(.media-preview) { margin: 8px 0 0; }
.turn-segment-label { display: inline-flex; align-items: center; min-height: 20px; padding: 0 7px; border-radius: 10px; font-size: 11px; font-weight: 500; line-height: 20px; }
.turn-segment-label.process { color: var(--text-secondary); background: var(--bg-elevated); }
.turn-segment-label.summary { color: #176b55; background: #e6f5ee; }
[data-theme='dark'] .turn-segment-label.process { color: var(--text-secondary, #9ca3af); background: var(--bg-elevated, #1f2937); }
[data-theme='dark'] .turn-segment-label.summary { color: var(--c-agent, #34d399); background: var(--t-agent, rgba(22, 151, 122, 0.2)); }
.turn-process-tool > .turn-segment-label { margin: 0 0 6px; }

/* 每轮对话结尾的统一操作与指标栏 */
.turn-end-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
  margin-bottom: 22px;
  padding: 0 4px;
  color: var(--text-tertiary);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  user-select: none;
}
.turn-end-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.turn-end-actions .assistant-action {
  display: inline-grid;
  width: 26px;
  height: 26px;
  place-items: center;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #758497;
  padding: 0;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}
.turn-end-actions .assistant-action:hover:not(:disabled) {
  background: #edf5f1;
  color: #174a3a;
}
.turn-end-actions .assistant-action:disabled {
  cursor: default;
  opacity: 0.35;
}
.turn-end-metrics {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}
.turn-end-metric {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--text-tertiary);
  font-size: 11.5px;
}
[data-theme='dark'] .turn-end-toolbar,
[data-theme='dark'] .turn-end-metric {
  color: #94a3b8;
}
[data-theme='dark'] .turn-end-actions .assistant-action {
  color: #94a3b8;
}
[data-theme='dark'] .turn-end-actions .assistant-action:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: #34d399;
}

/* 消息区与输入框共用同一宽度壳层，并始终在页面内容区居中。 */
.loop-chat-shell {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  width: var(--chat-width);
  max-width: calc(100% - 40px);
  margin-inline: auto;
}

.loop-chat-shell .loop-composer-wrap {
  flex: 0 0 auto;
  max-width: none;
  padding: 10px 0 14px;
}
.loop-chat-shell.has-interaction .loop-conversation{min-height:96px;padding-bottom:12px}.loop-chat-shell.has-interaction .loop-composer-wrap{padding-top:8px}.loop-chat-shell.has-interaction .composer-top-bar,.loop-trace-composer.has-interaction .composer-top-bar{display:none}.composer-anchor{position:relative}.composer-interaction-drawer{position:absolute;z-index:20;right:0;bottom:calc(100% + 12px);left:0;margin:0}.composer-interaction-enter-active,.composer-interaction-leave-active{overflow:hidden;transition:max-height .24s cubic-bezier(.2,.8,.2,1),opacity .18s ease,transform .24s cubic-bezier(.2,.8,.2,1)}.composer-interaction-enter-from,.composer-interaction-leave-to{max-height:0;opacity:0;transform:translateY(12px)}.composer-interaction-enter-to,.composer-interaction-leave-from{max-height:520px;opacity:1;transform:translateY(0)}

/* 自适应空闲空间。高度不足时从顶部开始滚动，标题和输入框仍可访问。 */
.loop-chat-shell.is-empty {
  padding-block: 24px 30px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.loop-chat-shell.is-empty .loop-conversation.is-empty { display: none; }

.loop-empty-hero {
  flex: 0 0 auto;
  width: 100%;
  margin-block: auto 14px;
  padding-inline: 4px;
}

.hero-tagline {
  margin: 0 0 7px;
  color: var(--text-primary);
  font: 650 clamp(25px, 4vw, 38px)/1.25 var(--font-display);
  letter-spacing: -.035em;
}

.hero-subline {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.6;
}

.loop-loading {
  margin-block: auto 12px;
  color: var(--text-secondary);
  text-align: center;
}

.loop-empty-prompts {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-block: 1px auto;
}

.empty-prompt-card {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-main);
  color: var(--text-primary);
  text-align: start;
  cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}

.empty-prompt-card:hover {
  border-color: var(--accent-ai);
  background: var(--bg-elevated);
}

.prompt-icon {
  display: grid;
  flex: 0 0 32px;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: var(--radius-lg);
  background: var(--t-agent);
  color: var(--c-agent);
}

.prompt-text {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 2px;
  font-size: 11px;
  line-height: 1.4;
  color: var(--text-secondary);
}

.prompt-text strong {
  font-size: 13px;
  font-weight: 650;
  color: var(--text-primary);
}

.prompt-arrow { flex-shrink: 0; color: var(--text-tertiary); }
.empty-prompt-card:hover .prompt-arrow { color: var(--c-agent); }

@container (max-width: 640px) {
  .loop-empty-prompts { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .empty-prompt-card { padding: 6px 8px; }
  .prompt-text { display: flex; align-items: baseline; flex-wrap: wrap; gap: 2px 8px; }
}

/* 拖拽式隐藏边框：命中区与图2高品质羽化渐变悬浮手柄 */
.loop-chat-shell.is-resizing {
  user-select: none;
  cursor: col-resize;
}
.loop-chat-shell.is-resizing * {
  user-select: none !important;
}
.loop-width-edge {
  position: absolute;
  z-index: 30;
  top: 0;
  bottom: 0;
  width: 28px;
  cursor: col-resize;
}
.loop-width-edge-left {
  left: -14px;
}
.loop-width-edge-right {
  right: -14px;
}
.loop-width-handle {
  position: absolute;
  left: 0;
  width: 28px;
  height: 100px;
  border: 0;
  border-radius: 0;
  background: transparent;
  cursor: col-resize;
  opacity: 0;
  touch-action: none;
  padding: 0;
  margin: 0;
  outline: none;
  transition: opacity 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  /* 默认浅色主题变量：对齐图2像素级平滑渐变消隐 (212/255 ≈ 0.17 核心实度) */
  --resizer-rgb: 15, 23, 42;
  --resizer-alpha-core: 0.17;
  --resizer-alpha-mid: 0.12;
  --resizer-alpha-soft: 0.06;
  --resizer-alpha-tip: 0.02;
  --resizer-scale-x: 1;
}
.loop-width-handle.is-visible,
.loop-width-handle.is-active,
.loop-width-handle:focus-visible {
  opacity: 1;
  background: transparent;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}
.loop-width-handle:hover {
  background: transparent;
  --resizer-alpha-core: 0.32;
  --resizer-alpha-mid: 0.22;
  --resizer-alpha-soft: 0.10;
  --resizer-alpha-tip: 0.03;
  --resizer-scale-x: 1.25;
}
.loop-width-handle.is-active {
  background: transparent;
  --resizer-alpha-core: 0.48;
  --resizer-alpha-mid: 0.34;
  --resizer-alpha-soft: 0.16;
  --resizer-alpha-tip: 0.05;
  --resizer-scale-x: 1.35;
}
/* 深色主题适配 */
[data-theme='dark'] .loop-width-handle {
  --resizer-rgb: 255, 255, 255;
  --resizer-alpha-core: 0.22;
  --resizer-alpha-mid: 0.15;
  --resizer-alpha-soft: 0.07;
  --resizer-alpha-tip: 0.02;
}
[data-theme='dark'] .loop-width-handle:hover {
  --resizer-alpha-core: 0.38;
  --resizer-alpha-mid: 0.26;
  --resizer-alpha-soft: 0.12;
  --resizer-alpha-tip: 0.04;
}
[data-theme='dark'] .loop-width-handle.is-active {
  --resizer-alpha-core: 0.54;
  --resizer-alpha-mid: 0.38;
  --resizer-alpha-soft: 0.18;
  --resizer-alpha-tip: 0.06;
}
.loop-width-handle span {
  display: block;
  width: 2px;
  height: 100%;
  margin: auto;
  border-radius: 999px;
  background: linear-gradient(
    to bottom,
    rgba(var(--resizer-rgb), 0) 0%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-tip)) 10%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-soft)) 20%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-mid)) 30%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-core)) 38%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-core)) 62%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-mid)) 70%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-soft)) 80%,
    rgba(var(--resizer-rgb), var(--resizer-alpha-tip)) 90%,
    rgba(var(--resizer-rgb), 0) 100%
  );
  box-shadow: none;
  transform: scaleX(var(--resizer-scale-x));
  transform-origin: center center;
  transition: transform 0.15s ease, background 0.15s ease;
  pointer-events: none;
}
@container (max-width: 560px) {
  .loop-chat-shell { max-width: calc(100% - 24px); width: 100%; }
  .loop-chat-shell .loop-composer-wrap { padding-block: 6px 10px; }
  .loop-chat-shell .loop-conversation { padding: 14px 0; }
  .loop-chat-shell.has-interaction .loop-conversation { min-height: 72px; padding-bottom: 8px; }
  .loop-width-edge { display: none; }
  .loop-trace-composer { padding: 8px 12px 12px; }
}

@media (max-height: 640px) {
  .loop-chat-shell.is-empty { padding-block: 12px 16px; }
  .loop-empty-hero { margin-bottom: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .empty-prompt-card, .loop-width-handle, .loop-width-handle span { transition: none; }
}

/* 输入框上方工作区选择器（图2样式） */
.composer-top-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  margin-bottom: 6px;
  padding: 0 4px;
}
.composer-ws-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  padding: 4px 8px;
  color: #263548;
  font-size: 13px;
  font-weight: 550;
  cursor: pointer;
  position: relative;
  z-index: 1;
  transition: transform 0.36s cubic-bezier(0.16, 1, 0.3, 1), background-color 0.16s ease, color 0.16s ease, border-color 0.16s ease, box-shadow 0.2s ease;
  user-select: none;
  will-change: transform;
}
.composer-ws-btn.is-open {
  background: #edf7f1;
  border-color: #c6dfd1;
  color: #174a3a;
  box-shadow: 0 7px 18px rgba(23, 74, 58, 0.11);
}
.composer-ws-btn.is-open .ws-btn-arrow {
  transform: rotate(180deg);
  color: #1f7155;
}
.composer-ws-btn:hover {
  background: #edf3f0;
  color: #174a3a;
}
.composer-ws-btn.is-draft:hover {
  border-color: #d1ded7;
}
.ws-btn-folder-icon {
  display: inline-flex;
  align-items: center;
  color: #4a5c53;
}
.composer-ws-btn:hover .ws-btn-folder-icon {
  color: #174a3a;
}
.ws-btn-name {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-btn-arrow {
  display: inline-flex;
  align-items: center;
  color: #7b8e84;
  margin-left: -1px;
  transition: transform 0.24s cubic-bezier(0.16, 1, 0.3, 1), color 0.16s ease;
}
[data-theme='dark'] .composer-ws-btn {
  color: #e2e8f0;
}
[data-theme='dark'] .composer-ws-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}
[data-theme='dark'] .ws-btn-folder-icon {
  color: #94a3b8;
}

/* 工作区弹窗面板 */
.ws-popover-card {
  width: 300px;
  max-width: calc(100vw - 32px);
  background: #ffffff;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 10px 30px -4px rgba(23, 74, 58, 0.15), 0 4px 12px -2px rgba(15, 23, 42, 0.08);
  border: 1px solid #d8e4dc;
  font-size: 13px;
  transform-origin: 22px 0;
  animation: workspace-popover-enter 0.32s cubic-bezier(0.16, 1, 0.3, 1) both;
  backface-visibility: hidden;
  will-change: transform, opacity;
}
@keyframes workspace-popover-enter {
  from { opacity: 0; transform: translate3d(0, -8px, 0) scale(0.985); }
  to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); }
}
:deep(.workspace-popover-layer) {
  border: 0;
  border-radius: 12px;
  box-shadow: none;
  overflow: visible;
}
.ws-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.ws-popover-title {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-weight: 650;
  color: #1e332a;
}
.ws-popover-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
  background: #eef2f5;
  color: #64748b;
}
.ws-popover-badge.is-active {
  background: #e6f1ec;
  color: #174a3a;
}
.ws-popover-badge-draft {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5f3;
  color: #647d70;
}
.ws-popover-tip {
  margin: 0 0 10px;
  font-size: 11.5px;
  color: #74877c;
  line-height: 1.45;
}
.ws-popover-loading,
.ws-popover-empty {
  padding: 14px 0;
  text-align: center;
  color: #8c9e94;
  font-size: 12px;
}
.ws-popover-list {
  max-height: 190px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 10px;
  padding-right: 2px;
}
.ws-popover-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 9px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #33443c;
  text-align: left;
  cursor: pointer;
  transition: all 0.14s ease;
  font-size: 12.5px;
}
.ws-popover-item:hover:not(:disabled) {
  background: #f0f6f3;
  color: #174a3a;
}
.ws-popover-item.is-selected {
  background: #e6f1ec;
  border-color: #cde0d6;
  color: #174a3a;
  font-weight: 600;
}
.ws-popover-item:disabled {
  cursor: default;
}
.ws-item-folder {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #7b8e84;
  flex-shrink: 0;
}
.ws-popover-item.is-selected .ws-item-folder {
  color: #1f5947;
}
.ws-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ws-item-check {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #1f5947;
  flex-shrink: 0;
}
.ws-popover-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid #e7eee9;
}
.ws-popover-input {
  flex: 1;
  min-width: 0;
  height: 32px;
  box-sizing: border-box;
  padding: 6px 10px;
  border: 1px solid #d2ded7;
  border-radius: 6px;
  background: #f9fbf9;
  font-size: 12px;
  color: #1e332a;
  outline: none !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.ws-popover-input:focus,
.ws-popover-input:focus-visible {
  outline: none !important;
  border-color: #1f5947 !important;
  box-shadow: 0 0 0 2px rgba(31, 89, 71, 0.12) !important;
  background: #ffffff;
}
.ws-popover-create-btn {
  height: 32px;
  box-sizing: border-box;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0;
  border-radius: 6px;
  background: #1f5947;
  color: #ffffff;
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}
.ws-popover-create-btn:hover:not(:disabled) {
  background: #174a3a;
}
.ws-popover-create-btn:disabled {
  background: #edf3f0;
  color: #9ab0a4;
  opacity: 1;
  cursor: not-allowed;
}

[data-theme='dark'] .ws-popover-card {
  background: #1e293b;
  border-color: rgba(255, 255, 255, 0.12);
  box-shadow: 0 10px 30px -4px rgba(0, 0, 0, 0.5);
}
@media (prefers-reduced-motion: reduce) {
  .composer-top-bar,
  .composer-ws-btn,
  .ws-btn-arrow { transition: none; }
  .ws-popover-card { animation: none; }
}
@media (max-height: 640px) {
  .ws-popover-list { max-height: 132px; }
}
[data-theme='dark'] .ws-popover-title {
  color: #f1f5f9;
}
[data-theme='dark'] .ws-popover-badge-draft {
  background: rgba(255, 255, 255, 0.08);
  color: #94a3b8;
}
[data-theme='dark'] .ws-popover-tip {
  color: #94a3b8;
}
[data-theme='dark'] .ws-popover-item {
  color: #cbd5e1;
}
[data-theme='dark'] .ws-popover-item:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  color: #ffffff;
}
[data-theme='dark'] .ws-popover-item.is-selected {
  background: rgba(22, 151, 122, 0.2);
  border-color: rgba(22, 151, 122, 0.4);
  color: #34d399;
}
[data-theme='dark'] .ws-item-folder {
  color: #94a3b8;
}
[data-theme='dark'] .ws-popover-item.is-selected .ws-item-folder {
  color: #34d399;
}
[data-theme='dark'] .ws-item-check {
  color: #34d399;
}
[data-theme='dark'] .ws-popover-footer {
  border-top-color: rgba(255, 255, 255, 0.1);
}
[data-theme='dark'] .ws-popover-input {
  background: #0f172a;
  border-color: rgba(255, 255, 255, 0.15);
  color: #f8fafc;
}
[data-theme='dark'] .ws-popover-input:focus,
[data-theme='dark'] .ws-popover-input:focus-visible {
  border-color: #16977a !important;
  box-shadow: 0 0 0 2px rgba(22, 151, 122, 0.25) !important;
  background: #1e293b;
}
[data-theme='dark'] .ws-popover-create-btn {
  background: #16977a;
  color: #ffffff;
}
[data-theme='dark'] .ws-popover-create-btn:hover:not(:disabled) {
  background: #148369;
}
[data-theme='dark'] .ws-popover-create-btn:disabled {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.3);
}

/* 页面底部指标条 */
.loop-bottom-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px 24px;
  padding: 8px 20px 10px;
  color: var(--text-tertiary);
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
  border-top: 1px solid var(--border-subtle);
  background: color-mix(in srgb, var(--bg-main) 85%, transparent);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  flex-shrink: 0;
}
.loop-bottom-metrics span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.loop-bottom-metrics svg {
  color: #8da0b3;
  flex-shrink: 0;
}
[data-theme='dark'] .loop-bottom-metrics {
  border-top-color: rgba(255, 255, 255, 0.08);
  background: rgba(17, 24, 39, 0.8);
  color: #94a3b8;
}
[data-theme='dark'] .loop-bottom-metrics svg {
  color: #64748b;
}

</style>
