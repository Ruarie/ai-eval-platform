<template>
  <div class="app" :class="{ folded: theme.collapsed }">
    <!-- 侧边栏 -->
    <div v-if="mobileNavOpen" class="mobile-nav-backdrop" aria-hidden="true" @click="closeMobileNavigation"></div>
    <aside id="platform-nav" class="sidebar" :class="{ 'mobile-open': mobileNavOpen }" :inert="isMobileViewport && !mobileNavOpen">
      <div class="sidebar-head">
        <router-link class="brand" to="/agent" aria-label="AI 测试平台首页" @click="closeMobileNavigation">
          <img class="brand-mark" src="/favicon.svg" width="34" height="34" alt="" />
          <span class="brand-name">AI 测试平台</span>
        </router-link>
        <button ref="mobileCloseRef" class="topbar-icon-btn mobile-nav-close" type="button" aria-label="关闭导航菜单" @click="closeMobileNavigation">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <path d="m6 6 12 12M6 18 18 6" />
          </svg>
        </button>
      </div>

      <nav class="nav" aria-label="主导航">
        <!-- 分组导航：所有业务路由必须有入口，历史页面显式标注，避免出现只能手输 URL 的孤立页。 -->
        <template v-for="group in visibleNavGroups" :key="group.title">
          <div class="nav-group">{{ group.title }}</div>
          <router-link
            v-for="item in group.items"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :class="{ active: isRouteActive(item.path) }"
            :aria-label="item.label"
            :title="item.label"
            @click="closeMobileNavigation"
          >
            <span class="nav-ico" aria-hidden="true">
              <component :is="item.icon" />
            </span>
            <span class="nav-label">{{ item.label }}</span>
          </router-link>
        </template>
      </nav>

      <!-- 侧边栏底部：折叠按钮（对齐原型 sidebar-fold）+ 用户信息 -->
      <div class="sidebar-foot">
        <button class="sidebar-fold" type="button" :title="foldLabel" :aria-label="foldLabel" :aria-expanded="!theme.collapsed" @click="theme.toggleCollapsed()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m14 6-6 6 6 6" />
          </svg>
          <span class="fold-label">{{ foldLabel }}</span>
        </button>
        <div class="user-card">
          <div class="avatar" aria-hidden="true">{{ userInitial }}</div>
          <div class="user-meta">
            <div class="user-name">{{ userName }}</div>
            <div class="user-role">{{ roleLabel }}</div>
          </div>
          <button class="logout-btn" type="button" @click="handleLogout" title="退出登录" aria-label="退出登录">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
          </button>
        </div>
      </div>
    </aside>

    <main class="main" :inert="mobileNavOpen">
      <!-- 顶栏 -->
      <header class="topbar">
        <button ref="mobileToggleRef" class="topbar-icon-btn mobile-nav-toggle" type="button" title="打开导航菜单" aria-label="打开导航菜单" aria-controls="platform-nav" :aria-expanded="mobileNavOpen" @click="openMobileNavigation">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
            <line x1="4" y1="6" x2="20" y2="6" />
            <line x1="4" y1="12" x2="20" y2="12" />
            <line x1="4" y1="18" x2="20" y2="18" />
          </svg>
        </button>
        <component :is="route.meta.titleInTopbar ? 'h1' : 'div'" class="topbar-title">{{ currentTitle }}</component>

        <!-- 右侧操作栏 -->
        <div class="topbar-actions">
          <!-- 全局搜索：Cmd/Ctrl+K 命令面板 -->
          <button class="topbar-search-btn" type="button" :title="`全局搜索（${searchShortcut}）`" aria-label="全局搜索" @click="searchRef?.open()">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
              <circle cx="11" cy="11" r="7"></circle>
              <path d="m20 20-3.5-3.5"></path>
            </svg>
            <span class="topbar-search-text">搜索</span>
            <kbd class="topbar-search-kbd" aria-hidden="true">{{ searchShortcut }}</kbd>
          </button>

          <NotificationBell />

          <span v-if="api.isMock()" class="data-source-badge" title="示例模式使用本地数据">示例数据</span>

          <!-- 主题切换 -->
          <button class="topbar-icon-btn" @click="theme.toggle()" :title="theme.mode === 'light' ? '切换深色模式' : '切换浅色模式'">
            <svg v-if="theme.mode === 'light'" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
            <svg v-else width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
          </button>

          <!-- 改密入口 -->
          <button class="topbar-icon-btn" @click="showChangePwd = true" title="修改密码">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
              <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
            </svg>
          </button>
        </div>
      </header>

      <!-- 视图呈现区 -->
      <section class="content" :class="{ flush: isFlushView }">
        <router-view />
      </section>
    </main>

    <!-- 修改密码弹窗（V1.83 起仅普通自助改密，不再有首次强制改密形态） -->
    <n-modal v-model:show="showChangePwd" preset="card" title="修改登录密码" style="width: 440px">
      <n-form ref="pwdFormRef" :model="pwdForm" label-placement="left" label-width="80">
        <n-form-item label="原密码">
          <n-input v-model:value="pwdForm.oldPassword" type="password" show-password-on="click" placeholder="输入当前密码" />
        </n-form-item>
        <n-form-item label="新密码">
          <n-input v-model:value="pwdForm.newPassword" type="password" show-password-on="click" placeholder="至少 8 位，包含字母与数字" />
        </n-form-item>
        <n-form-item label="确认密码">
          <n-input v-model:value="pwdForm.confirmPassword" type="password" show-password-on="click" placeholder="再次输入新密码" />
        </n-form-item>
      </n-form>
      <template #footer>
        <div style="display: flex; justify-content: flex-end; gap: 8px">
          <n-button @click="showChangePwd = false">取消</n-button>
          <n-button type="primary" :loading="pwdLoading" @click="submitChangePassword">确认修改</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 全局搜索命令面板：Ctrl/Cmd+K 打开，八类资产按权限检索。 -->
    <GlobalSearch ref="searchRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import { api } from '../api/http'
