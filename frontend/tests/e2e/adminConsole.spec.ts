import { expect, test, type Page } from '@playwright/test'

/**
 * 管理后台 UI 契约：概览 / 审计 / 资源治理。
 *
 * 后端聚合口径由 backend/api/tests/test_admin_overview.py 覆盖；这里锁定前端：
 * 1. 概览把六组数字与分布图渲染出来，不出现「—」占位（数据齐的情况）；
 * 2. 审计支持按动作过滤，加载更多不丢已加载行；
 * 3. 资源治理可切换可见性（PATCH）与下架（DELETE），改动即时反映在行上。
 */

const USER = {
  id: 'u-1', username: 'admin', display_name: '管理员', email: null, role: 'admin',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

const OVERVIEW = {
  users: { total: 12, new_7d: 2, active_7d: 7, disabled: 1 },
  sessions: { total: 48, new_7d: 9, shared: 5 },
  tasks: { total_7d: 21, by_status: { succeeded: 15, running: 2, failed: 3, queued: 1 } },
  resources: { total: 9, new_7d: 3, team: 6, private: 3, usage_total: 33, by_kind: { agent: 4, rag: 2, skill: 2, rule: 1 } },
  storage: { files: 25, bytes: 5 * 1024 * 1024, kb_count: 2, kb_docs: 13 },
  audit_24h: 18,
  top_actions: { resource_create: 6, resource_update: 5, resource_delete: 2 },
  recent_audit: [
    { id: 3, action: 'resource_create', target_type: 'resource', target_id: 'r-abc12345', user_name: 'Alice', ip: '10.0.0.1', ts: '2026-11-19T02:00:00+00:00' },
    { id: 2, action: 'resource_delete', target_type: 'resource', target_id: 'r-def67890', user_name: 'Bob', ip: '10.0.0.2', ts: '2026-11-19T01:30:00+00:00' },
  ],
  generated_at: '2026-11-19T02:10:00+00:00',
}

const AUDIT = {
  total: 60,
  items: Array.from({ length: 60 }, (_, i) => ({
    id: 60 - i,
    at: '2026-11-19T01:00:00+00:00',
    actor_id: 'u-1',
    actor_name: '管理员',
    action: i % 3 === 0 ? 'resource_delete' : 'resource_create',
    target: { type: 'resource', id: `r-${String(i).padStart(8, '0')}` },
    detail: { kind: 'agent' },
    ip: '10.0.0.1',
  })),
}

const RES = (over: Record<string, unknown> = {}) => ({
  id: 'r-1', kind: 'agent', name: '日志分析助手', summary: '按错误聚合',
  content: {}, owner_id: 'u-1', owner_name: 'Alice', visibility: 'team',
  usage_count: 5, source_id: null, editable: true,
  created_at: '2026-11-01T10:00:00+00:00', updated_at: '2026-11-18T09:00:00+00:00', ...over,
})

async function mockAdmin(page: Page, store: { rows: Record<string, unknown>[]; patches: string[]; deletes: string[] }) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, route => {
    const req = route.request()
    const path = new URL(req.url()).pathname
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/admin/overview') return route.fulfill({ json: OVERVIEW })
    if (path === '/api/admin/audit-logs') return route.fulfill({ json: AUDIT })
    if (path === '/api/resources' && req.method() === 'GET') {
      return route.fulfill({ json: { items: store.rows, total: store.rows.length } })
    }
    if (/^\/api\/resources\/r-\d+$/.test(path) && req.method() === 'PATCH') {
      const body = req.postDataJSON() as { visibility?: string }
      const row = store.rows.find(r => r.id === path.split('/').pop())
      if (row && body.visibility) row.visibility = body.visibility
      store.patches.push(path)
      return route.fulfill({ json: row })
    }
    if (/^\/api\/resources\/r-\d+$/.test(path) && req.method() === 'DELETE') {
      store.deletes.push(path)
      return route.fulfill({ json: { deleted: true } })
    }
    return route.fulfill({ json: {} })
  })
}

test('平台概览：六组指标与分布图渲染', async ({ page }) => {
  const store = { rows: [RES()], patches: [] as string[], deletes: [] as string[] }
  await mockAdmin(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin')

  await expect(page.getByRole('heading', { name: '平台概览' })).toBeVisible()
  const cards = page.locator('.ao-card')
  await expect(cards).toHaveCount(6)
  await expect(cards.nth(0)).toContainText('12')
  await expect(cards.nth(1)).toContainText('48')
  await expect(cards.nth(4)).toContainText('5.0 MB')

  // 资源分布：agent 4 / rag 2 / skill 2 / rule 1
  await expect(page.locator('.ao-panel').first()).toContainText('Agent')
  await expect(page.locator('.ao-panel').first().locator('.ao-bar')).toHaveCount(4)
  // 最近操作表：两条，操作人已解析
  await expect(page.locator('.ao-table tbody tr')).toHaveCount(2)
  await expect(page.locator('.ao-table')).toContainText('Alice')
  // 不再出现未解析的占位
  await expect(page.locator('.ao-table')).not.toContainText('成员 u-1')
})

test('审计日志：默认分页、动作过滤与加载更多', async ({ page }) => {
  const store = { rows: [RES()], patches: [] as string[], deletes: [] as string[] }
  await mockAdmin(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin/audit')

  await expect(page.getByRole('heading', { name: '审计日志' })).toBeVisible()
  await expect(page.locator('.aa-total')).toContainText('共 60 条')
  await expect(page.locator('.aa-table tbody tr').first()).toContainText('管理员')
  // 默认一页 50 行
  await expect(page.locator('.aa-table tbody tr')).toHaveCount(50)

  await page.getByRole('button', { name: '加载更多' }).click()
  await expect(page.locator('.aa-table tbody tr')).toHaveCount(60)
  await expect(page.locator('.aa-more')).toContainText('已到末尾')

  // 按动作过滤：resource_delete 每 3 条一个 → 20 行
  await page.locator('.aa-toolbar .n-select').click()
  await page.locator('.n-base-select-option', { hasText: 'resource_delete' }).click()
  await expect(page.locator('.aa-table tbody tr')).toHaveCount(20)
})

test('资源治理：切换可见性与下架删除', async ({ page }) => {
  const store = {
    rows: [RES(), RES({ id: 'r-2', name: '退款检索口径', kind: 'rag', visibility: 'private', owner_name: 'Bob' })],
    patches: [] as string[],
    deletes: [] as string[],
  }
  await mockAdmin(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/admin/resources')

  await expect(page.getByRole('heading', { name: '资源治理' })).toBeVisible()
  await expect(page.locator('.ar-table tbody tr')).toHaveCount(2)
  await expect(page.locator('.ar-total')).toContainText('共 2 个')

  // 团队 → 私有
  await page.locator('.ar-table tbody tr').first().getByRole('button', { name: '转为私有' }).click()
  await expect(page.locator('.ar-table tbody tr').first().locator('.ar-vis')).toHaveText('私有')
  expect(store.patches).toHaveLength(1)

  // 删除需要确认
  page.on('dialog', dialog => dialog.accept())
  await page.locator('.ar-table tbody tr').nth(1).getByRole('button', { name: '下架删除' }).click()
  await expect(page.locator('.ar-table tbody tr')).toHaveCount(1)
  expect(store.deletes).toHaveLength(1)
})
