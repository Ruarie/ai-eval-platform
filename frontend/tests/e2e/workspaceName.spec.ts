import { expect, test, type Page } from '@playwright/test'

/**
 * 工作区名称上限 60（与后端 `_NameBody.name` 一致）。
 *
 * 之前 150 字的名称能直接创建成功，左栏被撑坏；现在输入框限制 + 提交兜底双保险，
 * 文件/文件夹名不受影响（仍是 255）。
 */

const USER = { id: 'u-1', username: 'admin', display_name: '管理员', role: 'admin', disabled: false }

async function mockWorkspaces(page: Page, created: { payloads: Record<string, unknown>[] }) {
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', (r) => r.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/workspaces' && req.method() === 'GET') return route.fulfill({ json: { items: [] } })
    if (path === '/api/workspaces' && req.method() === 'POST') {
      created.payloads.push(req.postDataJSON() as Record<string, unknown>)
      return route.fulfill({ status: 201, json: { id: 'ws-new', name: 'ok', kind: 'local', deleted: false } })
    }
    return route.fulfill({ json: {} })
  })
}

test('新建工作区：输入框限制 60 字并有字数提示', async ({ page }) => {
  const created = { payloads: [] as Record<string, unknown>[] }
  await mockWorkspaces(page, created)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/workspaces')

  await page.getByRole('button', { name: '新建工作区' }).click()
  const input = page.getByPlaceholder('例如：大模型评测主库')
  await expect(input).toBeVisible()
  await expect(input).toHaveAttribute('maxlength', '60')
  await expect(page.locator('.form-hint')).toHaveText('0 / 60 字')

  // 键盘输入超过 60 字，浏览器按 maxlength 截断
  await input.pressSequentially('A'.repeat(61))
  await expect(input).toHaveValue('A'.repeat(60))
  await expect(page.locator('.form-hint')).toHaveText('60 / 60 字')
})

test('新建工作区：绕过 maxlength 的超长名在提交前被拦', async ({ page }) => {
  const created = { payloads: [] as Record<string, unknown>[] }
  await mockWorkspaces(page, created)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/workspaces')

  await page.getByRole('button', { name: '新建工作区' }).click()
  const input = page.getByPlaceholder('例如：大模型评测主库')
  // 模拟粘贴/脚本赋值：直接写 value，绕过 maxlength
  await input.evaluate((el, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
    setter.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }, 'B'.repeat(80))

  await page.getByRole('button', { name: /创建/ }).click()
  await expect(page.locator('.n-message')).toContainText('工作区名称最多 60 个字符')
  expect(created.payloads).toHaveLength(0)
})