import GlobalSearch from '../components/search/GlobalSearch.vue'
import NotificationBell from '../components/notifications/NotificationBell.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()
const theme = useThemeStore()
const searchRef = ref<InstanceType<typeof GlobalSearch> | null>(null)

const showChangePwd = ref(false)
const pwdLoading = ref(false)
const mobileNavOpen = ref(false)
const mobileToggleRef = ref<HTMLButtonElement | null>(null)
const mobileCloseRef = ref<HTMLButtonElement | null>(null)
const mobileViewport = window.matchMedia('(max-width: 700px)')
const isMobileViewport = ref(mobileViewport.matches)
const searchShortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘K' : 'Ctrl K'
const pwdForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

// 图标简易渲染
const IconAgent = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M12 3a5 5 0 0 1 5 5v1a5 5 0 0 1-5 5 5 5 0 0 1-5-5V8a5 5 0 0 1 5-5Z' }),
    h('path', { d: 'M5 21c0-3.3 3.1-5 7-5s7 1.7 7 5' }),
  ])

const IconDispatch = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('circle', { cx: '12', cy: '12', r: '2.4' }),
    h('circle', { cx: '5', cy: '5', r: '1.8' }),
    h('circle', { cx: '19', cy: '5', r: '1.8' }),
    h('circle', { cx: '5', cy: '19', r: '1.8' }),
    h('circle', { cx: '19', cy: '19', r: '1.8' }),
    h('path', { d: 'M6.4 6.4 10 10M13.9 10.1l3.7-3.7M6.4 17.6 10 14M13.9 13.9l3.7 3.7' }),
  ])

const IconTasks = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '4', y: '4', width: '16', height: '16', rx: '3' }),
    h('path', { d: 'M8 9h8M8 13h5' }),
  ])

const IconReports = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M5 20V10M12 20V4M19 20v-7' }),
  ])

const IconCases = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M9 11.5 11 14l4.5-5' }),
    h('rect', { x: '4', y: '4', width: '16', height: '16', rx: '3' }),
  ])

const IconProfiles = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '3', y: '5', width: '18', height: '14', rx: '3' }),
    h('path', { d: 'M7 10h4M7 14h7' }),
  ])

// 用例资产：归档盒 + 标签。
const IconAsset = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 7h16v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z' }),
    h('path', { d: 'M4 7 6 3h12l2 4M9 11h6' }),
  ])

// 用量：仪表盘 + 刻度。
const IconUsage = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 18a8 8 0 1 1 16 0' }),
    h('path', { d: 'M12 14 16 9M8 18h8' }),
    h('circle', { cx: '12', cy: '14', r: '1.2' }),
  ])

