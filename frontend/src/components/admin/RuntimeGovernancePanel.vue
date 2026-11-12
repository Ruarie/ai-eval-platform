<template>
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

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'

import { api } from '../../api/http'

const message = useMessage()

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

async function loadRuntimeSettings() {
  try {
    const settings = await api.admin.getSettings()
    const runtime = (settings as any)?.runtime
    if (runtime) runtimeForm.value = { ...runtimeForm.value, ...runtime }
    if ((settings as any)?.permission_tier_default) {
      runtimeForm.value.permission_tier_default = (settings as any).permission_tier_default
    }
  } catch (err: any) {
    message.error(err.message || '运行时参数加载失败')
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

onMounted(loadRuntimeSettings)
</script>

<style scoped>
/* ═══════════════════════════════════════════════════════════════
   运行时与主机治理
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

/* 间距工具类：父视图 scoped 样式不作用到子组件，随组件携带。 */
.mt2 { margin-top: 2px; }
.mt10 { margin-top: 10px; }
.mt20 { margin-top: 20px; }
.mb10 { margin-bottom: 10px; }
</style>
