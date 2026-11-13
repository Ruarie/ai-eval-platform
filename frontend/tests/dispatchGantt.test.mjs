import test from 'node:test'
import assert from 'node:assert/strict'
import { buildGanttRows, buildGanttTicks } from '../src/utils/dispatchGantt.ts'

const NOW = 1_700_000_000_000

test('空列表返回空', () => {
  assert.deepEqual(buildGanttRows([], NOW), [])
  assert.deepEqual(buildGanttTicks([], NOW, String), [])
})

test('百分比条按跨度归一，最短可见宽度生效', () => {
  const rows = buildGanttRows(
    [
      { id: 'a', start: NOW - 600_000, end: NOW },
      { id: 'b', start: NOW - 1000, end: NOW - 500 },   // 极短任务
    ],
    NOW,
  )
  const a = rows.find(r => r.id === 'a')
  assert.ok(Math.abs(a.left) < 1e-6)
  assert.ok(Math.abs(a.width - 100) < 1e-6)
  const b = rows.find(r => r.id === 'b')
  assert.ok(b.width >= 1.5)
})

test('子任务紧跟在父任务之后，父按开始时间排序', () => {
  const rows = buildGanttRows(
    [
      { id: 'p2', start: NOW - 300_000, end: NOW - 200_000 },
      { id: 'p1', start: NOW - 900_000, end: NOW - 700_000 },
      { id: 'c1', start: NOW - 800_000, end: NOW - 750_000, parentId: 'p1', isChild: true },
    ],
    NOW,
  )
  assert.deepEqual(rows.map(r => r.id), ['p1', 'c1', 'p2'])
})

test('父任务不在列表时，子任务按普通行参与排序', () => {
  const rows = buildGanttRows(
    [
      { id: 'c9', start: NOW - 200_000, end: NOW - 100_000, parentId: 'ghost', isChild: true },
      { id: 'p1', start: NOW - 900_000, end: NOW - 700_000 },
    ],
    NOW,
  )
  assert.equal(rows.length, 2)
  assert.equal(rows[0].id, 'p1')
})

test('刻度为 0/⅓/⅔/1 四档', () => {
  const ticks = buildGanttTicks(
    [{ id: 'a', start: NOW - 900_000, end: NOW }],
    NOW,
    ts => new Date(ts).toISOString(),
  )
  assert.equal(ticks.length, 4)
  assert.equal(ticks[0], new Date(NOW - 900_000).toISOString())
  assert.equal(ticks[3], new Date(NOW).toISOString())
})
