import { expect, test, type Page } from '@playwright/test'

/**
 * 能力中心（资源广场 + Agent/Skill/Script/Rule 四类资源）UI 契约。
 *
 * 后端行为由 backend/api/tests/test_resources.py 覆盖；这里锁定前端侧：
 * 1. 四类中心共用 ResourceCenter，按路由 meta 渲染各自的标题与字段；
 * 2. 新建时按类型组装 content（agent 为 system_prompt/tools，script 为 language/code，
 *    skill/rule 为 markdown），不把无关字段写进 JSONB；
 * 3. 使用会打 /use 并把内容复制到剪贴板，卡片计数就地更新；
 * 4. 基于此创建会在列表里出现副本；
 * 5. 广场三榜渲染，飙升榜为空时给出口径提示而不是复用热门数据。
 */

const USER = {
  id: 'u-1', username: 'alice', display_name: 'Alice', email: null, role: 'admin',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

type Res = {
  id: string; kind: string; name: string; summary: string; content: Record<string, unknown>
  owner_id: string | null; owner_name: string; visibility: string; usage_count: number
  source_id: string | null; editable: boolean; created_at: string; updated_at: string
}

function makeRes(over: Partial<Res> = {}): Res {
  return {
    id: 'r-1', kind: 'agent', name: '日志分析助手', summary: '按错误聚合分析日志',
    content: { system_prompt: '你是日志分析助手', tools: ['read'] },
    owner_id: 'u-1', owner_name: 'Alice', visibility: 'team', usage_count: 3,
    source_id: null, editable: true,
    created_at: '2026-11-01T10:00:00+00:00', updated_at: '2026-11-18T09:00:00+00:00',
    ...over,
  }
}

async function mockApis(page: Page, store: { items: Res[]; creates: unknown[]; uses: string[]; clones: string[] }) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname
    const method = req.method()

    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })

    if (path === '/api/kb') return route.fulfill({ json: [{ id: 'kb-1', name: '退款知识库', kind: 'lightrag', doc_count: 12, is_core: false, owner: 'Alice' }] })
    if (path === '/api/kb/kb-1/query') {
      const body = req.postDataJSON() as { query: string; mode: string; k: number }
      return route.fulfill({ json: {
        query: body.query, mode: body.mode,
        items: [{ chunk_id: 'c-1', doc_name: '退款说明.md', similarity: 0.71, text: '退款申请需在订单完成后 7 天内提交。' }],
        reranked_ids: ['c-1'], metrics: { hit_rate: 1, mrr: 1, recall: 1, contain: 1 },
      } })
    }
    if (path === '/api/mcp/all-tools') {
      return route.fulfill({ json: { total: 3, items: [
        { name: 'read', display_name: '读取文件', desc: '读取工作区文件', permission: 'read', risk_level: 'read', timeout_s: 30, transport: 'native', server_id: 'platform.native' },
        { name: 'bash', display_name: '执行命令', desc: '在沙箱执行 shell', permission: 'write', risk_level: 'exec', timeout_s: 120, transport: 'native', server_id: 'platform.native' },
        { name: 'task.create', display_name: '创建任务', desc: '写入任务队列', permission: 'write', risk_level: 'write', timeout_s: 10, transport: 'mcp', server_id: 'platform.tasks' },
      ] } })
    }
    if (path === '/api/mcp/health-check') {
      return route.fulfill({ json: {
        ok: true, summary: { total_tools: 3, native_tools_count: 2, internal_mcp_tools_count: 1, external_mcp_servers_count: 0 },
        channels: {
          native: { channel: 'native_toolcall', name: 'NativeToolExecutor', ok: true, tools_count: 2, latency_ms: 3, message: '原生通道已注册', sandbox_mode: 'bwrap' },
          internal_mcp: { channel: 'internal_mcp', name: 'platform.tasks', ok: true, tools_count: 1, latency_ms: 2, message: '内部 MCP 可用' },
        },
      } })
    }
    if (path === '/api/kb') return route.fulfill({ json: [{ id: 'kb-1', name: '退款知识库', kind: 'lightrag', doc_count: 12, is_core: false, owner: 'Alice' }] })
    if (path === '/api/kb/kb-1/query') {
      const body = req.postDataJSON() as { query: string; mode: string; k: number }
      return route.fulfill({ json: {
        query: body.query, mode: body.mode,
        items: [{ chunk_id: 'c-1', doc_name: '退款说明.md', similarity: 0.71, text: '退款申请需在订单完成后 7 天内提交。' }],
        reranked_ids: ['c-1'], metrics: { hit_rate: 1, mrr: 1, recall: 1, contain: 1 },
      } })
    }
    if (path === '/api/mcp/all-tools') {
      return route.fulfill({ json: { total: 3, items: [
        { name: 'read', display_name: '读取文件', desc: '读取工作区文件', permission: 'read', risk_level: 'read', timeout_s: 30, transport: 'native', server_id: 'platform.native' },
        { name: 'bash', display_name: '执行命令', desc: '在沙箱执行 shell', permission: 'write', risk_level: 'exec', timeout_s: 120, transport: 'native', server_id: 'platform.native' },
        { name: 'task.create', display_name: '创建任务', desc: '写入任务队列', permission: 'write', risk_level: 'write', timeout_s: 10, transport: 'mcp', server_id: 'platform.tasks' },
      ] } })
    }
    if (path === '/api/mcp/health-check') {
      return route.fulfill({ json: {
        ok: true, summary: { total_tools: 3, native_tools_count: 2, internal_mcp_tools_count: 1, external_mcp_servers_count: 0 },
        channels: {
          native: { channel: 'native_toolcall', name: 'NativeToolExecutor', ok: true, tools_count: 2, latency_ms: 3, message: '原生通道已注册', sandbox_mode: 'bwrap' },
          internal_mcp: { channel: 'internal_mcp', name: 'platform.tasks', ok: true, tools_count: 1, latency_ms: 2, message: '内部 MCP 可用' },
        },
      } })
    }
    if (path === '/api/resources/plaza') {
      const popular = store.items.map((r, i) => ({
        id: r.id, kind: r.kind, name: r.name, summary: r.summary, owner_name: r.owner_name,
        usage_count: r.usage_count - i, weekly_uses: i === 0 ? 2 : 0, created_at: r.created_at,
      }))
      return route.fulfill({ json: { total: store.items.length, featured: popular, popular, rising: popular.slice(0, 1).filter(r => r.weekly_uses > 0), newest: [...popular].reverse() } })
    }

    if (path === '/api/resources' && method === 'GET') {
      const kind = url.searchParams.get('kind') || ''
      const items = store.items.filter(r => !kind || r.kind === kind)
      return route.fulfill({ json: { items, total: items.length } })
    }

    if (path === '/api/resources' && method === 'POST') {
      const payload = req.postDataJSON() as Record<string, unknown>
      store.creates.push(payload)
      const created = makeRes({
        id: `r-${store.items.length + 1}`,
        kind: String(payload.kind),
        name: String(payload.name),
        summary: String(payload.summary || ''),
        content: payload.content as Record<string, unknown>,
        usage_count: 0,
      })
      store.items.push(created)
      return route.fulfill({ json: created })
    }

    const useMatch = path.match(/^\/api\/resources\/([^/]+)\/use$/)
    if (useMatch) {
      store.uses.push(useMatch[1])
      const target = store.items.find(r => r.id === useMatch[1])!
      target.usage_count += 1
      return route.fulfill({ json: { id: target.id, usage_count: target.usage_count, content: target.content } })
    }

    const cloneMatch = path.match(/^\/api\/resources\/([^/]+)\/clone$/)
    if (cloneMatch) {
      store.clones.push(cloneMatch[1])
      const source = store.items.find(r => r.id === cloneMatch[1])!
      const copy = makeRes({ id: `copy-${store.items.length + 1}`, name: `${source.name} 副本`, visibility: 'private', source_id: source.id, usage_count: 0 })
      store.items.push(copy)
      return route.fulfill({ json: copy })
    }

    return route.fulfill({ json: {} })
  })
}

