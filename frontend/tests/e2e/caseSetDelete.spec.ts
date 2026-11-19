import { expect, test, type Page } from '@playwright/test'

/**
 * 删除用例集（新能力）：右键菜单入口 + 确认弹窗 + 调接口 + 列表刷新。
 *
 * 背景：用例集此前只能建不能删，「废弃」只是改状态、条目仍留在列表里。
 * 现在删除是软删：草稿与已入库都能移除，已入库的版本与评审记录保留。
 */

const SETS = [
  { id: 'set-1', name: '待删草稿集', status: 'generated', revision: 1, generated_count: 2, confirmed_count: 0, created_at: '2026-11-19T01:00:00Z' },
  { id: 'set-2', name: '已入库集', status: 'confirmed', revision: 3, generated_count: 5, confirmed_count: 5, created_at: '2026-11-19T00:00:00Z' },
]

async function mockCases(page: Page, calls: { deleted: string[] }) {
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', (r) => r.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: 'u-1', username: 'admin', display_name: '管理员', role: 'admin', disabled: false } })
    }
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/case-sets' && req.method() === 'GET') {
      return route.fulfill({ json: { items: SETS, total: SETS.length, truncated: false } })
    }
    if (/^\/api\/case-sets\/[^/]+$/.test(path) && req.method() === 'DELETE') {
      calls.deleted.push(path.split('/').pop()!)
      return route.fulfill({ status: 204, body: '' })
    }
    if (path.startsWith('/api/case-sets/')) return route.fulfill({ json: { ...SETS[0], cases: [], column_schema: [] } })
    return route.fulfill({ json: {} })
  })
}

async function openMenu(page: Page, name: string) {
  const node = page.locator('.tree-node.file-node', { hasText: name })
  await node.click({ button: 'right' })
  await expect(page.locator('.n-dropdown')).toBeVisible()
}

test('草稿用例集：右键删除并确认后从列表移除', async ({ page }) => {
  const calls = { deleted: [] as string[] }
  await mockCases(page, calls)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/cases')
  await expect(page.locator('.tree-node.file-node')).toHaveCount(2)

  await openMenu(page, '待删草稿集')
  await page.locator('.n-dropdown-option', { hasText: '删除用例集' }).click()

  const dialog = page.locator('.n-dialog')
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText('无法恢复')
  await dialog.getByRole('button', { name: '删除' }).click()

  await expect(page.locator('.n-message')).toContainText('已删除「待删草稿集」')
  expect(calls.deleted).toEqual(['set-1'])
})

test('已入库用例集：确认文案说明只归档，不承诺不可恢复', async ({ page }) => {
  const calls = { deleted: [] as string[] }
  await mockCases(page, calls)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/cases')

  await openMenu(page, '已入库集')
  await page.locator('.n-dropdown-option', { hasText: '删除用例集' }).click()

  const dialog = page.locator('.n-dialog')
  await expect(dialog).toContainText('历史版本与评审记录仍保留')
  await dialog.getByRole('button', { name: '删除' }).click()
  expect(calls.deleted).toEqual(['set-2'])
})
