import { expect, test, type Page } from '@playwright/test'

/**
 * 成员开通回归（P1）：请求体只能有契约内字段，且服务端字段错误要能落到表单项。
 *
 * 真实事故：前端多带 `role` 被后端 `extra=forbid` 拒绝 → 400「请检查标红字段」，
 * 表单却没有标红，表现为「开通新成员总是失败且看不出原因」。
 */

const USER = {
  id: 'u-1', username: 'admin', display_name: '管理员', email: null, role: 'admin',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

async function mockUsers(page: Page, handler: { status: number; body: unknown; captured?: { payload?: Record<string, unknown> } }) {
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', (r) => r.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/users' && req.method() === 'GET') {
      return route.fulfill({ json: { items: [USER], total: 1 } })
    }
    if (path === '/api/users' && req.method() === 'POST') {
      handler.captured = { payload: req.postDataJSON() as Record<string, unknown> }
      return route.fulfill({ status: handler.status, json: handler.body })
    }
    if (path.startsWith('/api/users/activity')) {
      return route.fulfill({ json: {
        kpis: { active_members: 1, new_members: 0, total_tasks: 0, disabled_members: 0, login_count: 3, login_failed: 0 },
        login_buckets: [],
        recent_audits: [],
      } })
    }
    if (path === '/api/audit-logs' || path === '/api/admin/audit-logs') return route.fulfill({ json: { items: [], total: 0 } })
    return route.fulfill({ json: {} })
  })
}

async function openModal(page: Page) {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin/users')
  await page.getByRole('button', { name: /开通新成员/ }).click()
  await expect(page.locator('.n-modal')).toBeVisible()
}

test('开通新成员：只提交契约内字段，不带 role', async ({ page }) => {
  const handler = {
    status: 201,
    body: { ...USER, id: 'u-2', username: 'zhangsan', display_name: '张三' },
    captured: {} as { payload?: Record<string, unknown> },
  }
  await mockUsers(page, handler)
  await openModal(page)

  await page.getByPlaceholder('输入成员账号名称').fill('zhangsan')
  await page.getByPlaceholder('至少 8 位，包含字母与数字').fill('UiTest2026x')
  await page.getByPlaceholder('例如：张三（可留空）').fill('张三')
  await page.getByRole('button', { name: '确认开通' }).click()

  await expect(page.locator('.n-modal')).toBeHidden()
  const payload = handler.captured.payload!
  expect(payload).toMatchObject({ username: 'zhangsan', password: 'UiTest2026x', display_name: '张三' })
  expect(payload).not.toHaveProperty('role')
})

test('开通新成员：服务端返回字段错误时标红对应输入框', async ({ page }) => {
  const handler = {
    status: 400,
    body: { code: 'VALIDATION', message: '请检查标红字段', fields: { username: '该账号已存在' } },
    captured: {} as { payload?: Record<string, unknown> },
  }
  await mockUsers(page, handler)
  await openModal(page)

  await page.getByPlaceholder('输入成员账号名称').fill('zhangsan')
  await page.getByPlaceholder('至少 8 位，包含字母与数字').fill('UiTest2026x')
  await page.getByRole('button', { name: '确认开通' }).click()

  // 弹窗仍在，用户名下方出现服务端文案，输入框进入错误态
  await expect(page.locator('.n-modal')).toBeVisible()
  await expect(page.locator('.field-error')).toHaveText('该账号已存在')
  await expect(page.locator('.n-modal .n-input--error-status').first()).toBeVisible()
})