// 质量看板：柱状图 + 上升趋势。
const IconQuality = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 20V6M4 20h16' }),
    h('path', { d: 'M8 16v-4M12 16V8M16 16v-6M20 16v-2' }),
  ])

const IconUsers = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('circle', { cx: '9', cy: '8', r: '3.5' }),
    h('path', { d: 'M3.5 20c.6-3.2 2.9-5 5.5-5s4.9 1.8 5.5 5' }),
    h('path', { d: 'M16 8.5h5M18.5 6v5' }),
  ])

const IconWorkspaces = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z' }),
    h('path', { d: 'M9 13h6M12 10v6' }),
  ])

// 用户主动维护的记忆入口，与工作区同属个人数据域。
const IconMemories = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '5', y: '3', width: '15', height: '18', rx: '2' }),
    h('path', { d: 'M9 3v18M12 8h5M12 12h5M3 7h4M3 17h4' }),
  ])

// 知识库：文档索引、检索 Playground 与只读知识图谱的统一入口。
const IconKnowledge = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('ellipse', { cx: '12', cy: '6', rx: '7', ry: '3' }),
    h('path', { d: 'M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6' }),
    h('path', { d: 'M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6' }),
  ])

// 数据集：历史评测遗留资产，当前只读维护。
const IconDatasets = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '3', y: '4', width: '18', height: '16', rx: '2.5' }),
    h('path', { d: 'M3 9h18M9 9v11M15 9v11' }),
  ])

// 模型对比：历史 benchmark 只读对比页。
const IconCompare = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 7h11M4 7l3-3M4 7l3 3' }),
    h('path', { d: 'M20 17H9M20 17l-3-3M20 17l-3 3' }),
  ])

// 资源广场：四格 + 星标，表达"精选与榜单"。
const IconPlaza = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '3', y: '3', width: '8', height: '8', rx: '2' }),
    h('rect', { x: '13', y: '3', width: '8', height: '8', rx: '2' }),
    h('rect', { x: '3', y: '13', width: '8', height: '8', rx: '2' }),
    h('path', { d: 'M17 13v6M14 16h6' }),
  ])

// 能力：拼图块，表达"可组合的 Agent / Skill / Script / Rule"。
const IconCapability = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M9 3h6v3a2 2 0 0 0 2 2h4v6h-4a2 2 0 0 0-2 2v5H9v-5a2 2 0 0 0-2-2H3V9h4a2 2 0 0 0 2-2z' }),
  ])

// 脚本：终端提示符。
const IconScript = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('rect', { x: '3', y: '4', width: '18', height: '16', rx: '2.5' }),
    h('path', { d: 'm7 9 3 3-3 3M13 15h4' }),
  ])

// 规则：清单 + 勾选。
const IconRule = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M9 5h11M9 12h11M9 19h11' }),
    h('path', { d: 'm3 5 1.6 1.6L7 4M3 12l1.6 1.6L7 11M3 19l1.6 1.6L7 18' }),
  ])

// 技能：星形勋章。
const IconSkill = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('circle', { cx: '12', cy: '9', r: '6' }),
    h('path', { d: 'm9 14-1 7 4-2 4 2-1-7' }),
  ])

// MCP：插头，表达"连接外部能力"。
const IconMcp = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M9 3v5M15 3v5' }),
    h('path', { d: 'M6 8h12v3a6 6 0 0 1-12 0z' }),
    h('path', { d: 'M12 17v4' }),
  ])

// RAG：书页 + 检索放大镜。
const IconRag = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 5a2 2 0 0 1 2-2h6v18H6a2 2 0 0 1-2-2z' }),
    h('circle', { cx: '15.5', cy: '13.5', r: '3.5' }),
    h('path', { d: 'm18.2 16.2 2.3 2.3' }),
  ])

// 概览：仪表盘。
const IconOverview = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M4 19V9M10 19V5M16 19v-6M22 19H2' }),
  ])

// 审计：带勾的清单文档。
const IconAudit = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M6 3h9l4 4v14H6z' }),
    h('path', { d: 'M9 12h6M9 16h4' }),
  ])

// 治理：盾牌。
const IconGovern = () =>
  h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }, [
    h('path', { d: 'M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z' }),
    h('path', { d: 'm9 12 2 2 4-4' }),
  ])

