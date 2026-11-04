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

const KB = {
  id: 'kb-1',
  name: '默认知识库',
  kind: 'lightrag',
  doc_count: 1,
  is_core: false,
  owner: '联调成员',
  capabilities: { projection: false, rerank_compare: false },
}

const DOC = {
  doc_id: 'd-1',
  filename: '退款规则.md',
  status: 'indexed',
  size: '1 KB',
  created_at: '2026-11-04T00:00:00Z',
}

const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

type Options = { queryDelayMs?: number; graphDelayMs?: number }

/** 统一拦截：只接管 /api/，其余模块请求必须放行，否则页面白屏。 */
async function setup(page: Page, options: Options = {}) {
  const counters = { query: 0, graph: 0 }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/kb') return route.fulfill({ json: { items: [KB], total: 1 } })
    if (path === '/api/kb/kb-1/documents') return route.fulfill({ json: { items: [DOC], total: 1 } })
    if (path === '/api/kb/kb-1/gold-qa') return route.fulfill({ json: { items: [], total: 0 } })
    if (path === '/api/kb/kb-1/documents/d-1/chunks') {
      return route.fulfill({ json: { items: [{ chunk_id: 'd-1#c01', doc_id: 'd-1', text: '退款 1-3 个工作日到账', tokens: 12 }], total: 1 } })
    }
    if (path === '/api/kb/kb-1/query') {
      counters.query += 1
      await sleep(options.queryDelayMs ?? 1200)
      return route.fulfill({
        json: {
          items: [{ chunk_id: 'd-1#c01', doc_name: '退款规则.md', similarity: 0.9, text: '退款 1-3 个工作日到账', hit: true }],
          metrics: { hit_rate: 1, mrr: 1, recall: 1, contain: 1 },
          reranked_ids: ['d-1#c01'],
        },
      })
    }
    if (path === '/api/kb/kb-1/graph') {
      counters.graph += 1
      await sleep(options.graphDelayMs ?? 1200)
      return route.fulfill({
        json: {
          kb_id: 'kb-1',
          nodes: [{ id: '退款', entity_type: 'event', description: '退款对象', degree: 1, doc_ids: ['d-1'] }],
          edges: [],
          truncated: false,
          engine: 'lightrag',
        },
      })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/kb')
  await expect(page.getByRole('button', { name: '知识图谱' })).toBeVisible()
  return counters
}

test('慢响应下检索按钮进入加载态，连点不会重复发请求', async ({ page }) => {
  const counters = await setup(page, { queryDelayMs: 1500 })

  const search = page.getByRole('button', { name: '检索', exact: true })
  await search.click()
  // 请求未返回期间按钮变为「检索中…」且禁用
  await expect(page.getByRole('button', { name: '检索中…' })).toBeVisible()
  await page.getByRole('button', { name: '检索中…' }).click({ force: true }).catch(() => {})
  await page.getByRole('button', { name: '检索中…' }).click({ force: true }).catch(() => {})

  await expect(page.getByRole('button', { name: '检索', exact: true })).toBeVisible({ timeout: 15000 })
  expect(counters.query).toBe(1)
  await expect(page.getByText('Top-5', { exact: false }).first()).toBeVisible()
})

test('慢响应下图谱抽屉先显示加载态，完成后才渲染节点', async ({ page }) => {
  await setup(page, { graphDelayMs: 1500 })

  await page.getByRole('button', { name: '知识图谱' }).click()
  // 加载态文案先出现，且此时没有画布
  await expect(page.getByText('正在读取实体关系…')).toBeVisible()
  await expect(page.locator('svg.graph-canvas')).toHaveCount(0)

  await expect(page.locator('svg.graph-canvas')).toHaveCount(1, { timeout: 15000 })
  await expect(page.getByText('1 个实体 · 0 条关系')).toBeVisible()
})
