/** 调度实时数据装配里的纯逻辑：Worker 归一化、历史序列、事件分类与日志条目。 */

export type LogCategory = 'assign' | 'done' | 'error' | 'node'
export type LogFilter = LogCategory | 'all'

export interface WorkerSource {
  id: string
  name: string
  caps?: string[] | null
  state: string
  load_percent?: number | null
  weight?: number
  current_task?: string | null
}

export interface WorkerNodeView {
  id: string
  name: string
  caps: string[]
  state: string
  load: number
  ram: string
  task: string | null
  weight?: number
}

export interface AuditLogEntry {
  time: string
  kind: string
  cat: LogCategory
  html: string
  tid?: string
}

/** 服务端 Worker → 视图节点：负载取整、缺省能力集与占位内存。 */
export function mapWorkerRow(worker: WorkerSource): WorkerNodeView {
  return {
    id: worker.id,
    name: worker.name,
    caps: worker.caps || [],
    state: worker.state,
    load: Math.round(worker.load_percent ?? 0),
    ram: '—',
    task: worker.current_task || null,
    weight: worker.weight,
  }
}

/** 有界历史序列：追加后超过上限则丢弃最旧值（就地修改，供 ref 数组直接使用）。 */
export function pushBoundedHistory(hist: number[], value: number, max = 24): number[] {
  hist.push(value)
  if (hist.length > max) hist.shift()
  return hist
}

/** 事件类型 → 审计分类（按关键字包含匹配，大小写不敏感）。 */
export function eventCategory(kind: string): LogCategory {
  const upper = kind.toUpperCase()
  if (['ASSIGN', 'ENQUEUE', 'HOLD', 'START'].some(token => upper.includes(token))) return 'assign'
  if (['DONE', 'SUCCEEDED', 'COMPLETE', 'FINISH'].some(token => upper.includes(token))) return 'done'
  if (['FAIL', 'ERROR', 'TIMEOUT', 'CANCEL'].some(token => upper.includes(token))) return 'error'
  return 'node'
}

/** 采集一条审计日志（时间戳固定 8 位，便于列表对齐）。 */
export function buildLogEntry(
  kind: string,
  html: string,
  tid?: string,
  now: Date = new Date(),
): AuditLogEntry {
  return {
    time: now.toTimeString().slice(0, 8),
    kind,
    cat: eventCategory(kind),
    html,
    tid,
  }
}

/** 多页任务合并去重（按 id），按创建时间倒序。 */
export function mergeActiveTasks<T extends { id: string; created_at: string }>(...pages: T[][]): T[] {
  const byId = new Map<string, T>()
  pages.flat().forEach(task => byId.set(task.id, task))
  return [...byId.values()].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
}
