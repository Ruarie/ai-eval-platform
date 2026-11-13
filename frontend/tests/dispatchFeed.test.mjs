import test from 'node:test'
import assert from 'node:assert/strict'
import {
  mapWorkerRow, pushBoundedHistory, eventCategory, buildLogEntry, mergeActiveTasks,
} from '../src/utils/dispatchFeed.ts'

test('Worker 归一化：负载取整与缺省值', () => {
  const w = mapWorkerRow({ id: 'w1', name: 'worker-01', state: 'busy', load_percent: 73.6 })
  assert.equal(w.load, 74)
  assert.deepEqual(w.caps, [])
  assert.equal(w.ram, '—')
  assert.equal(w.task, null)
})

test('有界历史只保留最近 N 条', () => {
  const hist = []
  for (let i = 0; i < 30; i += 1) pushBoundedHistory(hist, i, 24)
  assert.equal(hist.length, 24)
  assert.equal(hist[0], 6)
  assert.equal(hist[23], 29)
})

test('事件分类：分配/完成/异常/节点', () => {
  assert.equal(eventCategory('ENQUEUE'), 'assign')
  assert.equal(eventCategory('start'), 'assign')
  assert.equal(eventCategory('succeeded'), 'done')
  assert.equal(eventCategory('FAIL'), 'error')
  assert.equal(eventCategory('heartbeat'), 'node')
})

test('日志条目时间戳固定 8 位且分类正确', () => {
  const entry = buildLogEntry('ASSIGN', '<b>q-1</b> → worker-01', 'q-1', new Date(2026, 0, 2, 3, 4, 5))
  assert.equal(entry.time.length, 8)
  assert.equal(entry.cat, 'assign')
  assert.equal(entry.tid, 'q-1')
})

test('多页任务合并去重并按创建时间倒序', () => {
  const merged = mergeActiveTasks(
    [{ id: 'a', created_at: '2026-01-01T00:00:00Z' }],
    [{ id: 'b', created_at: '2026-01-03T00:00:00Z' }, { id: 'a', created_at: '2026-01-01T00:00:00Z' }],
  )
  assert.deepEqual(merged.map(t => t.id), ['b', 'a'])
})
