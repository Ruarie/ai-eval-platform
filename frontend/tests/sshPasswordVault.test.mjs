import test from 'node:test'
import assert from 'node:assert/strict'
import {
  LEGACY_SSH_PASSWORD_KEY_PREFIX,
  clearAllSshPasswords,
  clearSshPassword,
  encodeSshPasswordHeader,
  hasSshPassword,
  purgeLegacySshPasswordStorage,
  setSshPassword,
  sshPasswordHeaderFor,
} from '../src/utils/sshPasswordVault.ts'

/** 最小 Storage 替身：只实现清理逻辑用到的 length/key/removeItem。 */
function fakeStorage(entries) {
  const map = new Map(Object.entries(entries))
  return {
    get length() { return map.size },
    key(index) { return [...map.keys()][index] ?? null },
    removeItem(key) { map.delete(key) },
    snapshot() { return Object.fromEntries(map) },
  }
}

test('SSH 密码只按工作区隔离保存，未保存时不附加请求头', () => {
  clearAllSshPasswords()
  assert.equal(sshPasswordHeaderFor('ws-a'), undefined)
  setSshPassword('ws-a', 'Pass-A1')
  assert.equal(hasSshPassword('ws-a'), true)
  assert.equal(hasSshPassword('ws-b'), false)
  assert.equal(Buffer.from(sshPasswordHeaderFor('ws-a'), 'base64').toString('utf-8'), 'Pass-A1')
  assert.equal(sshPasswordHeaderFor('ws-b'), undefined)
})

test('清除单个、空密码与登出全清', () => {
  clearAllSshPasswords()
  setSshPassword('ws-a', 'Pass-A1')
  setSshPassword('ws-b', 'Pass-B1')
  clearSshPassword('ws-a')
  assert.equal(hasSshPassword('ws-a'), false)
  setSshPassword('ws-b', '')
  assert.equal(hasSshPassword('ws-b'), false, '空字符串视为清除')
  setSshPassword('ws-c', 'Pass-C1')
  clearAllSshPasswords()
  assert.equal(hasSshPassword('ws-c'), false)
})

test('请求头编码支持中文与特殊字符（UTF-8 后 base64，仅含可见 ASCII）', () => {
  const password = '密码-p@ss:word/Ω'
  const encoded = encodeSshPasswordHeader(password)
  assert.match(encoded, /^[A-Za-z0-9+/=]+$/)
  assert.equal(Buffer.from(encoded, 'base64').toString('utf-8'), password)
})

test('升级清理只删除旧版 SSH 密码键，不影响其它会话存储', () => {
  const storage = fakeStorage({
    [`${LEGACY_SSH_PASSWORD_KEY_PREFIX}ws-1`]: 'bGVnYWN5',
    [`${LEGACY_SSH_PASSWORD_KEY_PREFIX}ws-2`]: 'bGVnYWN5Mg==',
    'ae_dynamic_import_retry': '/agent',
  })
  assert.equal(purgeLegacySshPasswordStorage(storage), 2)
  assert.deepEqual(storage.snapshot(), { 'ae_dynamic_import_retry': '/agent' })
})

test('无浏览器存储时清理静默跳过', () => {
  assert.equal(purgeLegacySshPasswordStorage(), 0)
})
