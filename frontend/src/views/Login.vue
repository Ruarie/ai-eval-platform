<template>
  <main class="login-wrapper">
    <header class="login-header">
      <span class="login-brand">AI 测试与评估平台</span>
      <span class="service-status" :class="serviceStatus" role="status">
        <span class="service-dot" aria-hidden="true"></span>
        {{ serviceLabels[serviceStatus] }}
      </span>
    </header>

    <div class="login-main-card">
      <section class="login-intro" aria-labelledby="login-intro-title">
        <h2 id="login-intro-title">从需求到<br />可审核的测试用例</h2>
        <ol class="login-steps">
          <li>
            <span class="step-index" aria-hidden="true">01</span>
            <div><b>提交需求</b><p>描述功能或上传需求文档。</p></div>
          </li>
          <li>
            <span class="step-index" aria-hidden="true">02</span>
            <div><b>生成用例</b><p>由 Agent 整理测试场景和预期结果。</p></div>
          </li>
          <li>
            <span class="step-index" aria-hidden="true">03</span>
            <div><b>审核入库</b><p>核对覆盖范围，确认后纳入用例集。</p></div>
          </li>
        </ol>
      </section>

      <section class="login-panel" aria-labelledby="login-title">
        <header class="login-panel-header">
          <h1 id="login-title">登录工作台</h1>
          <p>使用团队分配的账号登录。</p>
        </header>

        <form class="login-form" novalidate @submit.prevent="submitLogin">
          <div class="form-field">
            <label for="login-username">用户名</label>
            <input
              id="login-username"
              ref="usernameInputRef"
              v-model="username"
              type="text"
              class="native-input"
              placeholder="请输入用户名"
              autocomplete="username"
              required
              :disabled="loading"
              :aria-invalid="Boolean(inputErrors.username)"
              :aria-describedby="inputErrors.username ? 'login-username-error' : undefined"
              @input="clearFieldError('username')"
            />
            <p v-if="inputErrors.username" id="login-username-error" class="field-error-text">{{ inputErrors.username }}</p>
          </div>

          <div class="form-field">
            <label for="login-password">密码</label>
            <div class="password-field">
              <input
                id="login-password"
                ref="passwordInputRef"
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                class="native-input"
                placeholder="请输入密码"
                autocomplete="current-password"
                required
                :disabled="loading"
                :aria-invalid="Boolean(inputErrors.password)"
                :aria-describedby="inputErrors.password ? 'login-password-error' : undefined"
                @input="clearFieldError('password')"
              />
              <button
                type="button"
                class="password-toggle-btn"
                :aria-label="showPassword ? '隐藏密码' : '显示密码'"
                :title="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
                  <circle cx="12" cy="12" r="3" />
                  <path v-if="showPassword" d="M4 4l16 16" />
                </svg>
              </button>
            </div>
            <p v-if="inputErrors.password" id="login-password-error" class="field-error-text">{{ inputErrors.password }}</p>
          </div>

          <p v-if="globalErrorMsg" class="login-error-banner" role="alert">{{ globalErrorMsg }}</p>

          <button class="btn btn-primary login-submit-btn" type="submit" :disabled="loading" :aria-busy="loading">
            {{ loading ? '登录中…' : '登录' }}
          </button>
        </form>

        <div class="login-help">
          <button type="button" class="link-btn" @click="showForgotModal = true">忘记密码</button>
          <button type="button" class="link-btn" @click="showRegisterModal = true">申请账号</button>
        </div>
      </section>
    </div>

    <footer class="login-footer">
      <span :title="buildTooltip">版本 {{ buildTag }}</span>
    </footer>

    <n-modal v-model:show="showForgotModal" preset="card" title="找回密码" style="width: min(440px, calc(100vw - 32px))">
      <div class="login-dialog">
        <p>请联系平台管理员重置密码。</p>
        <!-- 演示凭据只在开发环境显示。 -->
        <dl v-if="isDev" class="demo-accounts">
          <dt>开发环境演示账号</dt>
          <dd><code>admin / admin123</code></dd>
          <dd><code>alice / Alice123</code></dd>
          <dd><code>bob / Bob12345</code></dd>
          <dd><code>boss / Boss1234</code></dd>
        </dl>
      </div>
      <template #footer>
        <div class="login-dialog-actions"><n-button type="primary" @click="showForgotModal = false">知道了</n-button></div>
      </template>
    </n-modal>

    <n-modal v-model:show="showRegisterModal" preset="card" title="申请账号" style="width: min(440px, calc(100vw - 32px))">
      <p>请联系项目负责人或平台管理员为你开通账号。</p>
      <template #footer>
        <div class="login-dialog-actions"><n-button type="primary" @click="showRegisterModal = false">知道了</n-button></div>
      </template>
    </n-modal>
  </main>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NModal, useMessage } from 'naive-ui'
