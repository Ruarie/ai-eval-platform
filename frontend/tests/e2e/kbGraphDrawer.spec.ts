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
  size: '1.2 KB',
  created_at: '2026-11-04T00:00:00Z',
}

const GRAPH = {
  kb_id: 'kb-1',
  nodes: [
    { id: '退款申请', entity_type: 'event', description: '退款业务对象', degree: 3, doc_ids: ['d-1'] },
    { id: '到账', entity_type: 'data', description: '到账时长 1-3 个工作日', degree: 2, doc_ids: ['d-1'] },
    { id: '客服', entity_type: 'organization', description: '超时未到账时联系客服', degree: 1, doc_ids: ['d-1'] },
  ],
  edges: [{ source: '退款申请', target: '到账', description: '退款 1-3 个工作日到账', weight: 1 }],
  truncated: false,
  engine: 'lightrag',
}

type GraphResponder = (route: Parameters<Parameters<Page['route']>[1]>[0]) => Promise<void> | void

async function setupKb(page: Page, graph: GraphResponder) {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    // 只接管后端接口：/src/api/*.ts 等模块请求必须放行，否则页面白屏。
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/kb') return route.fulfill({ json: { items: [KB], total: 1 } })
    if (path === '/api/kb/kb-1/documents') return route.fulfill({ json: { items: [DOC], total: 1 } })
    if (path === '/api/kb/kb-1/gold-qa') return route.fulfill({ json: { items: [], total: 0 } })
    if (path === '/api/kb/kb-1/documents/d-1/chunks') return route.fulfill({ json: { items: [], total: 0 } })
    if (path === '/api/kb/kb-1/graph') return graph(route)
    return route.fulfill({ json: {} })
  })
  await page.goto('/kb')
  await expect(page.getByRole('button', { name: '知识图谱' })).toBeVisible()
}

test('知识图谱抽屉展示实体、关系与中文类型详情', async ({ page }) => {
  await setupKb(page, route => route.fulfill({ json: GRAPH }))

  await page.getByRole('button', { name: '知识图谱' }).click()

  await expect(page.getByText('知识图谱 · 默认知识库')).toBeVisible()
  await expect(page.getByText('3 个实体 · 1 条关系')).toBeVisible()
  await expect(page.locator('svg.graph-canvas .graph-node')).toHaveCount(3)

  // 节点顺序由布局决定，点击「关联度最高」列表里的退款更稳。
  await page.locator('.graph-side .top-chip', { hasText: '退款' }).click()
  await expect(page.getByText('退款业务对象')).toBeVisible()
  // 类型中文化：event → 事件
  await expect(page.locator('.graph-side .chip')).toHaveText('事件')
  await expect(page.locator('.graph-side').getByText('退款规则.md')).toBeVisible()
})

test('图谱为空时提示先上传文档，不画示例图', async ({ page }) => {
  await setupKb(page, route =>
    route.fulfill({ json: { kb_id: 'kb-1', nodes: [], edges: [], truncated: false, engine: 'lightrag' } }),
  )

  await page.getByRole('button', { name: '知识图谱' }).click()

  await expect(page.getByText('当前库还没有抽出实体')).toBeVisible()
  await expect(page.locator('svg.graph-canvas')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '↑ 上传文档' }).last()).toBeVisible()
})

test('引擎不可用时显示错误与重试，不渲染空图', async ({ page }) => {
  let calls = 0
  await setupKb(page, route => {
    calls += 1
    return route.fulfill({ status: 502, json: { code: 'UPSTREAM', message: 'LightRAG 图谱读取失败，请稍后重试' } })
  })

  await page.getByRole('button', { name: '知识图谱' }).click()

  await expect(page.getByText('LightRAG 图谱读取失败，请稍后重试')).toBeVisible()
  await expect(page.locator('svg.graph-canvas')).toHaveCount(0)

  const before = calls
  await page.getByRole('button', { name: '重试' }).click()
  await expect.poll(() => calls).toBeGreaterThan(before)
})

test('节点过多时按关联度截断提示可见', async ({ page }) => {
  await setupKb(page, route =>
    route.fulfill({ json: { ...GRAPH, truncated: true } }),
  )

  await page.getByRole('button', { name: '知识图谱' }).click()

  await expect(page.getByText('已按关联度截断，仅展示最强的节点')).toBeVisible()
})
