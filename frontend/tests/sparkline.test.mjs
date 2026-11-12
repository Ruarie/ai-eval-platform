import test from 'node:test'
import assert from 'node:assert/strict'
import { sparkPoints } from '../src/utils/sparkline.ts'

test('少于两个点不画线', () => {
  assert.equal(sparkPoints([]), '')
  assert.equal(sparkPoints([5]), '')
})

test('首尾点贴边、纵向按极值归一', () => {
  const points = sparkPoints([0, 10]).split(' ')
  assert.equal(points.length, 2)
  assert.equal(points[0], '1.0,22.0')   // 最小值落在底边
  assert.equal(points[1], '75.0,2.0')   // 最大值落在顶边
})

test('全等序列退化为水平线', () => {
  const points = sparkPoints([3, 3, 3]).split(' ')
  assert.equal(points.length, 3)
  const ys = points.map(p => p.split(',')[1])
  assert.equal(new Set(ys).size, 1)  // 全等序列必须画成水平线
})

test('坐标数量与输入长度一致且递增', () => {
  const points = sparkPoints([1, 2, 0, 5, 4]).split(' ')
  assert.equal(points.length, 5)
  const xs = points.map(p => Number(p.split(',')[0]))
  for (let i = 1; i < xs.length; i += 1) assert.ok(xs[i] > xs[i - 1])
})
