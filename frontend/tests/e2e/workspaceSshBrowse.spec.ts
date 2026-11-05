import { expect, test, type Page } from '@playwright/test'

const USER = {
  id: 'u-1', username: '联调成员', display_name: '联调成员', email: null, role: 'member',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

type BrowseCall = { path: string; password?: string }

async function setup(page: Page): Promise<{ calls: BrowseCall[] }> {
  const calls: BrowseCall[] = []
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/workspaces') return route.fulfill({ json: { items: [], total: 0, quota_bytes: 0 } })
    if (path === '/api/workspaces/ssh/browse') {
      const body = route.request().postDataJSON() as BrowseCall
      calls.push(body)
      // 第二次请求（点进 project）返回下一层；其余一律落到 /config
      if (body.path === '/config/project') {
        return route.fulfill({
          json: {
            host: 'build-01',
            path: '/config/project',
            parent: '/config',
            entries: [{ name: 'src', path: '/config/project/src' }],
          },
        })
      }
      return route.fulfill({
        json: {
          host: 'build-01',
          path: '/config',
          parent: '/',
          entries: [{ name: 'project', path: '/config/project' }],
        },
      })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/workspaces')
  await page.getByRole('button', { name: /新建工作区/ }).first().click()
  return { calls }
}

test('远程工作区可浏览服务器目录并回填根目录', async ({ page }) => {
  const { calls } = await setup(page)

  await page.locator('.modal-card select').first().selectOption('ssh')
  // 认证方式选择密码，并填入仅用于浏览的密码
  await page.locator('.modal-card select').nth(1).selectOption('password')
  await page.getByPlaceholder('例如：build-01 或 10.0.0.8').fill('build-01')
  await page.getByPlaceholder('例如：deploy').fill('deploy')
  await page.getByPlaceholder('输入该账号密码后可浏览远程目录').fill('TestPass123')

  await page.getByRole('button', { name: '浏览' }).click()

  // 目录选择弹窗：展示当前路径与子目录
  await expect(page.getByText('选择远程目录')).toBeVisible()
  await expect(page.getByRole('button', { name: /project/ })).toBeVisible()
  expect(calls[0].password).toBe('TestPass123')

  // 进入下一层后「选择当前目录」应回填该层路径
  await page.getByRole('button', { name: /project/ }).click()
  await expect(page.getByText('/config/project')).toBeVisible()
  await page.getByRole('button', { name: '选择当前目录' }).click()

  await expect(page.getByPlaceholder('/srv/workspace（可填 / 但权限更大）')).toHaveValue('/config/project')
})

test('未填连接信息时浏览给出提示而不是发起请求', async ({ page }) => {
  const { calls } = await setup(page)

  await page.locator('.modal-card select').first().selectOption('ssh')
  await page.getByRole('button', { name: '浏览' }).click()

  await expect(page.getByText('请先填写主机与登录用户')).toBeVisible()
  expect(calls.length).toBe(0)
})
