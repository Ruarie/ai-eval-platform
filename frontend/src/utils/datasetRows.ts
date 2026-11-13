/** 数据集行在「服务端结构」与「可编辑结构」之间的纯映射与校验。 */

export interface ApiRow {
  row_no: number
  question?: string
  reference?: string
  context?: string | null
  [key: string]: unknown
}

export interface EditableRow {
  row_no: number
  q: string
  r: string
  c: string
  tags: string
  difficulty: string
  checked: boolean
  extras: Record<string, string>
}

/** 服务端已知字段：其余键在编辑态统一收进 extras。 */
export const KNOWN_ROW_KEYS = new Set([
  'id', 'dataset_id', 'row_no', 'question', 'reference', 'context',
  'q', 'r', 'c', 'tags', 'difficulty', 'source_case_id', 'is_pending',
  'created_at', 'updated_at',
])

/** 服务端行 → 可编辑行；未知字段落 extras，缺省字段给空串。 */
export function toEditableRow(row: ApiRow): EditableRow {
  const extras: Record<string, string> = {}
  Object.keys(row).forEach(key => {
    if (!KNOWN_ROW_KEYS.has(key) && row[key] != null) extras[key] = String(row[key])
  })
  return {
    row_no: row.row_no,
    q: String(row.question ?? row.q ?? ''),
    r: String(row.reference ?? row.r ?? ''),
    c: String(row.context ?? row.c ?? ''),
    tags: String(row.tags ?? ''),
    difficulty: String(row.difficulty ?? '简单'),
    checked: false,
    extras,
  }
}

/** 可编辑行 → 提交结构：同时带 question/reference 别名与扩展列。 */
export function toApiRow(row: EditableRow): ApiRow {
  return {
    row_no: row.row_no,
    question: row.q,
    reference: row.r,
    context: row.c || null,
    q: row.q,
    r: row.r,
    c: row.c,
    tags: row.tags,
    difficulty: row.difficulty,
    ...row.extras,
  }
}

/** 待补全：问句或标准答案为空。 */
export function isRowPending(row: EditableRow): boolean {
  return !row.q.trim() || !row.r.trim()
}

export function countPendingRows(rows: EditableRow[]): number {
  return rows.filter(isRowPending).length
}

/** 追加新行时的下一个行号（不复用空号，避免与已删行冲突）。 */
export function nextRowNo(rows: Pick<EditableRow, 'row_no'>[]): number {
  return Math.max(0, ...rows.map(row => row.row_no)) + 1
}

/** 删除后重排行号（1..n），保持与服务端一致。 */
export function renumberRows<T extends { row_no: number }>(rows: T[]): T[] {
  rows.forEach((row, index) => { row.row_no = index + 1 })
  return rows
}