const navGroups = [
  {
    title: '工作台',
    items: [
      { path: '/agent', label: '智能体', icon: IconAgent },
      { path: '/cases', label: '用例', icon: IconCases },
      { path: '/case-quality', label: '用例质量', icon: IconQuality },
      { path: '/usage', label: '用量中心', icon: IconUsage },
      { path: '/tasks', label: '任务中心', icon: IconTasks },
      { path: '/dispatch', label: '调度中心', icon: IconDispatch },
    ],
  },
  {
    title: '能力',
    items: [
      { path: '/plaza', label: '资源广场', icon: IconPlaza },
      { path: '/agents', label: 'Agent 中心', icon: IconCapability },
      { path: '/skills', label: 'Skills', icon: IconSkill },
      { path: '/scripts', label: 'Scripts', icon: IconScript },
      { path: '/rules', label: 'Rules', icon: IconRule },
      { path: '/rag', label: 'RAG 中心', icon: IconRag },
      { path: '/mcp', label: 'MCP 中心', icon: IconMcp },
    ],
  },
  {
    title: '资产与历史',
    items: [
      { path: '/case-assets', label: '用例资产', icon: IconAsset },
      // 历史数据集与模型对比仍可进入，但只做只读查询/维护，不再作为新建评测入口。
      { path: '/datasets', label: '历史数据集', icon: IconDatasets },
      // PRD 5.8 路由表包含 /kb；RAG 评测停用后仍保留检索与图谱能力。
      { path: '/kb', label: '知识库', icon: IconKnowledge },
      { path: '/reports', label: '历史报告', icon: IconReports },
      { path: '/model-compare', label: '模型对比', icon: IconCompare },
    ],
  },
  {
    title: '协作',
    items: [
      // F1（G1）：我的工作区（用户自管数据域；管理端清理视图已于 V1.79 下线）
      { path: '/workspaces', label: '我的工作区', icon: IconWorkspaces },
      { path: '/memories', label: '我的记忆', icon: IconMemories },
      { path: '/my-models', label: '我的模型', icon: IconProfiles },
    ],
  },
  {
    title: '管理',
    items: [
      { path: '/admin', label: '平台概览', icon: IconOverview, adminOnly: true },
      { path: '/admin/audit', label: '审计日志', icon: IconAudit, adminOnly: true },
      { path: '/admin/resources', label: '资源治理', icon: IconGovern, adminOnly: true },
      { path: '/admin/profiles', label: '模型管理', icon: IconProfiles, adminOnly: true },
      { path: '/admin/users', label: '账号', icon: IconUsers, adminOnly: true },
    ],
  },
]

/** 普通成员不渲染管理分组；管理端账号保留全部入口。 */
const visibleNavGroups = computed(() => navGroups
  .map((group) => ({
    ...group,
    items: group.items.filter((item) => !('adminOnly' in item && item.adminOnly) || auth.user?.role === 'admin'),
  }))
  .filter((group) => group.items.length > 0))

/** 当前路由激活状态匹配判定 */
function isRouteActive(itemPath: string): boolean {
  if (itemPath === '/agent') {
    return route.path === '/agent' || route.path.startsWith('/agent/')
  }
  // 管理后台的父级路由不做前缀匹配，否则 /admin/audit 会把「平台概览」也点亮。
  if (itemPath === '/admin') {
    return route.path === '/admin'
  }
  return route.path === itemPath || route.path.startsWith(itemPath + '/')
}

// 标题唯一来源是路由 meta（router/index.ts），此处不再做路径特判。
const currentTitle = computed(() => (route.meta.title as string) || 'AI 测试与评估平台')
const isFlushView = computed(() => route.path.startsWith('/agent'))

const userName = computed(() => auth.user?.display_name || auth.user?.username || '当前成员')
const userInitial = computed(() => Array.from(userName.value)[0].toUpperCase())
const foldLabel = computed(() => theme.collapsed ? '展开导航' : '收起导航')

/** 侧栏身份展示：按后端角色映射，避免管理员也显示成「平台成员」。 */
const roleLabel = computed(() => {
  const labels: Record<string, string> = {
    admin: '管理员',
    engineer: '工程师',
    readonly: '只读成员',
    member: '平台成员',
  }
  return labels[auth.user?.role || 'member'] || '平台成员'
})

