import { expect, test, type Page } from '@playwright/test'

/**
 * 自研弹窗（.modal-backdrop）的 Esc 关闭契约。
 *
 * 背景：工作区「新建/重命名/新建文件」等弹窗是自研遮罩层，不走 Naive UI，
 * 原先只有「取消」按钮能关闭，Esc 无效；协议档编辑弹窗关闭了 trap-focus，
 * Naive UI 的默认 Esc 监听也收不到事件。这里锁定统一行为。
 */

const USER = {
  id: 'u-1', username: '联调成员', display_name: '联调成员', email: null, role: 'admin',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

const PROFILE = {
  id: 'p-1', name: 'DeepSeek (deepseek-flash)', version: 'v1', model: 'deepseek-flash',
  protocol: 'anthropic_messages', base_url: 'https://api.deepseek.com/anthropic',
  usages: ['agent', 'judge'], allowed_efforts: ['off', 'low', 'high'], default_effort: 'high',
}

async function mockApi(page: Page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/workspaces') {
      return route.fulfill({
        json: {
          items: [{ id: 'w1', name: '默认工作区', deleted: false, quota_bytes: 1073741824, folder: { total_bytes: 1024, file_count: 0 } }],
          total: 1,
        },
      })
    }
    if (path.endsWith('/tree')) return route.fulfill({ json: { tree: [] } })
    if (path === '/api/profiles') return route.fulfill({ json: [PROFILE] })
    if (path === '/api/profiles/reasoning-templates') return route.fulfill({ json: [] })
    if (path === '/api/admin/settings') return route.fulfill({ json: { agent_profile_id: PROFILE.id } })
    return route.fulfill({ json: {} })
  })
}

test('新建工作区弹窗可以用 Esc 关闭', async ({ page }) => {
  await mockApi(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/workspaces')
  await page.getByRole('button', { name: '新建工作区' }).click()
  await expect(page.locator('.modal-backdrop')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.modal-backdrop')).toHaveCount(0)
})

test('编辑协议档弹窗可以用 Esc 关闭', async ({ page }) => {
  await mockApi(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin/profiles')
  await page.getByRole('button', { name: '编辑', exact: true }).first().click()
  await expect(page.locator('.n-modal')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('.n-modal')).toHaveCount(0)
})
