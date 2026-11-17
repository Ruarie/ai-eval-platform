import { expect, test, type Page } from '@playwright/test'

/**
 * 用例工作台顶栏布局契约。
 *
 * 背景：草稿态用例集的工具项（新增用例/新增列/AI 评审/评审工作台/需求覆盖/
 * PRD 推导向导/保存修改/确认入库/更多）在 1440×900、1512×950 这类笔记本视口
 * 下总宽超过容器，历史实现让 flex 直接压缩标题列，导致标题逐字竖排、右侧
 * 「保存修改」「确认入库」被挤出视口且页面没有横向滚动条，草稿集无法保存入库。
 *
 * 这里锁定两条不变量：
 * 1. 标题行保持单行（高度 <= 32px），不被压缩成竖排；
 * 2. 关键写操作按钮完整落在视口内（right <= innerWidth），折行而不是溢出。
 * 另外锁定已入库用例集的只读提示：不再显示「Enter 编辑」快捷键，改为只读说明。
 */

const USER = {
  id: 'u-1',
  username: '联调成员',
  display_name: '联调成员',
  email: null,
  role: 'admin',
  disabled: false,
  must_change_password: false,
  last_login_at: null,
  last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

const generatedSet = {
  id: 'gen-1', task_id: null, name: '支付链路草稿用例集', status: 'generated',
  revision: 1, generated_count: 1, confirmed_count: 0, checks: [], column_schema: [],
}
const confirmedSet = {
  id: 'conf-1', task_id: null, name: '已入库用例集', status: 'confirmed',
  revision: 2, generated_count: 1, confirmed_count: 1, checks: [], column_schema: [],
}

/** 单行用例夹具：字段与后端 CaseOut 同形，足够渲染整行网格。 */
function row(id = 'row-1', code = 'TC-001') {
  return {
    id, code, name: '余额充足场景下完成支付', strategy: '正向', priority: 'HX',
    module: '收银台', submodule: '支付', feature_point: '正常支付',
    precondition: '已登录且余额充足', steps: '1. 提交订单；2. 余额支付', expected: '支付成功',
    test_type: '回归', mapped: true, pending_complete: false,
  }
}

async function setup(page: Page) {
  await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }))
  await page.route('https://fonts.gstatic.com/**', route => route.fulfill({ body: '' }))
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/notifications/unread-count') return route.fulfill({ json: { unread: 0 } })
    if (path === '/api/case-sets') return route.fulfill({ json: { items: [generatedSet, confirmedSet] } })
    if (path === '/api/case-sets/gen-1') return route.fulfill({ json: { ...generatedSet, cases: [row()] } })
    if (path === '/api/case-sets/conf-1') return route.fulfill({ json: { ...confirmedSet, cases: [row('row-2', 'TC-002')] } })
    return route.fulfill({ json: {} })
  })
}

/** 关键写操作在给定视口下必须完整可见。 */
async function expectWritable(page: Page) {
  const report = await page.evaluate(() => {
    const vw = window.innerWidth
    const pick = (label: string) => {
      const el = [...document.querySelectorAll('button')].find(b => (b.innerText || '').includes(label))
      if (!el) return { label, found: false }
      const rect = el.getBoundingClientRect()
      return { label, found: true, right: Math.round(rect.right), width: Math.round(rect.width) }
    }
    const title = document.querySelector('.main-dataset-title') as HTMLElement | null
    const rect = title?.getBoundingClientRect()
    return {
      vw,
      titleText: title?.textContent?.trim() ?? '',
      titleHeight: rect ? Math.round(rect.height) : 0,
      titleWidth: rect ? Math.round(rect.width) : 0,
      buttons: ['保存修改', '确认入库', 'PRD 推导向导', '新增用例'].map(pick),
      docScrollWidth: document.documentElement.scrollWidth,
    }
  })
  // 标题不得逐字换行：单行高度 / 宽度明显大于单字宽度
  expect(report.titleHeight, `标题被压成竖排：${JSON.stringify(report)}`).toBeLessThanOrEqual(32)
  expect(report.titleWidth, `标题宽度过窄：${JSON.stringify(report)}`).toBeGreaterThan(40)
  // 关键按钮全部在视口内，且没有被压扁
  for (const btn of report.buttons) {
    expect(btn.found, `找不到按钮 ${btn.label}`).toBe(true)
    expect(btn.right! , `按钮 ${btn.label} 溢出视口 ${report.vw}px：${JSON.stringify(report)}`).toBeLessThanOrEqual(report.vw + 1)
    expect(btn.width!, `按钮 ${btn.label} 宽度异常`).toBeGreaterThan(40)
  }
  // 页面不产生横向滚动（折行消化了溢出）
  expect(report.docScrollWidth).toBeLessThanOrEqual(report.vw + 1)
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 1512, height: 950 }, { width: 1280, height: 800 }]) {
  test(`草稿用例集顶栏在 ${viewport.width}×${viewport.height} 不塌陷`, async ({ page }) => {
    await setup(page)
    await page.setViewportSize(viewport)
    await page.goto('/cases?set_id=gen-1')
    await expect(page.locator('.main-dataset-title')).toHaveText(generatedSet.name)
    await expectWritable(page)
  })
}

test('已入库用例集展示只读提示，不再提示可编辑', async ({ page }) => {
  await setup(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/cases?set_id=conf-1')
  await expect(page.locator('.main-dataset-title')).toHaveText(confirmedSet.name)
  await expect(page.locator('.readonly-hint')).toBeVisible()
  await expect(page.locator('.keyboard-flow-hint')).toHaveCount(0)
  // 点击单元格不再点亮「可编辑光标」
  await page.locator('table tbody tr td.cell-edit').first().click()
  await expect(page.locator('table td.cell-cursor')).toHaveCount(0)
  // Enter 不进入编辑态
  await page.keyboard.press('Enter')
  await expect(page.locator('table textarea')).toHaveCount(0)
})

test('全局搜索面板在失焦后仍可用 Esc 关闭', async ({ page }) => {
  await setup(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/cases?set_id=conf-1')
  await page.locator('.topbar-search-btn').click()
  await expect(page.locator('.gs-panel')).toBeVisible()
  // 主动把焦点移出输入框，模拟点击分组标题/结果区的场景
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
  await page.keyboard.press('Escape')
  await expect(page.locator('.gs-panel')).toHaveCount(0)
})

test('用例表空态不被 1700px 表格横向裁切', async ({ page }) => {
  await setup(page)
  await page.setViewportSize({ width: 1440, height: 900 })
  const emptySet = { ...generatedSet, id: 'empty-1', name: '空用例集', generated_count: 0 }
  // 后注册的路由优先：把空用例集加进列表，并返回空 cases。
  await page.route('**/api/case-sets', route => route.fulfill({ json: { items: [generatedSet, confirmedSet, emptySet] } }))
  await page.route('**/api/case-sets/empty-1', route => route.fulfill({ json: { ...emptySet, cases: [] } }))
  await page.goto('/cases?set_id=empty-1')
  const empty = page.locator('.cases-empty')
  await expect(empty).toBeVisible()
  const box = await empty.locator('.empty-message').boundingBox()
  expect(box).not.toBeNull()
  // 空态文案必须完整落在视口内
  expect(box!.x + box!.width).toBeLessThanOrEqual(1440)
  expect(box!.x).toBeGreaterThanOrEqual(0)
})
