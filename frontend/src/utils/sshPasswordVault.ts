/**
 * 远程（SSH）工作区临时密码的页面内存保管处。
 *
 * 安全取舍（代码质量报告 S4）：旧实现把 base64 密码写进 sessionStorage，
 * 任意注入脚本都能直接读出明文凭据。改为只保存在本模块闭包内的 Map：
 * - 不落 Web Storage，刷新或关闭页面即失效（用户需重新输入）；
 * - 不在其它标签页复用；
 * - 只在 HTTP 拦截器附加请求头时编码为 base64（请求头只允许可见 ASCII）。
 */

/** 旧版 sessionStorage 键前缀；仅用于清理升级前残留的明文密码。 */
export const LEGACY_SSH_PASSWORD_KEY_PREFIX = 'ae_ws_ssh_pwd:'

const vault = new Map<string, string>()

/** 保存某个工作区的 SSH 密码（空字符串视为清除）。 */
export function setSshPassword(workspaceId: string, password: string): void {
  if (!workspaceId) return
  if (!password) {
    vault.delete(workspaceId)
    return
  }
  vault.set(workspaceId, password)
}

/** 当前页面是否已为该工作区保存密码。 */
export function hasSshPassword(workspaceId: string): boolean {
  return vault.has(workspaceId)
}

/** 清除某个工作区已保存的密码。 */
export function clearSshPassword(workspaceId: string): void {
  vault.delete(workspaceId)
}

/** 清除全部已保存的密码（登出等场景使用）。 */
export function clearAllSshPasswords(): void {
  vault.clear()
}

/** 将 UTF-8 密码编码为 base64，供 X-Workspace-SSH-Password 请求头使用。 */
export function encodeSshPasswordHeader(password: string): string {
  const bytes = new TextEncoder().encode(password)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

/** 取得该工作区待附加的请求头值；未保存时返回 undefined。 */
export function sshPasswordHeaderFor(workspaceId: string): string | undefined {
  const password = vault.get(workspaceId)
  return password ? encodeSshPasswordHeader(password) : undefined
}

/**
 * 清理升级前写入 sessionStorage 的旧密码，避免明文凭据继续残留在存储中。
 * 非浏览器环境或存储不可用时静默跳过。
 */
export function purgeLegacySshPasswordStorage(storage?: Pick<Storage, 'length' | 'key' | 'removeItem'>): number {
  let target = storage
  try {
    if (!target && typeof window !== 'undefined') target = window.sessionStorage
  } catch {
    return 0
  }
  if (!target) return 0
  const stale: string[] = []
  try {
    for (let index = 0; index < target.length; index += 1) {
      const key = target.key(index)
      if (key && key.startsWith(LEGACY_SSH_PASSWORD_KEY_PREFIX)) stale.push(key)
    }
    for (const key of stale) target.removeItem(key)
  } catch {
    return 0
  }
  return stale.length
}