import { ApiError } from '../api/http'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

/** 构建版本标识：短哈希 + 构建日期（北京时间），悬停查看完整信息 */
const buildCommit = __BUILD_VERSION__
const buildDate = new Date(__BUILD_TIME__)
const buildTimeLabel = Number.isNaN(buildDate.getTime())
  ? ''
  : buildDate.toLocaleString('zh-CN', {
      timeZone: 'Asia/Shanghai',
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
const buildTag = buildTimeLabel ? `${buildCommit.slice(0, 8)} · ${buildTimeLabel.slice(5, 10)}` : buildCommit.slice(0, 8)
const buildTooltip = `前端构建\n版本：${buildCommit}\n构建时间：${buildTimeLabel || '未知'}（北京时间）`

const isDev = import.meta.env.DEV
const username = ref(isDev ? 'admin' : '')
const password = ref(isDev ? 'admin123' : '')
const showPassword = ref(false)
const loading = ref(false)
const globalErrorMsg = ref('')
const inputErrors = reactive({ username: '', password: '' })
const usernameInputRef = ref<HTMLInputElement | null>(null)
const passwordInputRef = ref<HTMLInputElement | null>(null)
const showForgotModal = ref(false)
const showRegisterModal = ref(false)

const serviceLabels = {
  checking: '正在检查服务',
  available: '服务正常',
  unavailable: '服务不可用',
}
const serviceStatus = ref<keyof typeof serviceLabels>('checking')

// 匿名健康检查仅反映 API 可用性。
async function loadServiceStatus() {
  try {
    const response = await fetch('/api/health')
    serviceStatus.value = response.ok ? 'available' : 'unavailable'
  } catch {
    serviceStatus.value = 'unavailable'
  }
}

function clearFieldError(field: keyof typeof inputErrors) {
  inputErrors[field] = ''
  globalErrorMsg.value = ''
}

async function submitLogin() {
  if (loading.value) return
  const trimmedUser = username.value.trim()
  inputErrors.username = trimmedUser ? '' : '请输入用户名'
  inputErrors.password = password.value ? '' : '请输入密码'
  globalErrorMsg.value = ''

  if (inputErrors.username || inputErrors.password) {
    await nextTick()
    const invalidInput = inputErrors.username ? usernameInputRef.value : passwordInputRef.value
    invalidInput?.focus()
    return
  }

  loading.value = true
  try {
    const user = await auth.login(trimmedUser, password.value)
    message.success(`欢迎回来，${user.username}`)
    await router.push('/agent')
  } catch (error) {
    globalErrorMsg.value = loginErrorMessage(error)
  } finally {
    loading.value = false
  }
}

/** 登录失败文案：区分凭据错误、账号禁用与服务不可达，避免网络故障被误报成「密码错误」。 */
function loginErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return '用户名或密码错误，请重新输入'
    if (error.status === 403) return '账号已被禁用或无权登录，请联系管理员'
    if (error.status === 429) return '尝试过于频繁，请稍后再试'
    if (error.status && error.status >= 500) return '服务暂时不可用，请稍后重试'
    return error.message || '登录失败，请稍后重试'
  }
  return '网络异常，无法连接服务端，请检查网络后重试'
}

onMounted(loadServiceStatus)
</script>

