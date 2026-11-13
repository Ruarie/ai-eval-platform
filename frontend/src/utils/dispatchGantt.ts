/** 甘特抽屉的纯计算：把任务快照换算成百分比条与时间刻度。 */

export interface GanttBaseRow {
  id: string
  start: number
  end: number
  parentId?: string | null
  isChild?: boolean
  [key: string]: unknown
}

export interface PositionedRow extends GanttBaseRow {
  left: number
  width: number
}

/** 最短可视宽度（%）：避免 1 秒任务在长跨度里看不见。 */
const MIN_BAR_WIDTH_PERCENT = 1.5
/** 计算跨度时的下限（1 分钟），防止单任务时被拉伸到整屏。 */
const MIN_SPAN_MS = 60_000

/** 计算百分比条，并把派生子任务紧跟在父任务之后（父按开始时间排序）。 */
export function buildGanttRows(rows: GanttBaseRow[], now: number): PositionedRow[] {
  if (!rows.length) return []
  const minStart = Math.min(...rows.map(r => r.start))
  const maxEnd = Math.max(now, ...rows.map(r => r.end))
  const span = Math.max(maxEnd - minStart, MIN_SPAN_MS)
  const positioned: PositionedRow[] = rows.map(r => ({
    ...r,
    left: Math.max(0, ((r.start - minStart) / span) * 100),
    width: Math.max(
      MIN_BAR_WIDTH_PERCENT,
      ((Math.max(r.end, r.start + 800) - r.start) / span) * 100,
    ),
  }))
  const ids = new Set(positioned.map(r => r.id))
  const parents = positioned.filter(r => !r.isChild || !ids.has(r.parentId || ''))
  const children = positioned.filter(r => r.isChild && ids.has(r.parentId || ''))
  const ordered: PositionedRow[] = []
  parents.sort((a, b) => a.start - b.start).forEach(parent => {
    ordered.push(parent)
    children.filter(child => child.parentId === parent.id).forEach(child => ordered.push(child))
  })
  return ordered
}

/** 四个时间刻度文案：0 / 1/3 / 2/3 / 1 处的实际时间。 */
export function buildGanttTicks(rows: GanttBaseRow[], now: number, format: (ts: number) => string): string[] {
  if (!rows.length) return []
  const minStart = Math.min(...rows.map(r => r.start))
  const maxEnd = Math.max(now, ...rows.map(r => r.end))
  return [0, 1 / 3, 2 / 3, 1].map(ratio => format(minStart + (maxEnd - minStart) * ratio))
}
