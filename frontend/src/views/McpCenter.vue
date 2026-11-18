<template>
  <div class="mc-page">
    <header class="mc-head">
      <div>
        <div class="eyebrow">能力中心</div>
        <h1>MCP 中心</h1>
        <p>平台已注册的工具通道与扩展目录；只读展示，连接配置在部署期完成。</p>
      </div>
      <div class="mc-head-actions">
        <n-button :loading="checking" @click="runCheck">健康检查</n-button>
        <n-button :disabled="loading" @click="loadAll">刷新</n-button>
      </div>
    </header>

    <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

    <n-spin :show="loading">
      <div class="mc-stats">
        <div><b>{{ summary.total_tools ?? '—' }}</b><span>已注册工具</span></div>
        <div><b>{{ summary.native_tools_count ?? '—' }}</b><span>原生工具</span></div>
        <div><b>{{ summary.internal_mcp_tools_count ?? '—' }}</b><span>内部 MCP</span></div>
        <div><b>{{ summary.external_mcp_servers_count ?? '—' }}</b><span>外部 MCP 服务</span></div>
      </div>

      <section v-if="channels.length" class="mc-channels">
        <article v-for="c in channels" :key="c.channel" class="mc-channel" :class="{ bad: !c.ok }">
          <div class="mc-channel-top">
            <span class="mc-dot" :class="dotClass(c)"></span>
            <b>{{ c.name }}</b>
            <span class="mc-latency">{{ c.latency_ms }}ms</span>
          </div>
          <p class="mc-channel-msg">{{ c.message }}</p>
          <div class="mc-channel-meta">
            <span>工具 {{ c.tools_count ?? '—' }}</span>
            <span v-if="c.sandbox_mode">{{ c.sandbox_mode }}</span>
          </div>
        </article>
      </section>

      <section class="mc-tools">
        <div class="mc-section-head">
          <h2>工具清单</h2>
          <span>按通道分组；权限与风险等级决定是否需要确认卡</span>
        </div>
        <div v-for="group in groups" :key="group.key" class="mc-group">
          <h3>{{ group.title }} <small>{{ group.items.length }} 个</small></h3>
          <div class="mc-table">
            <div class="mc-row mc-row-head">
              <span>工具</span><span>权限</span><span>风险</span><span>超时</span><span>说明</span>
            </div>
            <div v-for="tool in group.items" :key="tool.name" class="mc-row">
              <span class="mc-name">
                <b>{{ tool.display_name || tool.name }}</b>
                <small>{{ tool.name }}</small>
              </span>
              <span><span class="mc-tag" :class="'perm-' + (tool.permission || 'read')">{{ permLabel(tool.permission) }}</span></span>
              <span class="mc-risk">{{ tool.risk_level || '—' }}</span>
              <span class="mc-timeout">{{ tool.timeout_s != null ? tool.timeout_s + 's' : '—' }}</span>
              <span class="mc-desc">{{ tool.desc || '（无描述）' }}</span>
            </div>
          </div>
        </div>
        <p v-if="!groups.length && !loading" class="mc-empty">还没有注册任何工具。</p>
      </section>

      <div class="mc-note">
        <b>边界：</b>浏览器只能查看目录与状态，不能指定任意第三方 MCP 地址；新增扩展需在后端 allowlist 登记并随部署发布。
        媒体 MCP 的模型配置在「协议档 → MCP 与工具」页维护，密钥只在服务端保存。
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import http from '../api/http'

interface ToolItem {
  name: string
  display_name?: string
  desc?: string
  permission?: string
  risk_level?: string
  timeout_s?: number
  transport?: string
  server_id?: string
  enabled?: boolean
}

interface Channel {
  channel: string
  name: string
  ok: boolean
  tools_count?: number
  latency_ms?: number
  message?: string
  sandbox_mode?: string
}

const tools = ref<ToolItem[]>([])
const channels = ref<Channel[]>([])
const summary = ref<Record<string, number>>({})
const loading = ref(false)
const checking = ref(false)
const error = ref('')

/** 未启用（standby）不是故障，用中性色区分，避免绿点误导。 */
const dotClass = (c: Channel): string => {
  if (c.ok) return (c.message || '').includes('未启用') ? 'idle' : 'ok'
  return 'bad'
}

const permLabel = (permission?: string): string => {
  if (permission === 'write') return '写入'
  if (permission === 'network') return '联网'
  if (permission === 'danger') return '高危'
  return '只读'
}

/** 原生与 MCP 扩展分开展示，避免把进程内工具当成外部连接器。 */
const groups = computed(() => {
  const native = tools.value.filter((t) => t.transport === 'native')
  const mcp = tools.value.filter((t) => t.transport !== 'native')
  return [
    { key: 'native', title: '原生工具（进程内）', items: native },
    { key: 'mcp', title: 'MCP 扩展', items: mcp },
  ].filter((g) => g.items.length)
})

