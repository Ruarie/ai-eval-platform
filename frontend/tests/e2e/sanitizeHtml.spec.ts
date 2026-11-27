import { expect, test } from '@playwright/test'

/**
 * sanitizeHtml 依赖真实 DOM（DOMPurify），在浏览器中经 Vite 直接加载源码模块验证：
 * 攻击载荷被移除，Markdown 渲染器实际输出的受控标签与属性保持不变。
 */
type SanitizeModule = { sanitizeHtml: (html: string) => string }

test.beforeEach(async ({ page }) => {
  await page.route('**/api/**', route => route.fulfill({ status: 401, json: { code: 'UNAUTHORIZED', message: '未登录' } }))
  await page.goto('/login')
})

async function sanitize(page: import('@playwright/test').Page, inputs: string[]): Promise<string[]> {
  return page.evaluate(async (items) => {
    const mod = (await import('/src/utils/sanitizeHtml.ts')) as SanitizeModule
    return items.map(item => mod.sanitizeHtml(item))
  }, inputs)
}

test('移除脚本、事件属性与危险协议', async ({ page }) => {
  const outputs = await sanitize(page, [
    '<img src=x onerror="window.__xss=1">',
    '<script>window.__xss=1</script><p>ok</p>',
    '<a href="javascript:alert(1)">x</a>',
    '<a href="data:text/html,<script>alert(1)</script>">x</a>',
    '<svg><g onload="alert(1)"></g></svg>',
    '<iframe src="https://evil.example"></iframe><form action="/x"><input name="p"></form>',
    '<div style="x" onclick="alert(1)">t</div>',
  ])
  for (const out of outputs) {
    expect(out).not.toMatch(/onerror|onload|onclick|<script|javascript:|data:text|<iframe|<form|<input/i)
  }
  expect(outputs[1]).toBe('<p>ok</p>')
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined()
})

test('保留 Markdown 渲染器输出的受控结构', async ({ page }) => {
  const [table, link, copy, sameOrigin] = await sanitize(page, [
    '<div class="md-table-wrap"><table class="md-table"><thead><tr><th class="md-th align-center" style="text-align: center">列</th></tr></thead></table></div>',
    '<a href="https://example.com/a" target="_blank" class="md-link">链接 <span class="link-arrow">↗</span></a>',
    '<div class="md-mermaid-card" data-mermaid-code="graph%20TD"><button class="md-copy-btn" data-copy="a &lt; b" data-action="tab-code" type="button"><svg width="13" height="13" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13"></rect></svg></button><div class="md-mermaid-view-code" style="display: none;"></div></div>',
    '<a href="/api/workspaces/w1/files/raw?path=a.md&amp;download=true" target="_blank">下载</a>',
  ])
  expect(table).toContain('style="text-align: center"')
  expect(table).toContain('class="md-th align-center"')
  expect(link).toContain('href="https://example.com/a"')
  expect(link).toContain('target="_blank"')
  expect(link).toContain('rel="noopener noreferrer"')
  expect(copy).toContain('data-mermaid-code="graph%20TD"')
  expect(copy).toContain('data-copy="a &lt; b"')
  expect(copy).toContain('data-action="tab-code"')
  expect(copy).toContain('<svg')
  expect(copy).toContain('width="13"')
  expect(copy).toContain('viewBox="0 0 24 24"')
  expect(copy).toContain('style="display: none;"')
  expect(sameOrigin).toContain('href="/api/workspaces/w1/files/raw?path=a.md&amp;download=true"')
})
