import test from 'node:test'
import assert from 'node:assert/strict'
import {
  toEditableRow, toApiRow, isRowPending, countPendingRows, nextRowNo, renumberRows,
} from '../src/utils/datasetRows.ts'

test('服务端行转编辑态：别名与扩展列', () => {
  const row = toEditableRow({ row_no: 3, question: 'q1', reference: 'r1', context: null, level: 'P0' })
  assert.equal(row.q, 'q1')
  assert.equal(row.r, 'r1')
  assert.equal(row.c, '')
  assert.equal(row.difficulty, '简单')
  assert.deepEqual(row.extras, { level: 'P0' })
  assert.equal(row.checked, false)
})

test('兼容旧字段 q/r/c', () => {
  const row = toEditableRow({ row_no: 1, q: '问', r: '答', c: 'ctx' })
  assert.equal(row.q, '问')
  assert.equal(row.r, '答')
  assert.equal(row.c, 'ctx')
})

test('编辑态转提交结构：双别名 + 扩展列展开', () => {
  const api = toApiRow({
    row_no: 2, q: '问', r: '答', c: '', tags: 't', difficulty: '高',
    checked: true, extras: { level: 'P0' },
  })
  assert.equal(api.question, '问')
  assert.equal(api.reference, '答')
  assert.equal(api.context, null)
  assert.equal(api.level, 'P0')
  assert.equal('checked' in api, false)
})

test('待补全判定与计数', () => {
  const rows = [
    { row_no: 1, q: 'a', r: 'b' },
    { row_no: 2, q: 'a', r: '  ' },
    { row_no: 3, q: '', r: 'b' },
  ]
  assert.equal(isRowPending(rows[0]), false)
  assert.equal(isRowPending(rows[1]), true)
  assert.equal(countPendingRows(rows), 2)
})

test('下一行号与重排', () => {
  assert.equal(nextRowNo([]), 1)
  assert.equal(nextRowNo([{ row_no: 4 }, { row_no: 2 }]), 5)
  const rows = [{ row_no: 7 }, { row_no: 9 }]
  renumberRows(rows)
  assert.deepEqual(rows.map(r => r.row_no), [1, 2])
})