async function loadAll(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const { data } = await http.get<{ items: ToolItem[]; total: number }>('/api/mcp/all-tools')
    tools.value = data.items || []
    summary.value = { ...summary.value, total_tools: data.total ?? tools.value.length }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载工具清单失败'
  } finally {
    loading.value = false
  }
}

async function runCheck(): Promise<void> {
  checking.value = true
  error.value = ''
  try {
    const { data } = await http.get<{
      ok: boolean
      summary: Record<string, number>
      channels: Record<string, Channel>
    }>('/api/mcp/health-check')
    summary.value = { ...summary.value, ...data.summary }
    channels.value = Object.values(data.channels || {})
  } catch (err) {
    error.value = err instanceof Error ? err.message : '健康检查失败'
  } finally {
    checking.value = false
  }
}

onMounted(() => {
  void loadAll()
  void runCheck()
})
</script>

<style scoped>
.mc-page { display: flex; flex-direction: column; gap: 16px; }
.mc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.eyebrow { font-size: 12px; letter-spacing: .12em; color: var(--text-tertiary); text-transform: uppercase; }
.mc-head h1 { margin: 4px 0 4px; font-size: 22px; }
.mc-head p { margin: 0; color: var(--text-secondary); font-size: 13.5px; }
.mc-head-actions { display: flex; gap: 8px; }

.mc-stats { display: flex; gap: 28px; flex-wrap: wrap; margin-bottom: 4px; }
.mc-stats div { display: flex; flex-direction: column; }
.mc-stats b { font-size: 22px; font-variant-numeric: tabular-nums; }
.mc-stats span { font-size: 11.5px; color: var(--text-tertiary); }

.mc-channels { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.mc-channel { border: 1px solid var(--border-subtle); border-radius: 12px; padding: 12px 14px; background: var(--bg-card); }
.mc-channel.bad { border-color: color-mix(in srgb, var(--danger) 40%, var(--border-subtle)); }
.mc-channel-top { display: flex; align-items: center; gap: 8px; }
.mc-channel-top b { font-size: 13px; flex: 1 1 auto; min-width: 0; }
.mc-dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.mc-dot.ok { background: var(--accent-success); }
.mc-dot.bad { background: var(--danger); }
.mc-dot.idle { background: var(--text-tertiary); }
.mc-latency { font-size: 11.5px; color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
.mc-channel-msg { margin: 8px 0 6px; font-size: 12.5px; line-height: 1.55; color: var(--text-secondary); }
.mc-channel-meta { display: flex; gap: 10px; font-size: 11.5px; color: var(--text-tertiary); flex-wrap: wrap; }

.mc-section-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.mc-section-head h2 { font-size: 16px; margin: 0; }
.mc-section-head span { font-size: 12px; color: var(--text-tertiary); }
.mc-group { margin-bottom: 14px; }
.mc-group h3 { font-size: 13.5px; margin: 0 0 6px; }
.mc-group h3 small { color: var(--text-tertiary); font-weight: 400; margin-left: 6px; }
.mc-table { border: 1px solid var(--border-subtle); border-radius: 12px; overflow: hidden; background: var(--bg-card); }
.mc-row { display: grid; grid-template-columns: 220px 70px 80px 70px minmax(0, 1fr); gap: 10px; padding: 9px 12px; border-bottom: 1px solid var(--border-subtle); font-size: 12.5px; align-items: center; }
.mc-row:last-child { border-bottom: 0; }
.mc-row-head { background: var(--bg-elevated); color: var(--text-tertiary); font-size: 11.5px; }
.mc-name { display: flex; flex-direction: column; min-width: 0; }
.mc-name b { font-size: 12.8px; }
.mc-name small { font: 11px/1.4 var(--font-mono); color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; }
.mc-tag { font-size: 11px; padding: 1px 7px; border-radius: 5px; background: var(--bg-elevated); color: var(--text-secondary); }
.mc-tag.perm-write { background: var(--t-profiles); color: var(--c-profiles); }
.mc-tag.perm-danger { background: var(--t-stress); color: var(--c-stress); }
.mc-risk, .mc-timeout { color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
.mc-desc { color: var(--text-secondary); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.mc-empty { color: var(--text-tertiary); font-size: 13px; padding: 24px 0; text-align: center; }
.mc-note { margin-top: 6px; padding: 12px 14px; border: 1px dashed var(--border-subtle); border-radius: 12px; font-size: 12.5px; line-height: 1.6; color: var(--text-secondary); }

@media (max-width: 900px) {
  .mc-row { grid-template-columns: 1fr 60px 60px; }
  .mc-row span:nth-child(4), .mc-row span:nth-child(5) { display: none; }
}
</style>
