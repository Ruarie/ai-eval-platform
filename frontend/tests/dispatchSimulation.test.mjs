import test from 'node:test'
import assert from 'node:assert/strict'
import {
  applyAssignLoad, applyReleaseLoad, isIdleLoad, computeProgress, pickTemplate, createMockTask,
} from '../src/utils/dispatchSimulation.ts'

test('分配负载封顶 96', () => {
  assert.equal(applyAssignLoad(0, 0), 24)
  assert.equal(applyAssignLoad(0, 1), 46)
  assert.equal(applyAssignLoad(90, 1), 96)
})

test('释放负载保底 4，并给出空闲判定', () => {
  assert.equal(applyReleaseLoad(96, 1), 44)
  assert.equal(applyReleaseLoad(10, 1), 4)
  assert.equal(isIdleLoad(29), true)
  assert.equal(isIdleLoad(30), false)
})

test('进度按耗时换算并封顶 99', () => {
  assert.equal(computeProgress(0, 1000, 1000), 0)
  assert.equal(computeProgress(1000, 1500, 1000), 50)
  assert.equal(computeProgress(1000, 9000, 1000), 99)
  assert.equal(computeProgress(1000, 2000, 0), 0)
})

test('模板选取不越界', () => {
  const tpls = ['a', 'b', 'c']
  assert.equal(pickTemplate(tpls, 0), 'a')
  assert.equal(pickTemplate(tpls, 0.999), 'c')
  assert.equal(pickTemplate(tpls, 1), 'c')
})

test('工单构造带 qid 与缺省 parentId', () => {
  const item = createMockTask(7, { kind: 'testcase', label: 'L', prio: 'P0' })
  assert.deepEqual(item, { qid: 'q-7', kind: 'testcase', label: 'L', prio: 'P0', parentId: null })
})
