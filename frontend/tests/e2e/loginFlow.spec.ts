import { expect, test, type Page } from '@playwright/test'

const USER = {
  id: 'u-1',
  username: '联调成员',
  display_name: '联调成员',
  email: null,
  role: 'member',
  disabled: false,
  must_change_password: false,
  last_login_at: null,
  last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

/** 未登录态：/api/auth/me 返回 401，登录接口由用例决定。 */
async function setupGuest(page: Page, loginStatus: 'success' | 'unauthorized' = 'unauthorized') {
  let loggedIn = false
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    // 只接管后端接口：/src/api/*.ts 等模块请求必须放行，否则页面白屏。
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') {
      return loggedIn
        ? route.fulfill({ json: USER })
        : route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '未登录' } })
    }
    if (path === '/api/auth/login') {
      if (loginStatus === 'unauthorized') {
        return route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '用户名或密码错误' } })
      }
      loggedIn = true
      return route.fulfill({ json: USER })
    }
    if (path === '/api/auth/logout') {
      loggedIn = false
      return route.fulfill({ json: { ok: true } })
    }
    return route.fulfill({ json: {} })
  })
}

test('未登录访问受保护页面跳转登录页', async ({ page }) => {
  await setupGuest(page)
  await page.goto('/cases')
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.locator('.login-submit-btn')).toBeVisible()
})

test('空表单提交给出字段级提示且不发登录请求', async ({ page }) => {
  let loginCalls = 0
  await setupGuest(page)
  page.on('request', request => {
    if (request.url().includes('/api/auth/login')) loginCalls += 1
  })
  await page.goto('/login')
  // dev server 会预填 admin/admin123（仅开发态），先清空再验证空表单校验。
  await page.getByPlaceholder('请输入用户名').fill('')
  await page.getByPlaceholder('请输入密码').fill('')
  await page.locator('.login-submit-btn').click()

  await expect(page.getByText('请输入用户名')).toBeVisible()
  await expect(page.getByText('请输入密码')).toBeVisible()
  expect(loginCalls).toBe(0)
})

test('凭证错误时展示全局错误横幅并停留登录页', async ({ page }) => {
  await setupGuest(page, 'unauthorized')
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill('someone')
  await page.getByPlaceholder('请输入密码').fill('wrong-password')
  await page.locator('.login-submit-btn').click()

  await expect(page.locator('.login-error-banner')).toBeVisible()
  await expect(page.locator('.login-error-banner')).toContainText('用户名或密码错误')
  await expect(page).toHaveURL(/\/login$/)
})

test('登录成功后进入主工作区，已登录再访问登录页会跳回智能体', async ({ page }) => {
  await setupGuest(page, 'success')
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill('someone')
  await page.getByPlaceholder('请输入密码').fill('right-password')
  await page.locator('.login-submit-btn').click()

  await expect(page).toHaveURL(/\/agent$/)
  await expect(page.locator('.sidebar .nav-item')).not.toHaveCount(0)

  await page.goto('/login')
  await expect(page).toHaveURL(/\/agent$/)
})
