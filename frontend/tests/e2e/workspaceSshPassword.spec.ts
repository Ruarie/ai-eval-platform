import { expect, test, type Page } from '@playwright/test'

const USER = {
  id: 'u-1', username: '联调成员', display_name: '联调成员', email: null, role: 'member',
  disabled: false, must_change_password: false, last_login_at: null, last_login_ip: null,
  created_at: '2026-01-01T00:00:00Z',
}

const WS_PASSWORD = {
  id: 'ws-pwd', name: '密码认证主机', owner_id: 'u-1', kind: 'ssh', auth_type: 'password',
  ssh_host: 'build-02', ssh_port: 22, ssh_user: 'deploy', ssh_key_name: null,
  remote_root: '/srv/app', created_at: '2026-11-05T00:00:00Z', updated_at: '2026-11-05T00:00:00Z',
  deleted: false, quota_bytes: 0, folder: { files: 0, bytes: 0 },
}

type Seen = { passwords: string[] }

async function setup(page: Page): Promise<Seen> {
  const seen: Seen = { passwords: [] }
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/workspaces') return route.fulfill({ json: { items: [WS_PASSWORD], total: 1, quota_bytes: 0 } })
    if (path === `/api/workspaces/${WS_PASSWORD.id}`) return route.fulfill({ json: WS_PASSWORD })
    if (path === `/api/workspaces/${WS_PASSWORD.id}/files/tree`) {
      const header = route.request().headers()['x-workspace-ssh-password'] || ''
      if (header) seen.passwords.push(Buffer.from(header, 'base64').toString('utf-8'))
      return route.fulfill({ json: { tree: [] } })
    }
    if (path === `/api/workspaces/${WS_PASSWORD.id}/files`) {
      const header = route.request().headers()['x-workspace-ssh-password'] || ''
      if (header) seen.passwords.push(Buffer.from(header, 'base64').toString('utf-8'))
      return route.fulfill({ json: { entries: [], total: 0 } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/workspaces')
  return seen
}

test('密码认证工作区提供独立的「SSH 密码」入口', async ({ page }) => {
  await setup(page)
  await expect(page.getByRole('button', { name: '🔑' })).toBeVisible()
})

test('保存密码后请求头会带上 base64 密码，且密码不写入浏览器存储', async ({ page, context }) => {
  const seen = await setup(page)

  await page.getByRole('button', { name: '🔑' }).click()
  await page.getByPlaceholder('输入目标机该账号的密码').fill('TestPass123')
  await page.getByRole('button', { name: '保存到本次会话' }).click()

  await expect(page.getByRole('button', { name: '🔓' })).toBeVisible()
  await expect.poll(() => seen.passwords.includes('TestPass123')).toBe(true)

  // 密码只在页面内存：sessionStorage / localStorage 中都不应出现明文或 base64 形式。
  const storages = await page.evaluate(() => JSON.stringify({ ...window.sessionStorage, ...window.localStorage }))
  expect(storages).not.toContain('TestPass123')
  expect(storages).not.toContain(Buffer.from('TestPass123').toString('base64'))

  // 新标签页不复用密码，仍显示未设置状态的 🔑 入口。
  const fresh = await context.newPage()
  await setup(fresh)
  await expect(fresh.getByRole('button', { name: '🔑' })).toBeVisible()
  await fresh.close()
})

test('刷新页面后密码失效，请求不再携带密码头', async ({ page }) => {
  const seen = await setup(page)
  await page.getByRole('button', { name: '🔑' }).click()
  await page.getByPlaceholder('输入目标机该账号的密码').fill('TestPass123')
  await page.getByRole('button', { name: '保存到本次会话' }).click()
  await expect.poll(() => seen.passwords.length).toBeGreaterThan(0)

  const before = seen.passwords.length
  await page.reload()
  await expect(page.getByRole('button', { name: '🔑' })).toBeVisible()
  expect(seen.passwords.length).toBe(before)
})

test('升级前残留在 sessionStorage 的旧密码会被清理', async ({ page }) => {
  await page.addInitScript(() => {
    window.sessionStorage.setItem('ae_ws_ssh_pwd:ws-pwd', btoa('LegacyPass1'))
  })
  const seen = await setup(page)
  await expect(page.getByRole('button', { name: '🔑' })).toBeVisible()
  const legacy = await page.evaluate(() => window.sessionStorage.getItem('ae_ws_ssh_pwd:ws-pwd'))
  expect(legacy).toBeNull()
  expect(seen.passwords).not.toContain('LegacyPass1')
})
