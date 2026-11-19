import { expect, test, type Page } from '@playwright/test'

/**
 * 远程工作区入口一致性（P2）：SSH 工作区在后端只允许浏览，新建/上传/重命名会被
 * `_require_local` 拒绝。前端必须同步收口，不能留「可点但必然失败」的入口。
 */

const LOCAL = {
  id: 'ws-local', name: '本地工作区', owner_id: 'u-1', deleted: false,
  kind: 'local', quota_bytes: 1024 * 1024 * 1024, created_at: '2026-11-01T00:00:00Z',
}
const REMOTE = {
  id: 'ws-ssh', name: '远程工作区', owner_id: 'u-1', deleted: false,
  kind: 'ssh', auth_type: 'password', ssh_host: '10.0.0.9', ssh_user: 'root',
  ssh_port: 22, remote_path: '/srv/app', created_at: '2026-11-02T00:00:00Z',
}

async function mockWorkspaces(page: Page) {
  await page.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, (route) => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') {
      return route.fulfill({ json: { id: 'u-1', username: 'admin', display_name: '管理员', role: 'admin', disabled: false } })
    }
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/workspaces') return route.fulfill({ json: { items: [LOCAL, REMOTE] } })
    if (path.endsWith('/files/tree')) return route.fulfill({ json: { items: [] } })
    return route.fulfill({ json: {} })
  })
}

test('远程工作区：写操作入口禁用并给出原因', async ({ page }) => {
  await mockWorkspaces(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await page.goto('/workspaces')
  await expect(page.locator('.explorer-panel')).toBeVisible()

  // 切到远程工作区
  await page.locator('select').first().selectOption('ws-ssh')
  await page.waitForTimeout(600)

  await expect(page.locator('.readonly-pill')).toHaveText('只读')
  const newFile = page.locator('.explorer-actions button[title*="远程工作区仅支持浏览"]').first()
  await expect(newFile).toBeDisabled()

  // 快捷新建同样收口
  const quick = page.getByRole('button', { name: '新建 Python 脚本' })
  await expect(quick).toBeDisabled()
  await expect(quick).toHaveAttribute('title', /远程工作区仅支持浏览/)

  // 拖拽上传给出明确提示，而不是发请求后报错
  const dropped = await page.evaluate(() => {
    const zone = document.querySelector('.tree-container, .tree-empty, [class*=tree]') as HTMLElement | null
    if (!zone) return 'no zone'
    const dt = new DataTransfer()
    dt.items.add(new File(['x'], 'drag.txt', { type: 'text/plain' }))
    ;['dragenter', 'dragover', 'drop'].forEach((t) => {
      zone.dispatchEvent(new DragEvent(t, { bubbles: true, cancelable: true, dataTransfer: dt }))
    })
    return 'ok'
  })
  expect(dropped).toBe('ok')
  await expect(page.locator('.n-message')).toContainText('远程工作区仅支持浏览，不能上传文件')
})

test('本地工作区：写操作入口可用', async ({ page }) => {
  await mockWorkspaces(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/workspaces')
  await expect(page.locator('.explorer-panel')).toBeVisible()

  await page.locator('select').first().selectOption('ws-local')
  await page.waitForTimeout(600)

  await expect(page.locator('.readonly-pill')).toHaveCount(0)
  await expect(page.locator('.explorer-actions button[title="新建文件"]')).toBeEnabled()
  await expect(page.getByRole('button', { name: '新建 Python 脚本' })).toBeEnabled()
})
