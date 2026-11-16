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

/** 登录态下给四个新页面准备最小成功响应，其它接口返回空对象。 */
async function setup(page: Page, options: { usageFails?: boolean } = {}) {
  let usageCalls = 0
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/notifications') {
      return route.fulfill({ json: { items: [], total: 0, unread: 0, offset: 0, limit: 20 } })
    }
    if (path === '/api/usage/summary') {
      usageCalls += 1
      if (options.usageFails && usageCalls === 1) {
        return route.fulfill({ status: 502, json: { code: 'UPSTREAM', message: '用量聚合失败' } })
      }
      return route.fulfill({
        json: {
          calls: 0, sessions: 0, users: 0,
          prompt_tokens: 0, completion_tokens: 0, total_tokens: 0,
          series: [], by_model: [], by_user: [], recent: [],
        },
      })
    }
    if (path === '/api/metrics/casegen') {
      return route.fulfill({
        json: {
          days: 30,
          generated_at: '2026-11-16T00:00:00Z',
          total_runs: 0,
          succeeded_runs: 0,
          failed_runs: 0,
          cancelled_runs: 0,
          awaiting_runs: 0,
          success_rate: 0,
          total_generated: 0,
          total_confirmed: 0,
          adoption_rate: 0,
          ai_scored_runs: 0,
          avg_ai_score: null,
          review_approved: 0,
          series: [],
          by_model: [],
          by_status: [],
          modules: [],
          recent: [],
        },
      })
    }
    if (path === '/api/case-assets/stats') {
      return route.fulfill({ json: { total: 0, source_sets: 0, modules: [], tags: [] } })
    }
    if (path === '/api/case-assets') {
      return route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 20 } })
    }
    return route.fulfill({ json: {} })
  })
  return {
    usageCalls: () => usageCalls,
  }
}

test('用量、质量、资产和通知页都能打开空态', async ({ page }) => {
  await setup(page)
  await page.goto('/usage')
  await expect(page.getByRole('heading', { name: '用量中心' })).toBeVisible()
  await expect(page.getByText('当前时间范围内没有可统计的模型调用')).toBeVisible()

  await page.goto('/case-quality')
  await expect(page.getByRole('heading', { name: '用例质量看板' })).toBeVisible()
  await expect(page.getByText('当前时间范围内没有用例生成任务')).toBeVisible()

  await page.goto('/case-assets')
  await expect(page.getByRole('heading', { name: '用例资产库' })).toBeVisible()
  await expect(page.getByText('资产总数')).toBeVisible()

  await page.goto('/notifications')
  await expect(page.getByRole('heading', { name: '通知中心' })).toBeVisible()
  await expect(page.getByText('暂无通知；任务完成或评审指派后会出现在这里。')).toBeVisible()
})

test('用量加载失败后可以重试', async ({ page }) => {
  const calls = await setup(page, { usageFails: true })
  await page.goto('/usage')
  await expect(page.getByText('用量聚合失败')).toBeVisible()
  await page.getByRole('button', { name: '重试' }).click()
  await expect(page.getByText('当前时间范围内没有可统计的模型调用')).toBeVisible()
  expect(calls.usageCalls()).toBeGreaterThan(1)
})
