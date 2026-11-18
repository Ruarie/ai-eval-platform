import { expect, test, type Page } from '@playwright/test'

/**
 * 窄屏与主题回归契约（2026-11-18 UI 全量测试缺陷批次）。
 *
 * 背景：部署版本（d75bc840）在 1440×900 与 780×700 下存在三处布局缺陷：
 * 1. 深色模式下对话/轨迹标签栏沿用浅色底 rgba(255,255,255,.68)，选中标签
 *    （浅紫 #a5b4fc）落在浅底上对比度接近 1:1，文字不可读；
 * 2. 数据集详情顶栏在 ≤1440px 被 flex 压缩，标题断成窄列、状态徽标逐字竖排；
 * 3. 聊天壳写死 min-width:520px，780px 视口下比容器宽 100px，内部出现横向滚动条。
 * 另外移动端 390px 输入区控件被压成「思/考/高/强/度」竖排。
 *
 * 本文件锁定四条不变量：标签栏跟随主题、标题单行且徽标横排、聊天壳不溢出、
 * 输入区控件的思考强度文案保持横向可读。
 */

const USER = { id: 'u-1', username: '联调成员', display_name: '联调成员', email: null, role: 'admin', disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null, created_at: '2026-01-01T00:00:00Z' }

const dataset = {
  id: 'ds-1', name: 'smoke-20 冒烟数据集', version: 3, row_count: 1, pending_complete_count: 1,
  metric: 'contain', owner: 'qa', column_schema: [], created_at: '2026-09-28T00:00:00Z',
}

const agentUi = {
  version: 1, enabled: true,
  profile: { id: 'p1', name: 'DeepSeek 协议档', version: 'v1', model: 'deepseek-chat', protocol: 'openai_chat', allowed_efforts: ['off', 'high'], default_effort: 'high' },
  profiles: [{ id: 'p1', name: 'DeepSeek 协议档', version: 'v1', model: 'deepseek-chat', protocol: 'openai_chat', allowed_efforts: ['off', 'high'], default_effort: 'high' }],
  agent: 'general',
  agents: [{ id: 'general', name: '通用助手', description: '平台默认助手', badge: '通用', default: true }],
  allowed_efforts: ['off', 'high'], default_effort: 'high',
  permissions: { write: true, trace: true, reasoning: true, interactions: true, settings: true },
  controller: { active: false, owned_by_actor: false },
  attachments: { upload_suffixes: ['.txt'], inline_suffixes: ['.txt'], image_suffixes: [], max_bytes: 20971520, max_image_bytes: 4194304, content_required: true },
}

/** 页面与 WS 都使用契约夹具：只验证布局，不把夹具当供应商闭环。 */
async function mockApis(page: Page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    let body: unknown = {}
    if (path === '/api/auth/me') body = USER
    else if (path === '/api/auth/ws-ticket') body = { ticket: 'ticket', expires_in: 300 }
    else if (path === '/api/sessions') body = [{ id: 's1', title: '联调会话', owner_id: 'u-1', visibility: 'private', can_manage: true, can_delete: true, engine_version: 'agent_loop_v2', workspace_id: 'ws-1', workspace_name: '默认工作区', created_at: '2026-09-09T00:00:00Z' }]
    else if (path.endsWith('/agent-ui')) body = agentUi
    else if (path === '/api/notifications/unread-count') body = { unread: 0 }
    else if (path === '/api/datasets') body = { items: [dataset] }
    else if (path === '/api/datasets/ds-1') body = { ...dataset, rows: [{ row_no: 1, question: '如何修改登录密码？', reference: '在右上角修改。', context: null }] }
    else if (path === '/api/profiles') body = []
    else if (path === '/api/workspaces') body = []
    else if (path === '/api/kb') body = { items: [] }
    return route.fulfill({ json: body })
  })
  await page.routeWebSocket(/\/ws\//, () => { /* 静默握手：布局断言不依赖帧 */ })
}

test.describe('窄屏与主题布局契约', () => {
  test('深色模式下对话标签栏不保留浅色底，选中标签可读', async ({ page }) => {
    await mockApis(page)
    await page.addInitScript(() => localStorage.setItem('data-theme', 'dark'))
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/agent')
    const bar = page.locator('.loop-tabs')
    await expect(bar).toBeVisible()
    const style = await bar.evaluate((el) => {
      const cs = getComputedStyle(el)
      const active = el.querySelector('.workspace-tab.active')
      return { bg: cs.backgroundColor, color: active ? getComputedStyle(active).color : '' }
    })
    // 浅色态的 rgba(255,255,255,.68) 在深色下会形成浅色带；深色必须是透明或深色底。
    expect(style.bg === 'rgba(0, 0, 0, 0)' || style.bg.startsWith('rgba(15') || style.bg.startsWith('rgb(1')).toBe(true)
    expect(style.color).not.toBe('rgb(97, 119, 106)')
  })

  test('1440px 数据集顶栏标题单行、徽标横排', async ({ page }) => {
    await mockApis(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/datasets')
    const title = page.locator('.main-dataset-title')
    await expect(title).toBeVisible()
    const box = await title.boundingBox()
    expect(box!.height).toBeLessThan(32)               // 竖排时会断成 4 行、高度 > 60
    const badges = page.locator('.title-row > *:not(.main-dataset-title)')
    const count = await badges.count()
    expect(count).toBeGreaterThanOrEqual(2)
    for (let i = 0; i < count; i++) {
      const b = await badges.nth(i).boundingBox()
      expect(b!.height).toBeLessThan(26)               // 逐字竖排会拉高到 100px 以上
      expect(b!.width).toBeGreaterThan(24)
    }
  })

  test('780px 聊天区不产生内部横向溢出', async ({ page }) => {
    await mockApis(page)
    await page.setViewportSize({ width: 780, height: 700 })
    await page.goto('/agent')
    await expect(page.locator('.agent-layout')).toBeVisible()
    const sizes = await page.evaluate(() => {
      const layout = document.querySelector('.agent-layout') as HTMLElement
      const shell = document.querySelector('.loop-chat-shell') as HTMLElement
      return { layoutOver: layout.scrollWidth - layout.clientWidth, shellOver: shell ? shell.scrollWidth - shell.clientWidth : 0 }
    })
    expect(sizes.layoutOver).toBeLessThanOrEqual(1)
    expect(sizes.shellOver).toBeLessThanOrEqual(16)    // 仅允许缩放手柄（绝对定位）外溢
  })

  test('390px 输入区思考强度文案保持横向可读', async ({ page }) => {
    await mockApis(page)
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/agent')
    const copy = page.locator('.thinking-copy')
    await expect(copy).toBeVisible()
    const box = await copy.boundingBox()
    expect(box!.width).toBeGreaterThan(24)             // 被压缩时宽度只有 11px
    expect(box!.height).toBeLessThan(40)               // 竖排时高度 55px
    const model = page.locator('.composer-bottom .model-trigger').filter({ hasText: 'deepseek' })
    const modelBox = await model.boundingBox()
    expect(modelBox!.width).toBeGreaterThan(60)        // 被截成「de…」时只有 60px 出头
  })
})
