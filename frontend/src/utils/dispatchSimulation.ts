/** 调度仿真模式的纯计算：负载增减、进度推进、模板选取。 */

export interface QueueTemplate {
  kind: string
  label: string
  prio: string
  parentId?: string | null
}

export interface MockQueueItem {
  qid: string
  kind: string
  label: string
  prio: string
  parentId: string | null
}

/** 分配任务时的节点负载：加 24~46，封顶 96。 */
export function applyAssignLoad(load: number, rnd: number): number {
  return Math.min(96, load + 24 + Math.round(rnd * 22))
}

/** 任务完成时的节点负载：减 32~52，保底 4。 */
export function applyReleaseLoad(load: number, rnd: number): number {
  return Math.max(4, load - 32 - Math.round(rnd * 20))
}

/** 低于该负载视为空闲，可回收节点占用。 */
export const IDLE_LOAD_THRESHOLD = 30

export function isIdleLoad(load: number): boolean {
  return load < IDLE_LOAD_THRESHOLD
}

/** 运行中进度：按已耗时/总时长换算，最多 99%（完成由结束事件收口）。 */
export function computeProgress(startedAt: number, now: number, durationMs: number): number {
  if (!startedAt || durationMs <= 0) return 0
  const ratio = (now - startedAt) / durationMs
  return Math.max(0, Math.min(99, ratio * 100))
}

/** 随机取一条排队模板。 */
export function pickTemplate<T>(templates: T[], rnd: number): T {
  const index = Math.min(templates.length - 1, Math.floor(rnd * templates.length))
  return templates[index]
}

/** 构造一条排队工单（qid 由自增序号生成）。 */
export function createMockTask(sequence: number, template: QueueTemplate): MockQueueItem {
  return {
    qid: `q-${sequence}`,
    kind: template.kind,
    label: template.label,
    prio: template.prio,
    parentId: template.parentId ?? null,
  }
}
