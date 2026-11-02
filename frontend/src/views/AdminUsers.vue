<template>
  <div class="users-admin-page">
    <!-- U5 顶部：权限说明条 + 4 维 KPI 统计卡（对齐原型 admin-users.html 70-95） -->
    <div class="row-between">
      <div class="info-strip" style="margin: 0; padding: 6px 14px; border-radius: 8px">
        单一角色「成员（Member）」，全员同权。所有人均具备发起评测、数据集管理与调度观测能力。
      </div>
    </div>

    <div class="kpi-grid" style="--glow-c: var(--c-users)">
      <div class="kpi">
        <div class="kpi-num num">{{ users.length }}</div>
        <div class="kpi-label">成员总数</div>
      </div>
      <div class="kpi">
        <div class="kpi-num num">{{ activeCount }}</div>
        <div class="kpi-label">正常使用</div>
      </div>
      <div class="kpi">
        <div class="kpi-num num" :style="disabledCount > 0 ? 'color: var(--accent-warning)' : ''">{{ disabledCount }}</div>
        <div class="kpi-label">已停用账号</div>
      </div>
      <div class="kpi">
        <div class="kpi-num num">{{ activeMembersText }}</div>
        <div class="kpi-label">24h 登录活跃</div>
      </div>
    </div>

    <!-- U6 主内容双栏：左主栏成员列表 + 右 340px 安全监控侧栏 -->
    <div class="users-grid">
      <!-- 左主栏：成员列表与即时筛选 -->
      <div class="panel glow" style="--glow-c: var(--c-users)">
        <div class="panel-title">
          <div class="row">
            <span>平台成员账号列表</span>
            <span class="mono" style="font-size: 12px; color: var(--text-tertiary)">({{ filteredUsers.length }} / {{ users.length }} 个成员)</span>
          </div>

          <div class="row">
            <!-- 即时搜索与状态筛选（对齐原型 admin-users.html） -->
            <input
              v-model="searchKeyword"
              class="input"
              style="width: 200px"
              placeholder="搜索用户名…"
            />
            <select v-model="statusFilter" class="select" style="width: 120px">
              <option value="all">全部状态</option>
              <option value="active">正常</option>
              <option value="disabled">已停用</option>
            </select>
            <button class="btn btn-primary btn-sm" @click="showUserModal = true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
              <span>开通新成员</span>
            </button>

            <button class="btn btn-secondary btn-sm" :disabled="loading" @click="loadPage">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
              </svg>
              <span>刷新</span>
            </button>
          </div>
        </div>

        <table class="ds-table">
          <thead>
            <tr>
              <th>成员信息</th>
              <th style="width: 130px">权限与角色</th>
              <th style="width: 110px">账号状态</th>
              <th style="width: 130px">最近登录 (IP)</th>
              <th style="width: 120px">开户时间</th>
              <th style="width: 150px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="u in filteredUsers" :key="u.id">
              <!-- U7 成员单元格双行结构：圆形头像 + 用户名 /（显示名·邮箱） -->
              <td>
                <div class="user-cell">
                  <div class="avatar-circle">{{ u.username.charAt(0).toUpperCase() }}</div>
                  <div class="user-name-box">
                    <span class="user-uname">{{ u.username }}</span>
                    <!-- 契约 AuthUser 暂无 display_name/email 字段，兜底展示「未完善资料」 -->
                    <span class="user-dname">{{ userSubText(u) }}</span>
                  </div>
                </div>
              </td>
              <td>
                <span class="tag-soft">成员 · 全员同权</span>
              </td>
              <td>
                <!-- U8 状态徽标：正常 succeeded / 停用 cancelled，均带呼吸点 -->
                <span v-if="!u.disabled" class="badge badge-succeeded"><i class="bdot"></i>正常</span>
                <span v-else class="badge badge-cancelled"><i class="bdot"></i>已停用</span>
              </td>
              <td class="small tertiary mono">
                <!-- 契约无 last_login_at/last_login_ip 字段，无数据显 — -->
                {{ lastLoginText(u) }}
              </td>
              <td class="mono" style="font-size: 12px; color: var(--text-tertiary)">
                {{ formatDate(u.created_at) }}
              </td>
              <td style="text-align: right">
                <div class="row" style="justify-content: flex-end; gap: 4px">
                  <button class="link-btn" @click="openResetPassword(u)">重置密码</button>
                  <button
                    class="link-btn"
                    :class="u.disabled ? '' : 'danger'"
                    @click="handleToggleStatus(u)"
                  >
                    {{ u.disabled ? '启用' : '停用' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 右栏：活动摘要、登录分布与审计都来自已有查询接口 -->
      <div class="section-gap" style="gap: 16px">
        <div class="panel glow" style="--glow-c: var(--c-users); padding: 16px 18px">
          <div class="panel-title" style="margin-bottom: 10px">近 24 小时</div>
          <div v-if="activityLoading && !activity" class="small tertiary">正在统计近 24 小时…</div>
          <div v-else-if="activityError" class="small">
            {{ activityError }}
            <button class="link-btn" @click="loadActivity">重试</button>
          </div>
          <div v-else class="section-gap" style="gap: 8px">
            <div class="row-between small"><span class="tertiary">活跃成员</span><b class="num">{{ kpiText(activity?.kpis.active_members) }}</b></div>
            <div class="row-between small"><span class="tertiary">新开通</span><b class="num">{{ kpiText(activity?.kpis.new_members) }}</b></div>
            <div class="row-between small"><span class="tertiary">新建任务</span><b class="num">{{ kpiText(activity?.kpis.total_tasks) }}</b></div>
            <div class="row-between small"><span class="tertiary">已停用</span><b class="num">{{ kpiText(activity?.kpis.disabled_members) }}</b></div>
          </div>
        </div>

        <div class="panel glow" style="--glow-c: var(--c-users); padding: 16px 18px">
          <div class="panel-title" style="margin-bottom: 8px">24h 登录活跃分布</div>
          <div v-if="activityError" class="small tertiary" style="margin-bottom: 8px">登录分布暂时不可用</div>
          <div v-else-if="activityLoading && !activity" class="small tertiary" style="margin-bottom: 8px">正在读取登录分布…</div>
          <div v-else-if="!loginBars.length" class="small tertiary" style="margin-bottom: 8px">暂无登录分布</div>
          <svg v-else width="100%" height="72" viewBox="0 0 280 72" preserveAspectRatio="none" role="img" aria-label="24 小时登录次数" style="margin-bottom: 8px">
            <rect
              v-for="(b, i) in loginBars"
              :key="i"
              :x="b.x"
              :y="b.y"
              :width="b.w"
              :height="b.h"
              rx="2"
              fill="var(--c-users)"
              :opacity="b.v ? 0.8 : 0.18"
            >
              <title>{{ b.title }}</title>
            </rect>
          </svg>
          <div class="row-between small">
            <span class="tertiary">登录成功 <b class="num" style="color: var(--accent-success)">{{ kpiText(activity?.kpis.login_count) }} 次</b></span>
            <span class="tertiary">登录失败 <b class="num" style="color: var(--accent-error)">{{ kpiText(activity?.kpis.login_failed) }} 次</b></span>
          </div>
        </div>

        <div class="panel glow" style="--glow-c: var(--c-users); padding: 16px 18px">
          <div class="panel-title" style="margin-bottom: 12px">近期合规审计轨迹</div>
          <div v-if="auditError" class="small">
            {{ auditError }}
            <button class="link-btn" @click="loadAudits">重试</button>
          </div>
          <div v-else-if="auditLoading" class="small tertiary">正在读取审计记录…</div>
          <div v-else-if="auditLogs.length === 0" class="small tertiary">最近没有审计记录</div>
          <div v-else class="timeline">
            <div v-for="item in auditLogs" :key="item.id" class="tl-item" :class="auditTone(item)">
              <div class="tl-time mono">{{ formatAuditTime(item.at) }}</div>
              <div class="small">{{ auditText(item) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗 -->
    <UserModal
      v-model:show="showUserModal"
      @success="loadPage"
    />

    <ResetPasswordModal
      v-model:show="showResetModal"
      :user="selectedUser"
      @success="loadPage"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useMessage, useDialog } from 'naive-ui'
import { api } from '../api/http'
import type { AuditLogEntry, AuthUser, UserActivitySummary } from '../api/types'
import UserModal from '../components/modals/UserModal.vue'
import ResetPasswordModal from '../components/modals/ResetPasswordModal.vue'
import { formatDate } from '../utils/format'

const message = useMessage()
const dialog = useDialog()

const users = ref<AuthUser[]>([])
const loading = ref(false)

// 搜索关键词与状态筛选（原型支持用户名/姓名/邮箱即时搜索，当前契约仅 username 字段）
const searchKeyword = ref('')
const statusFilter = ref<'all' | 'active' | 'disabled'>('all')

const filteredUsers = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  return users.value.filter(u => {
    if (kw && !u.username.toLowerCase().includes(kw)) return false
    if (statusFilter.value === 'active' && u.disabled) return false
    if (statusFilter.value === 'disabled' && !u.disabled) return false
    return true
  })
})

// U5 KPI：正常 / 已停用计数（成员总数直接取 users.length）
const activeCount = computed(() => users.value.filter(u => !u.disabled).length)
const disabledCount = computed(() => users.value.length - activeCount.value)

const showUserModal = ref(false)
const showResetModal = ref(false)
const selectedUser = ref<AuthUser | null>(null)

/** U7 成员副行文案：契约暂无 display_name/email，兜底「未完善资料」 */
function userSubText(u: AuthUser): string {
  const ext = u as AuthUser & { display_name?: string; email?: string }
  return ext.display_name || ext.email || '未完善资料'
}

/** U7 最近登录列：契约暂无 last_login_* 字段，无数据显 — */
function lastLoginText(u: AuthUser): string {
  const ext = u as AuthUser & { last_login_ip?: string; last_login_at?: string }
  if (!ext.last_login_at && !ext.last_login_ip) return '—'
  const ip = ext.last_login_ip || '—'
  const at = ext.last_login_at ? new Date(ext.last_login_at).toLocaleString('zh-CN', { hour12: false }) : ''
  return at ? `${ip} · ${at}` : ip
}

/* ─── 右栏：活动摘要、登录柱与审计轨迹均来自服务端 ─── */

const activity = ref<UserActivitySummary | null>(null)
const activityLoading = ref(true)
const activityError = ref('')
const auditLogs = ref<AuditLogEntry[]>([])
const auditLoading = ref(true)
const auditError = ref('')

/** 统计尚未返回或失败时显示占位，避免把 0 和「还没读到」混在一起。 */
function kpiText(value: number | undefined): string {
  return value === undefined || Number.isNaN(value) ? '—' : String(value)
}

const activeMembersText = computed(() => kpiText(activity.value?.kpis.active_members))

/** 把登录桶画进 280×72 视窗；柱数随区间小时数变化。 */
const loginBars = computed(() => {
  const buckets = activity.value?.login_buckets ?? []
  if (!buckets.length) return []
  const max = Math.max(...buckets.map((bucket) => bucket.count), 1)
  const width = 280 / buckets.length
  return buckets.map((bucket, index) => {
    const bar = Math.max(2, (bucket.count / max) * 60)
    const hour = formatAuditTime(bucket.ts)
    return {
      v: bucket.count,
      title: `${hour} · ${bucket.count} 次`,
      x: +(index * width + 1.5).toFixed(1),
      y: +(68 - bar).toFixed(1),
      w: +Math.max(width - 3, 1).toFixed(1),
      h: +bar.toFixed(1),
    }
  })
})

const ACTION_LABELS: Record<string, string> = {
  login: '登录',
  login_failed: '登录失败',
  user_create: '开通账号',
  user_update: '更新资料',
  user_status_change: '变更账号状态',
  password_reset: '重置密码',
  key_change: '更新协议档密钥',
  profile_update: '更新协议档',
  profile_delete: '删除协议档',
  task_create: '创建任务',
  task_cancel: '取消任务',
  task_rerun: '复制任务',
  task_quota_rejected: '任务配额拒绝',
  case_set_create: '新建用例集',
  case_set_confirm: '确认用例入库',
  case_set_cancel: '废弃用例草稿',
  whitelist_change: '变更压测白名单',
  agent_skill_update: '更新技能文件',
}

function actorName(actorId: string | null): string {
  if (!actorId) return '系统'
  return users.value.find((user) => user.id === actorId)?.username || actorId.slice(0, 8)
}

function auditText(entry: AuditLogEntry): string {
  const label = ACTION_LABELS[entry.action] || entry.action
  return `${label} · ${actorName(entry.actor_id)}`
}

function auditTone(entry: AuditLogEntry): 'info' | 'warn' | 'err' {
  if (entry.action === 'login_failed' || entry.action === 'task_quota_rejected') return 'err'
  if (
    entry.action === 'user_status_change'
    || entry.action === 'password_reset'
    || entry.action.endsWith('_delete')
    || entry.action.endsWith('_cancel')
  ) return 'warn'
  return 'info'
}

function formatAuditTime(at: string): string {
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return at
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

async function loadActivity() {
  activityLoading.value = true
  activityError.value = ''
  try {
    activity.value = await api.users.activitySummary()
  } catch (err: any) {
    activity.value = null
    activityError.value = err.message || '加载登录活跃失败'
  } finally {
    activityLoading.value = false
  }
}

async function loadAudits() {
  auditLoading.value = true
  auditError.value = ''
  try {
    const page = await api.admin.listAuditLogs({ limit: 30 })
    auditLogs.value = page.items || []
  } catch (err: any) {
    auditLogs.value = []
    auditError.value = err.message || '加载审计记录失败'
  } finally {
    auditLoading.value = false
  }
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await api.users.list()
  } catch (err: any) {
    message.error(err.message || '加载用户列表失败')
  } finally {
    loading.value = false
  }
}

/** 成员表、活跃统计和审计互不阻塞，单侧失败仍保留其余结果。 */
function loadPage() {
  void loadUsers()
  void loadActivity()
  void loadAudits()
}

function openResetPassword(user: AuthUser) {
  selectedUser.value = user
  showResetModal.value = true
}

function handleToggleStatus(user: AuthUser) {
  const targetDisabled = !user.disabled
  const actionText = targetDisabled ? '停用' : '启用'

  // 最后一名正常账号保护：停用后平台将无人可登录，直接拦截（对齐原型）
  if (targetDisabled && users.value.filter(u => !u.disabled).length <= 1) {
    message.error('最后一名正常账号不可停用')
    return
  }

  dialog.warning({
    title: `${actionText}用户「${user.username}」？`,
    content: targetDisabled
      ? '停用后该用户将无法登录平台，正在运行的任务仍将保留。'
      : '启用后该用户可恢复正常登录。',
    positiveText: `确认${actionText}`,
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.users.toggleStatus(user.id, targetDisabled)
        user.disabled = targetDisabled
        message.success(`已${actionText}该账号`)
        void loadActivity()
        void loadAudits()
      } catch (err: any) {
        message.error(err.message || `${actionText}失败`)
      }
    },
  })
}

onMounted(loadPage)
</script>

<style scoped>
.users-admin-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
/* U6 双栏布局：左主栏 + 右 340px 侧栏（迁移自原型 .users-grid，侧栏宽度按任务要求 340px） */
.users-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  align-items: flex-start;
}
@media (max-width: 1100px) {
  .users-grid {
    grid-template-columns: 1fr;
  }
}
/* U7 成员单元格：圆形头像 + 双行名称（迁移自原型 .avatar-circle / .user-cell） */
.avatar-circle {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--c-users) 20%, var(--bg-main));
  color: var(--c-users);
  font-weight: 700;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--c-users) 40%, transparent);
  flex: 0 0 auto;
}
.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.user-name-box {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.user-uname {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}
.user-dname {
  font-size: 11px;
  color: var(--text-secondary);
}
/* 审计时间线 warn 类型节点色（base.css 仅定义 ok/err/info，此处补齐原型 warn 态） */
.tl-item.warn::before {
  border-color: var(--accent-warning);
}
</style>
