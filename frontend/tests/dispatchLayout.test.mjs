import test from 'node:test'
import assert from 'node:assert/strict'
import { polarPoint, wedgePath, workerLane, truncate } from '../src/utils/dispatchLayout.ts'

test('极坐标按方位角换算', () => {
  const p0 = polarPoint(100, 100, 0, 10)
  assert.ok(Math.abs(p0.x - 110) < 1e-9 && Math.abs(p0.y - 100) < 1e-9)
  const p90 = polarPoint(100, 100, 90, 10)
  assert.ok(Math.abs(p90.x - 100) < 1e-9 && Math.abs(p90.y - 110) < 1e-9)
})

test('负角度与 180° 落在对称位置', () => {
  const left = polarPoint(50, 50, 180, 20)
  assert.ok(Math.abs(left.x - 30) < 1e-9 && Math.abs(left.y - 50) < 1e-9)
  const up = polarPoint(50, 50, -90, 20)
  assert.ok(Math.abs(up.x - 50) < 1e-9 && Math.abs(up.y - 30) < 1e-9)
})

test('扇区路径以内核为起点、以 A 弧收口', () => {
  const d = wedgePath(200, 200, 0, 30, 120)
  assert.ok(d.startsWith('M 200 200 L '))
  assert.ok(d.includes(' A 120 120 0 0 1 '))
  assert.ok(d.endsWith(' Z'))
})

test('Worker 扇区归属取首个命中，未命中为 general', () => {
  assert.equal(workerLane(['stress', 'testcase'], ['testcase', 'stress']), 'testcase')
  assert.equal(workerLane(['unknown'], ['testcase', 'stress']), 'general')
  assert.equal(workerLane([], ['testcase']), 'general')
})

test('文本截断保留长度并补省略号', () => {
  assert.equal(truncate('abcdef', 10), 'abcdef')
  assert.equal(truncate('abcdef', 6), 'abcdef')
  assert.equal(truncate('abcdefg', 6), 'abcde…')
  assert.equal(truncate('abcdefg', 6).length, 6)
})
