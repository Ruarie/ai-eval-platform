import { expect, test, type Page } from '@playwright/test'

/**
 * 深/浅双主题文字对比度契约（2026-11-18 第二轮缺陷批次）。
 *
 * 背景：部署版本 b5ef9db 上切换主题后出现「看不清字」，根因是两类历史遗留：
 * 1. `--bg-card` / `--bg-surface` / `--bg-tertiary` / `--border` 等令牌从未定义，
 *    19 处 `var(--bg-card, #fff)` 在深色下仍是白底，而文字已切到浅色 → 白底白字；
 * 2. 语义色（`--accent-success/warning/error`）兼作正文颜色，在白底上只有 2.3–2.5:1。
 *
 * 这里锁定：`/agent`、`/cases`、`/datasets` 三页在 light 与 dark 下，所有可见文字
 * 与其实际层叠背景的对比度都要满足 WCAG AA（正文 ≥4.5:1，大字号 ≥3:1）。
 * 计算方式与人工审计一致：自元素向上叠加半透明背景，渐变/图片按主题兜底色处理。
 */

const USER = { id: 'u-1', username: '联调成员', display_name: '联调成员', email: null, role: 'admin', disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null, created_at: '2026-01-01T00:00:00Z' }

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

const caseSet = { id: 'set-1', task_id: null, name: '支付链路用例集', status: 'generated', revision: 1, generated_count: 1, confirmed_count: 0, checks: [], column_schema: [] }
const caseRow = {
  id: 'c-1', code: 'TC-001', name: '余额充足场景下完成支付', strategy: '正向', priority: 'HX',
  module: '收银台', submodule: '支付', feature_point: '正常支付',
  precondition: '已登录且余额充足', steps: '1. 提交订单；2. 余额支付', expected: '支付成功',
  test_type: '回归', mapped: true, pending_complete: false,
}
const dataset = { id: 'ds-1', name: 'smoke-20 冒烟数据集', version: 3, row_count: 1, pending_complete_count: 1, metric: 'contain', owner: 'qa', column_schema: [], created_at: '2026-09-28T00:00:00Z' }

async function mockApis(page: Page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route(/^http:\/\/127\.0\.0\.1:5273\/api\//, route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = {}
    if (path === '/api/auth/me') body = USER
    else if (path === '/api/auth/ws-ticket') body = { ticket: 'ticket', expires_in: 300 }
    else if (path === '/api/sessions') body = [{ id: 's1', title: '联调会话', owner_id: 'u-1', visibility: 'private', can_manage: true, can_delete: true, engine_version: 'agent_loop_v2', workspace_id: 'ws-1', workspace_name: '默认工作区', created_at: '2026-09-09T00:00:00Z' }]
    else if (path.endsWith('/agent-ui')) body = agentUi
    else if (path === '/api/notifications/unread-count') body = { unread: 0 }
    else if (path === '/api/case-sets') body = { items: [caseSet] }
    else if (path === '/api/case-sets/set-1') body = { ...caseSet, cases: [caseRow] }
    else if (path === '/api/datasets') body = { items: [dataset] }
    else if (path === '/api/datasets/ds-1') body = { ...dataset, rows: [{ row_no: 1, question: '如何修改登录密码？', reference: '在右上角修改。', context: null }] }
    else if (path === '/api/profiles') body = []
    else if (path === '/api/workspaces') body = []
    else if (path === '/api/kb') body = { items: [] }
    return route.fulfill({ json: body })
  })
  await page.routeWebSocket(/\/ws\//, () => { /* 静默握手：布局断言不依赖帧 */ })
}

/** 页面内计算：收集所有可见文字的对比度违规项。 */
const AUDIT = `(() => {
  const P = (c) => { const m = String(c).match(/rgba?\\(([^)]+)\\)/); if (!m) return null; const p = m[1].split(/[,\\s\\/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const LU = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const CR = (a, b) => { const l1 = LU(a), l2 = LU(b); return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05); };
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const fallback = dark ? { r: 11, g: 15, b: 25, a: 1 } : { r: 247, g: 248, b: 250, a: 1 };
  const bgOf = (el) => {
    const layers = [];
    for (let n = el; n; n = n.parentElement) {
      const cs = getComputedStyle(n);
      const c = P(cs.backgroundColor);
      if (c && c.a > 0.001) { layers.push(c); if (c.a > 0.99) break; }
    }
    let base = fallback;
    const bodyC = P(getComputedStyle(document.body).backgroundColor);
    if (bodyC && bodyC.a > 0.99) base = bodyC;
    let cur = base;
    for (let i = layers.length - 1; i >= 0; i--) cur = over(layers[i], cur);
    return cur;
  };
  const bad = [];
  for (const el of document.querySelectorAll('body *')) {
    const text = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    if (!text) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) < 0.6) continue;
    if (el.closest('[aria-hidden="true"], .sr-only, script, style')) continue;
    const fg = P(cs.color); if (!fg || fg.a < 0.5) continue;
    const bg = bgOf(el);
    const fgc = fg.a < 1 ? over(fg, bg) : fg;
    const cr = CR(fgc, bg);
    const size = parseFloat(cs.fontSize), bold = Number(cs.fontWeight) >= 600;
    const min = (size >= 24 || (size >= 18.66 && bold)) ? 3 : 4.5;
    if (cr < min - 0.01) bad.push({ text: text.slice(0, 20), ratio: Math.round(cr * 100) / 100, color: cs.color, bg: 'rgb(' + Math.round(bg.r) + ',' + Math.round(bg.g) + ',' + Math.round(bg.b) + ')' });
  }
  return bad;
})()`

const routes = [
  { path: '/agent', ready: '.loop-tabs' },
  { path: '/cases', ready: '.toolbar-default' },
  { path: '/datasets', ready: '.main-dataset-title' },
]

for (const theme of ['light', 'dark'] as const) {
  test(`${theme} 主题下三页文字对比度满足 AA`, async ({ page }) => {
    await mockApis(page)
    await page.addInitScript((t) => localStorage.setItem('data-theme', t), theme)
    await page.setViewportSize({ width: 1440, height: 900 })
    for (const r of routes) {
      await page.goto(r.path)
      await expect(page.locator(r.ready).first()).toBeVisible()
      await page.waitForTimeout(400)
      const bad = await page.evaluate(AUDIT) as { text: string; ratio: number }[]
      expect(bad, `${theme} ${r.path} 存在低对比文字：${JSON.stringify(bad.slice(0, 5))}`).toHaveLength(0)
    }
  })
}

test('深色下卡片与语义色令牌不再回退到浅色值', async ({ page }) => {
  await mockApis(page)
  await page.addInitScript(() => localStorage.setItem('data-theme', 'dark'))
  await page.goto('/agent')
  await expect(page.locator('.loop-tabs')).toBeVisible()
  const tokens = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement)
    const read = (n: string) => cs.getPropertyValue(n).trim()
    return { card: read('--bg-card'), surface: read('--bg-surface'), border: read('--border'), solid: read('--accent-solid'), success: read('--accent-success') }
  })
  expect(tokens.card).not.toBe('#ffffff')
  expect(tokens.card).not.toBe('')
  expect(tokens.surface).not.toBe('#ffffff')
  expect(tokens.border).not.toBe('')
  expect(tokens.solid).not.toBe('')
  expect(tokens.success).not.toBe('')
})