async function openMobileNavigation() {
  mobileNavOpen.value = true
  await nextTick()
  // 等抽屉和主区的 inert 更新后，再交接键盘焦点。
  requestAnimationFrame(() => {
    if (mobileNavOpen.value) mobileCloseRef.value?.focus({ preventScroll: true })
  })
}

async function closeMobileNavigation() {
  if (!mobileNavOpen.value) return
  mobileNavOpen.value = false
  await nextTick()
  requestAnimationFrame(() => {
    if (isMobileViewport.value && !mobileNavOpen.value) mobileToggleRef.value?.focus({ preventScroll: true })
  })
}

function dismissMobileNavigation(event: KeyboardEvent) {
  if (event.key === 'Escape' && mobileNavOpen.value && !event.defaultPrevented) void closeMobileNavigation()
}

function handleViewportChange(event: MediaQueryListEvent) {
  isMobileViewport.value = event.matches
  if (!event.matches) void closeMobileNavigation()
}

onMounted(() => {
  mobileViewport.addEventListener('change', handleViewportChange)
  window.addEventListener('keydown', dismissMobileNavigation)
})
onBeforeUnmount(() => {
  mobileViewport.removeEventListener('change', handleViewportChange)
  window.removeEventListener('keydown', dismissMobileNavigation)
})

function handleLogout() {
  dialog.warning({
    title: '退出登录？',
    content: '退出登录后，正在运行的用例生成任务不会停止。',
    positiveText: '确认退出',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await auth.logout()
        message.success('已退出登录')
      } catch {
        message.warning('退出请求失败，已清除本地登录状态')
      }
      router.push('/login')
    },
  })
}

async function submitChangePassword() {
  if (!pwdForm.value.newPassword || pwdForm.value.newPassword.length < 8) {
    message.warning('新密码长度不能少于 8 位')
    return
  }
  if (pwdForm.value.newPassword !== pwdForm.value.confirmPassword) {
    message.warning('两次输入的新密码不一致')
    return
  }

  pwdLoading.value = true
  try {
    await auth.changePassword(pwdForm.value.newPassword, pwdForm.value.oldPassword)
    message.success('密码修改成功')
    showChangePwd.value = false
    pwdForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
  } catch (err: any) {
    message.error(err.message || '密码修改失败')
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.app {
  display: grid;
  grid-template-columns: var(--sidebar-w) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  height: 100vh;
  height: 100dvh;
  transition: grid-template-columns var(--ease-shell);
}
.app.folded {
  grid-template-columns: var(--sidebar-w-fold) minmax(0, 1fr);
}

.sidebar {
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: var(--space-3);
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border-subtle);
}
.sidebar-head {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  min-height: 44px;
  margin-bottom: var(--space-2);
  padding-inline: var(--space-1);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  border-radius: var(--radius-lg);
}
.brand-mark {
  flex: 0 0 34px;
}
.brand-name {
  color: var(--text-primary);
  font: 700 15px/1.25 var(--font-display);
  white-space: nowrap;
}

.nav {
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 2px;
  min-height: 0;
  overflow: auto;
  padding: 2px;
}
.nav-group {
  flex: 0 0 auto;
  margin: 12px 8px 4px;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 600;
}
.nav-item {
  display: flex;
  flex: 0 0 35px;
  align-items: center;
  gap: 10px;
  padding-inline: 9px;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.15s ease, color 0.15s ease;
}
.nav-item:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.nav-item.active {
  border-color: color-mix(in srgb, var(--c-agent) 16%, var(--border-subtle));
  background: var(--t-agent);
  color: var(--c-agent);
  font-weight: 650;
}
.nav-ico,
.nav-ico svg {
  width: 17px;
  height: 17px;
}
.nav-ico {
  display: grid;
  flex-shrink: 0;
  place-items: center;
}

.sidebar-foot {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: var(--space-1);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border-subtle);
}
.sidebar-fold,
.logout-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 34px;
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  background: transparent;
  color: var(--text-secondary);
}
.sidebar-fold {
  padding: 4px 9px;
  font-size: 12px;
}
.sidebar-fold:hover,
.logout-btn:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.sidebar-fold svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  transition: transform var(--ease-shell);
}
.user-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 42px;
  padding: 4px;
}
.avatar {
  display: grid;
  width: 29px;
  height: 29px;
  flex: 0 0 29px;
  place-items: center;
  border-radius: var(--radius-lg);
  background: var(--t-agent);
  color: var(--c-agent);
  font-size: 12px;
  font-weight: 700;
}
.user-meta {
  flex: 1;
  min-width: 0;
}
.user-name {
  overflow: hidden;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-role {
  color: var(--text-tertiary);
  font-size: 11px;
}
.logout-btn {
  justify-content: center;
  width: 34px;
  flex-shrink: 0;
  padding: 0;
}
.logout-btn:hover {
  color: var(--accent-error);
}

.main {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  background: var(--bg-main);
}
.topbar {
  position: relative;
  z-index: 5;
  display: flex;
  flex: 0 0 var(--topbar-h);
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
  padding-inline: var(--space-5);
  border-bottom: 1px solid var(--border-subtle);
  background: var(--bg-main);
}
.topbar-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  font: 650 17px/1.3 var(--font-display);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: var(--space-2);
}
.topbar-search-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 0 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}
.topbar-search-btn:hover {
  border-color: var(--c-agent);
  color: var(--c-agent);
}
.topbar-search-kbd {
  padding: 1px 4px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--bg-main);
  color: var(--text-tertiary);
  font: 600 10px/1.5 var(--font-mono);
}
.data-source-badge {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--accent-warning) 10%, var(--bg-main));
  color: var(--accent-warning);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.content {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: var(--space-5);
}
.content.flush {
  display: flex;
  flex-direction: column;
  padding: 0;
}
.mobile-nav-backdrop,
.mobile-nav-toggle,
.mobile-nav-close {
  display: none;
}

