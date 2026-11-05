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

const WS = {
  id: 'ws-ssh',
  name: '远程构建机',
  owner_id: 'u-1',
  kind: 'ssh',
  ssh_host: 'build-01',
  ssh_port: 22,
  ssh_user: 'deploy',
  ssh_key_name: 'id_ed25519_remote1',
  remote_root: '/srv/app',
  created_at: '2026-11-05T00:00:00Z',
  updated_at: '2026-11-05T00:00:00Z',
  deleted: false,
  quota_bytes: 0,
  folder: { files: 0, bytes: 0 },
}

type Calls = { request: number; confirm: number; reject: number }

async function setup(page: Page): Promise<Calls> {
  const calls: Calls = { request: 0, confirm: 0, reject: 0 }
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (!path.startsWith('/api/')) return route.continue()
    if (path === '/api/auth/me') return route.fulfill({ json: USER })
    if (path === '/api/workspaces') {
      return route.fulfill({ json: { items: [WS], total: 1, quota_bytes: 0 } })
    }
    if (path === `/api/workspaces/${WS.id}`) return route.fulfill({ json: WS })
    if (path === `/api/workspaces/${WS.id}/files/tree`) return route.fulfill({ json: { tree: [] } })
    if (path === `/api/workspaces/${WS.id}/files`) {
      return route.fulfill({ json: { entries: [], total: 0 } })
    }
    if (path === `/api/workspaces/${WS.id}/exec` && route.request().method() === 'POST') {
      calls.request += 1
      return route.fulfill({
        status: 202,
        json: {
          approval_id: 'ap-1',
          status: 'pending',
          expires_in_s: 300,
          preview: { host: 'build-01', root: '/srv/app', command: 'ls -la', timeout_s: 60 },
        },
      })
    }
    if (path === `/api/workspaces/${WS.id}/exec/ap-1/confirm`) {
      calls.confirm += 1
      return route.fulfill({
        json: {
          approval_id: 'ap-1',
          exit_code: 0,
          stdout: 'total 0\n-rw-r--r-- 1 deploy users 12 hello.txt',
          stderr: '',
          truncated: false,
          host: 'build-01',
          root: '/srv/app',
        },
      })
    }
    if (path === `/api/workspaces/${WS.id}/exec/ap-1/reject`) {
      calls.reject += 1
      return route.fulfill({ json: { approval_id: 'ap-1', status: 'rejected' } })
    }
    return route.fulfill({ json: {} })
  })
  await page.goto('/workspaces')
  await expect(page.getByRole('button', { name: '⌘' })).toBeVisible()
  return calls
}

test('远程命令先登记审批、确认后才执行', async ({ page }) => {
  const calls = await setup(page)

  await page.getByRole('button', { name: '⌘' }).click()
  await expect(page.getByText('远程命令')).toBeVisible()
  await expect(page.locator('.exec-hint')).toContainText('build-01:/srv/app')

  const command = page.getByPlaceholder('例如：git status && ls -la')
  await command.click()
  await page.keyboard.type('ls -la')
  await expect(command).toHaveValue('ls -la')
  const submit = page.getByRole('button', { name: '请求执行' })
  await expect(submit).toBeEnabled()
  await submit.click()

  // 第一步只登记，不应触发执行
  await expect.poll(() => calls.request).toBe(1)
  expect(calls.confirm).toBe(0)
  // 确认区展示目标与完整命令
  await expect(page.locator('.exec-code').first()).toHaveText('ls -la')
  await expect(page.getByText(/确认后立即执行/)).toBeVisible()

  await page.getByRole('button', { name: '确认执行' }).click()
  await expect.poll(() => calls.confirm).toBe(1)
  await expect(page.getByText('退出码：0')).toBeVisible()
  await expect(page.locator('.exec-code').first()).toContainText('hello.txt')
})

test('远程命令可以取消，取消后不再执行', async ({ page }) => {
  const calls = await setup(page)

  await page.getByRole('button', { name: '⌘' }).click()
  await page.getByPlaceholder('例如：git status && ls -la').fill('rm -rf /tmp/x')
  await page.getByRole('button', { name: '请求执行' }).click()
  await expect.poll(() => calls.request).toBe(1)

  await page.getByRole('button', { name: '取消' }).click()
  await expect.poll(() => calls.reject).toBe(1)
  expect(calls.confirm).toBe(0)
  // 取消后回到输入态，不展示执行结果
  await expect(page.locator('.exec-code')).toHaveCount(0)
})