test('Agent 中心：列表渲染与新建按类型组装 content', async ({ page }) => {
  const store = { items: [makeRes()], creates: [] as unknown[], uses: [] as string[], clones: [] as string[] }
  await mockApis(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/agents')

  await expect(page.getByRole('heading', { name: 'Agent 中心' })).toBeVisible()
  await expect(page.locator('.rc-card')).toHaveCount(1)
  await expect(page.locator('.rc-card')).toContainText('日志分析助手')

  await page.getByRole('button', { name: '新建Agent' }).click()
  const dialog = page.locator('.n-modal')
  await expect(dialog).toBeVisible()
  await dialog.getByPlaceholder('例如：日志分析助手').fill('接口巡检助手')
  await dialog.getByPlaceholder(/描述角色、边界与输出格式/).fill('你是接口巡检助手')
  await dialog.getByText('read（读文件）').click()
  await dialog.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.rc-card')).toHaveCount(2)
  const payload = store.creates[0] as { kind: string; name: string; content: Record<string, unknown> }
  expect(payload.kind).toBe('agent')
  expect(payload.name).toBe('接口巡检助手')
  expect(payload.content).toMatchObject({ system_prompt: '你是接口巡检助手', tools: ['read'] })
})

test('Skills 中心：按路由切换类型，提交 markdown 字段', async ({ page }) => {
  const store = { items: [] as Res[], creates: [] as unknown[], uses: [] as string[], clones: [] as string[] }
  await mockApis(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/skills')

  await expect(page.getByRole('heading', { name: 'Skills 中心' })).toBeVisible()
  await expect(page.locator('.rc-empty')).toBeVisible()

  await page.getByRole('button', { name: '新建Skill' }).first().click()
  const dialog = page.locator('.n-modal')
  await dialog.getByPlaceholder('例如：日志分析助手').fill('日志排查技能')
  await dialog.getByPlaceholder(/支持 Markdown：适用场景/).fill('## 适用\n- 线上错误排查')
  await dialog.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.rc-card')).toHaveCount(1)
  const payload = store.creates[0] as { kind: string; content: Record<string, unknown> }
  expect(payload.kind).toBe('skill')
  expect(payload.content).toEqual({ markdown: '## 适用\n- 线上错误排查' })
})

test('使用与基于此创建：计数就地更新、副本入列表', async ({ page }) => {
  const store = { items: [makeRes()], creates: [] as unknown[], uses: [] as string[], clones: [] as string[] }
  await mockApis(page, store)
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/agents')

  await page.getByRole('button', { name: '使用' }).first().click()
  await expect(page.locator('.rc-card').first()).toContainText('使用 4')
  expect(store.uses).toEqual(['r-1'])

  await page.getByRole('button', { name: '基于此创建' }).first().click()
  await expect(page.locator('.rc-card')).toHaveCount(2)
  await expect(page.locator('.rc-card').nth(1)).toContainText('日志分析助手 副本')
  expect(store.clones).toEqual(['r-1'])
})

test('资源广场：精选卡与三榜渲染，飙升榜空态给出口径说明', async ({ page }) => {
  const store = {
    items: [makeRes(), makeRes({ id: 'r-2', kind: 'script', name: '日志聚合脚本', content: { language: 'python', code: 'print(1)' }, owner_name: 'Bob', usage_count: 1 })],
    creates: [] as unknown[], uses: [] as string[], clones: [] as string[],
  }
  await mockApis(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/plaza')

  await expect(page.getByRole('heading', { name: '资源广场' })).toBeVisible()
  await expect(page.locator('.pl-hero-card')).toHaveCount(2)
  await expect(page.locator('.pl-board')).toHaveCount(3)
  await expect(page.locator('.pl-board').nth(0)).toContainText('日志分析助手')
  await expect(page.locator('.pl-board').nth(1)).toContainText('近 7 日使用增长')
  await expect(page.locator('.pl-footnote')).toContainText('没有使用记录的资源不进飙升榜')

  // 空飙升榜：不给假数据，直接展示口径提示。
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\/resources\/plaza$/, route =>
    route.fulfill({ json: { total: 1, featured: [], popular: [], rising: [], newest: [] } }))
  await page.reload()
  await expect(page.locator('.pl-board').nth(1)).toContainText('近 7 天还没有新的使用记录')
})


test('RAG 中心：绑定知识库并可用固化口径试检索', async ({ page }) => {
  const store = { items: [] as Res[], creates: [] as unknown[], uses: [] as string[], clones: [] as string[] }
  await mockApis(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/rag')

  await expect(page.getByRole('heading', { name: 'RAG 中心' })).toBeVisible()
  await page.locator('.rc-head-actions button:has-text("新建RAG")').click()
  const dialog = page.locator('.n-modal')
  await dialog.getByPlaceholder('例如：日志分析助手').fill('退款检索口径')
  // 选知识库：点开下拉再选第一项
  await dialog.locator('.n-select').first().click()
  await page.locator('.n-base-select-option').first().click()
  await dialog.getByRole('button', { name: '保存' }).click()

  await expect(page.locator('.rc-card')).toHaveCount(1)
  const payload = store.creates[0] as { kind: string; content: Record<string, unknown> }
  expect(payload.kind).toBe('rag')
  expect(payload.content).toMatchObject({ kb_id: 'kb-1', mode: 'hybrid', k: 5 })

  // 详情里的试检索走真实 /api/kb/{id}/query
  await page.locator('.rc-card').first().getByRole('button', { name: '详情' }).click()
  const drawer = page.locator('.n-drawer')
  await expect(drawer).toBeVisible()
  await drawer.getByPlaceholder('输入一个问题，用这份口径检索一次').fill('退款多久内可以申请')
  await drawer.getByRole('button', { name: '检索' }).click()
  await expect(drawer.locator('.rc-probe-list li')).toHaveCount(1)
  await expect(drawer).toContainText('退款说明.md')
})

test('MCP 中心：只读通道状态与工具清单', async ({ page }) => {
  const store = { items: [] as Res[], creates: [] as unknown[], uses: [] as string[], clones: [] as string[] }
  await mockApis(page, store)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/mcp')

  await expect(page.getByRole('heading', { name: 'MCP 中心' })).toBeVisible()
  await expect(page.locator('.mc-channel')).toHaveCount(2)
  await expect(page.locator('.mc-channel').first()).toContainText('NativeToolExecutor')
  // 原生 2 个 + MCP 1 个，表头之外应为 3 行
  await expect(page.locator('.mc-row:not(.mc-row-head)')).toHaveCount(3)
  await expect(page.locator('.mc-tools')).toContainText('task.create')
  await expect(page.locator('.mc-note')).toContainText('不能指定任意第三方 MCP 地址')

  await page.getByRole('button', { name: '健康检查' }).click()
  await expect(page.locator('.mc-channel').first()).toContainText('原生通道已注册')
})