/* 自动折叠区间只显示图标，退出登录仍可使用。 */
@media (min-width: 701px) {
  .app.folded .sidebar-head,
  .app.folded .sidebar-fold,
  .app.folded .nav-item {
    justify-content: center;
    padding-inline: 0;
  }
  .app.folded .brand-name,
  .app.folded .nav-label,
  .app.folded .user-meta,
  .app.folded .fold-label {
    display: none;
  }
  .app.folded .sidebar-fold svg {
    transform: rotate(180deg);
  }
  .app.folded .nav-group {
    height: 1px;
    margin: 8px;
    overflow: hidden;
    background: var(--border-subtle);
    font-size: 0;
  }
  .app.folded .user-card {
    justify-content: center;
    padding: 0;
  }
  .app.folded .avatar {
    display: none;
  }
}
@media (min-width: 701px) and (max-width: 1060px) {
  .app,
  .app.folded {
    grid-template-columns: var(--sidebar-w-fold) minmax(0, 1fr);
  }
  .sidebar-head,
  .nav-item,
  .user-card {
    justify-content: center;
    padding-inline: 0;
  }
  .brand-name,
  .nav-label,
  .user-meta,
  .sidebar-fold,
  .avatar {
    display: none;
  }
  .nav-group {
    height: 1px;
    margin: 8px;
    overflow: hidden;
    background: var(--border-subtle);
    font-size: 0;
  }
  .content {
    padding: var(--space-4);
  }
}

@media (max-width: 700px) {
  .app,
  .app.folded {
    grid-template-columns: minmax(0, 1fr);
  }
  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    z-index: 22;
    width: min(280px, calc(100vw - 40px));
    transform: translateX(-100%);
    transition: transform var(--ease-shell);
    padding-bottom: max(var(--space-3), env(safe-area-inset-bottom));
  }
  .sidebar.mobile-open {
    transform: translateX(0);
  }
  .sidebar-fold {
    display: none;
  }
  .mobile-nav-backdrop {
    position: fixed;
    inset: 0;
    z-index: 21;
    display: block;
    background: var(--overlay);
  }
  .mobile-nav-toggle,
  .mobile-nav-close {
    display: grid;
    flex-shrink: 0;
  }
  .topbar {
    gap: 6px;
    padding-inline: var(--space-2);
  }
  .topbar-title {
    font-size: 15px;
  }
  .topbar-actions {
    gap: 3px;
  }
  .topbar-search-btn {
    width: 34px;
    justify-content: center;
    padding: 0;
  }
  .topbar-search-text,
  .topbar-search-kbd {
    display: none;
  }
  .content {
    padding: var(--space-3);
    padding-bottom: max(var(--space-3), env(safe-area-inset-bottom));
  }
}
</style>