<style scoped>
.login-wrapper {
  display: grid;
  grid-template-columns: minmax(0, 900px);
  grid-template-rows: auto 1fr auto;
  justify-content: center;
  align-items: center;
  gap: var(--space-5);
  height: 100vh;
  height: 100dvh;
  padding: var(--space-5);
  overflow: auto;
  background: var(--sidebar-bg);
}
.login-header,
.login-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}
.login-brand {
  color: var(--text-primary);
  font: 700 16px/1.4 var(--font-display);
}
.service-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}
.service-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-tertiary);
}
.service-status.available .service-dot {
  background: var(--accent-success);
}
.service-status.unavailable .service-dot {
  background: var(--accent-error);
}
.login-main-card {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
  background: var(--bg-main);
  box-shadow: var(--shadow-dialog);
  overflow: hidden;
}
.login-intro,
.login-panel {
  padding: clamp(24px, 4vw, 48px);
}
.login-intro {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: var(--space-6);
  border-inline-end: 1px solid var(--border-subtle);
  background: var(--bg-elevated);
}
.login-intro h2 {
  color: var(--text-primary);
  font: 700 clamp(26px, 3.6vw, 38px)/1.3 var(--font-display);
  text-wrap: initial;
}
.login-steps {
  display: grid;
  gap: var(--space-4);
  margin: 0;
  padding: 0;
  list-style: none;
}
.login-steps li {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}
.login-steps li:not(:last-child)::after {
  position: absolute;
  top: 32px;
  bottom: calc(-1 * var(--space-4));
  left: 15px;
  width: 1px;
  background: var(--border-subtle);
  content: '';
}
.step-index {
  display: grid;
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  place-items: center;
  border-radius: var(--radius-lg);
  background: var(--t-agent);
  color: var(--c-agent);
  font: 600 11px/1 var(--font-mono);
}
.login-steps p,
.login-panel-header p {
  color: var(--text-secondary);
  font-size: 13px;
}
.login-steps b {
  font-size: 14px;
}
.login-panel {
  align-self: center;
}
.login-panel-header {
  display: grid;
  gap: var(--space-2);
  margin-bottom: var(--space-5);
}
.login-panel-header h1 {
  color: var(--text-primary);
  font: 700 28px/1.25 var(--font-display);
}
.login-form,
.form-field {
  display: grid;
  gap: var(--space-4);
}
.form-field {
  gap: 6px;
}
.form-field label {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}
.native-input {
  width: 100%;
  height: 44px;
  padding-inline: var(--space-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-main);
  color: var(--text-primary);
  font-size: 16px;
}
.native-input::placeholder {
  color: var(--text-tertiary);
}
.native-input[aria-invalid='true'] {
  border-color: var(--accent-error);
}
.password-field {
  position: relative;
}
.password-field .native-input {
  padding-inline-end: 48px;
}
.password-toggle-btn {
  position: absolute;
  inset: 4px 4px 4px auto;
  display: grid;
  width: 36px;
  place-items: center;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--text-secondary);
}
.password-toggle-btn:hover {
  background: var(--row-hover);
  color: var(--text-primary);
}
.field-error-text {
  color: var(--c-error);
  font-size: 12px;
}
.login-error-banner {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--t-error);
  color: var(--c-error);
  font-size: 13px;
}
.login-submit-btn {
  min-height: 44px;
  margin-top: var(--space-1);
}
.login-help {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.login-help .link-btn {
  min-height: 32px;
}
.login-footer {
  justify-content: flex-end;
  color: var(--text-tertiary);
  font: 500 11px/1.5 var(--font-mono);
}
.login-dialog {
  display: grid;
  gap: var(--space-3);
}
.login-dialog-actions {
  display: flex;
  justify-content: flex-end;
}
.demo-accounts {
  margin: 0;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--bg-elevated);
}
.demo-accounts dd {
  margin-inline: 0;
  color: var(--text-secondary);
}

@media (max-width: 700px) {
  .login-wrapper {
    grid-template-columns: minmax(0, 420px);
    gap: var(--space-4);
    padding: var(--space-4);
  }
  .login-main-card {
    grid-template-columns: minmax(0, 1fr);
  }
  .login-intro {
    display: none;
  }
}
</style>
