import test from 'node:test'
import assert from 'node:assert/strict'
import { describeFieldErrors, GENERIC_VALIDATION_MESSAGE } from '../src/api/fieldErrors.ts'

/** 字段级错误翻译：字段名要中文化，pydantic 英文原因要给出人话。 */

test('长度类错误翻译成中文并保留上限', () => {
  assert.equal(
    describeFieldErrors({ name: 'String should have at most 100 characters' }),
    '名称：最多 100 个字符',
  )
  assert.equal(
    describeFieldErrors({ password: 'String should have at least 8 characters' }),
    '密码：至少 8 个字符',
  )
})

test('必填与契约外字段用短结论，不加冒号', () => {
  assert.equal(describeFieldErrors({ username: 'Field required' }), '用户名必填')
  assert.equal(describeFieldErrors({ role: 'Extra inputs are not permitted' }), '角色不支持的字段')
})

test('多个字段只取前两条，其余折叠成计数', () => {
  const text = describeFieldErrors({
    username: 'Field required',
    password: 'String should have at least 8 characters',
    email: 'Input should be a valid string',
  })
  assert.equal(text, '用户名必填；密码：至少 8 个字符（另有 1 项）')
})

test('未收录的字段名与英文原因原样保留，不吞信息', () => {
  assert.equal(
    describeFieldErrors({ webhook_secret: 'Value error, 长度不合法' }),
    'webhook_secret：Value error, 长度不合法',
  )
})

test('空值与空对象返回空串，避免弹出空提示', () => {
  assert.equal(describeFieldErrors(undefined), '')
  assert.equal(describeFieldErrors(null), '')
  assert.equal(describeFieldErrors({}), '')
  assert.equal(describeFieldErrors({ name: '   ' }), '')
})

test('通用文案常量与后端保持一致', () => {
  assert.equal(GENERIC_VALIDATION_MESSAGE, '请检查标红字段')
})
