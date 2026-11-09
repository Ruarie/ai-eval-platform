import assert from 'node:assert/strict'
import test from 'node:test'

import {
  casePayload,
  createEmptyCase,
  editableCase,
  getCaseExtra,
  highlightText,
  normalizeCaseStrategy,
} from '../src/utils/caseWorkbench.ts'

test('策略别名归一为页面策略', () => {
  assert.equal(normalizeCaseStrategy('等价'), '等价类')
  assert.equal(normalizeCaseStrategy('状态'), '状态迁移')
  assert.equal(normalizeCaseStrategy('反向'), '反向')
  assert.equal(normalizeCaseStrategy(''), '正向')
})

test('服务端用例转为可编辑行并保留扩展字段', () => {
  const row = editableCase(
    {
      id: 'c1',
      code: 'TC-001',
      name: '登录成功',
      module: '登录',
      strategy: '等价',
      priority: 'HX',
      precondition: '已注册',
      steps: '1. 输入手机号\n2. 点击登录',
      expected: '进入首页',
      custom_owner: 'qa',
    },
    'set-1',
    0,
  )
  assert.equal(row.strategy, '等价类')
  assert.deepEqual(row.steps, ['1. 输入手机号', '2. 点击登录'])
  assert.equal(getCaseExtra(row, 'custom_owner'), 'qa')
  assert.equal(row.source?.id, 'c1')
})

test('编辑行回写为契约字段，临时 ID 不提交', () => {
  const row = editableCase(
    {
      id: 'temp-1',
      name: '登录成功',
      module: '登录',
      strategy: '正向',
      priority: 'HX',
      precondition: '已注册',
      steps: '1. 输入手机号',
      expected: '进入首页',
      custom_owner: 'qa',
    },
    'set-1',
    0,
  )
  row.steps = ['1. 输入手机号', '2. 点击登录']
  row.expected_result = '进入工作台'
  const payload = casePayload(row)
  assert.equal(payload.id, undefined)
  assert.equal(payload.precondition, '已注册')
  assert.equal(payload.steps, '1. 输入手机号\n2. 点击登录')
  assert.equal(payload.expected, '进入工作台')
  assert.equal(payload.custom_owner, 'qa')
})

test('搜索高亮只输出转义文本与 mark 标签', () => {
  const html = highlightText('<script>登录</script>', '登录')
  assert.ok(html.includes('&lt;script&gt;'))
  assert.ok(html.includes('<mark class="highlight-match">登录</mark>'))
  assert.ok(!html.includes('<script>'))
})

test('空查询返回转义文本且不添加标记', () => {
  assert.equal(highlightText('a&b', ''), 'a&amp;b')
})

test('新建空用例带三位编号与默认策略', () => {
  const row = createEmptyCase('set-1', 7)
  assert.equal(row.set_id, 'set-1')
  assert.equal(row.code, 'TC-007')
  assert.equal(row.strategy, '正向')
  assert.deepEqual(row.steps, ['1. 执行标准输入'])
  assert.ok(row.id.startsWith('temp-'))
})
