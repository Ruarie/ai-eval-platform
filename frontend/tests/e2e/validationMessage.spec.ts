import { expect, test, type Page } from '@playwright/test'

/**
 * 校验失败的提示可读性：后端给「请检查标红字段」+ fields 时，toast 必须落到
 * 「哪个字段、错在哪」，而不是让用户自己猜。
 *
 * 用知识库新建做样本：它的名称输入框没有 maxlength，最容易真的打到后端 422。
 */

async function mockKb(page: Page) {
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', (r) => r.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: 'u-1', username: 'admin', display_name: '管理员', role: 'admin', disabled: false } })
    }
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/kb' && req.method() === 'GET') {
      return route.fulfill({ json: { items: [{ id: 'kb-1', name: '默认知识库', kind: 'lightrag' }], total: 1 } })
    }
    if (path === '/api/kb' && req.method() === 'POST') {
      return route.fulfill({
        status: 400,
        json: {
          code: 'VALIDATION',
          message: '请检查标红字段',
          fields: { name: 'String should have at most 100 characters' },
        },
      })
    }
    return route.fulfill({ json: {} })
  })
}

test('后端字段校验失败时提示翻译成人话', async ({ page }) => {
  await mockKb(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/kb')
  await expect(page.getByText('历史知识库')).toBeVisible()

  await page.getByRole('button', { name: /新建知识库/ }).click()
  const modal = page.locator('.n-modal')
  await expect(modal).toBeVisible()
  await modal.locator('input').first().fill('A'.repeat(150))
  await modal.getByRole('button', { name: '创建' }).click()

  const toast = page.locator('.n-message')
  await expect(toast).toBeVisible()
  await expect(toast).toContainText('名称：最多 100 个字符')
  await expect(toast).not.toContainText('请检查标红字段')
})
