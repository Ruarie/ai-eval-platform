/** 调度星图布局：由技能/Worker/任务快照计算出全部坐标与链路，纯函数。 */
import { polarPoint, wedgePath, workerLane } from './dispatchLayout.ts'

export interface TopoSkillDef {
  kind: string
  angle: number
  color: string
}

export interface TopoWorker {
  id: string
  caps: string[]
}

export interface TopoTask {
  id: string
  kind: string
  status: string
  workerId?: string | null
}

export interface TopoGeometry {
  cx: number
  cy: number
  rSkill: number
  rWorker: number
  rQueue: number
}

export interface TopoCounters {
  queue: number
  running: number
  awaiting: number
}

export interface TopoOptions<
  S extends TopoSkillDef = TopoSkillDef,
  W extends TopoWorker = TopoWorker,
  T extends TopoTask = TopoTask,
> {
  skills: S[]
  workers: W[]
  tasks: T[]
  liveMode: boolean
  maxQueueChips: number
  geometry: TopoGeometry
}

export interface Topo<
  S extends TopoSkillDef = TopoSkillDef,
  W extends TopoWorker = TopoWorker,
  T extends TopoTask = TopoTask,
> {
  skills: (S & { x: number; y: number; activeCount: number; runningCount: number })[]
  sectors: { kind: string; angle: number; spread: number; color: string; wedge: string }[]
  workers: { w: W; x: number; y: number; sx: number; sy: number; skillKind: string }[]
  tasks: { t: T; x: number; y: number }[]
  liveWires: { key: string; skillKind: string; d: string }[]
  queueOverflow: number
  runningOverflow: number
  awaitingOverflow: number
}

/**
 * 星图布局：技能固定角度、Worker 按扇区均布（单环 5 个后外扩）、
 * 排队芯片在内环均布、运行芯片飞到链路 55% 处并按堆叠横向错开。
 */
export function buildTopo<
  S extends TopoSkillDef,
  W extends TopoWorker,
  T extends TopoTask,
>(options: TopoOptions<S, W, T>, counters: TopoCounters): Topo<S, W, T> {
  const { skills: skillDefs, workers: workerPool, tasks: taskNodes, liveMode, maxQueueChips, geometry } = options
  const { cx, cy, rSkill, rWorker, rQueue } = geometry
  const polar = (angleDeg: number, r: number) => polarPoint(cx, cy, angleDeg, r)
  const kinds = skillDefs.map(def => def.kind)

  // 1) 技能节点：固定角度布点 + 活跃统计
  const skills = skillDefs.map(def => {
    const point = polar(def.angle, rSkill)
    const hit = taskNodes.filter(task => task.kind === def.kind)
    return {
      ...def,
      ...point,
      activeCount: hit.length,
      runningCount: hit.filter(task => task.status === 'running').length,
    }
  })
  const skillByKind = new Map(skills.map(skill => [skill.kind as string, skill]))

  // 2) 扇区：四业务域 + 存在未匹配 Worker 时的通用扇区（压缩跨度避免重叠）
  const hasGeneral = workerPool.some(worker => workerLane(worker.caps, kinds) === 'general')
  const spread = hasGeneral ? 26 : 34
  const sectorDefs = skillDefs.map(def => ({
    kind: def.kind,
    angle: def.angle,
    spread,
    color: def.color,
  }))
  if (hasGeneral) {
    sectorDefs.push({ kind: 'general', angle: 135, spread: 14, color: 'var(--text-tertiary)' })
  }
  const sectors = sectorDefs.map(sector => ({
    ...sector,
    wedge: wedgePath(cx, cy, sector.angle, sector.spread + 8, rWorker + 46),
  }))

  // 3) Worker：扇区内均布，超过 5 个外扩第二环
  const workers: Topo<S, W, T>['workers'] = []
  sectorDefs.forEach(sector => {
    const list = workerPool.filter(worker => workerLane(worker.caps, kinds) === sector.kind)
    const skill = skillByKind.get(sector.kind)
    list.forEach((worker, index) => {
      const ring = Math.floor(index / 5)
      const indexInRing = index % 5
      const inRing = Math.min(5, list.length - ring * 5)
      const offset =
        inRing === 1 ? 0 : -sector.spread + (2 * sector.spread * indexInRing) / (inRing - 1)
      const point = polar(sector.angle + offset, rWorker + ring * 58)
      workers.push({
        w: worker,
        x: point.x,
        y: point.y,
        sx: skill?.x ?? cx,
        sy: skill?.y ?? cy,
        skillKind: sector.kind,
      })
    })
  })
  const workerById = new Map(workers.map(item => [item.w.id, item]))

  // 4) 工单芯片：排队在内环均布，运行飞到链路中段并按同节点堆叠横向错开
  const queued = taskNodes.filter(task => task.status !== 'running')
  const running = taskNodes.filter(task => task.status === 'running')
  const runStack = new Map<string, number>()
  const chips: Topo<S, W, T>['tasks'] = []
  const visibleAwaiting = liveMode
    ? queued.filter(task => task.status === 'awaiting_case_confirm').slice(0, 2)
    : []
  const visibleQueued = liveMode
    ? [
        ...queued
          .filter(task => task.status === 'queued')
          .slice(0, maxQueueChips - visibleAwaiting.length),
        ...visibleAwaiting,
      ]
    : queued.slice(0, maxQueueChips)

  visibleQueued.forEach((task, index) => {
    const point = polar(105 + index * 30, rQueue)
    chips.push({ t: task, x: point.x, y: point.y })
  })
  running.forEach(task => {
    const skill = skillByKind.get(task.kind)
    const placed = task.workerId ? workerById.get(task.workerId) : undefined
    if (skill && placed) {
      const midX = skill.x + (placed.x - skill.x) * 0.55
      const midY = skill.y + (placed.y - skill.y) * 0.55
      const dx = placed.x - skill.x
      const dy = placed.y - skill.y
      const len = Math.max(Math.hypot(dx, dy), 1)
      const stack = runStack.get(placed.w.id) || 0
      runStack.set(placed.w.id, stack + 1)
      chips.push({ t: task, x: midX + (-dy / len) * 30 * stack, y: midY + (dx / len) * 30 * stack })
    } else if (skill) {
      const index = running.indexOf(task)
      const point = polar(skill.angle + 24 + index * 14, rSkill - 58)
      chips.push({ t: task, x: point.x, y: point.y })
    }
  })

  // 5) 执行链路：内核 → 技能 → Worker
  const liveWires = running
    .filter(task => task.workerId && workerById.has(task.workerId) && skillByKind.has(task.kind))
    .map(task => {
      const skill = skillByKind.get(task.kind)!
      const placed = workerById.get(task.workerId!)!
      return {
        key: `live-${task.id}`,
        skillKind: task.kind,
        d: `M ${cx} ${cy} L ${skill.x} ${skill.y} L ${placed.x} ${placed.y}`,
      }
    })

  const visibleByStatus = (status: string) =>
    chips.filter(item => item.t.status === status).length
  return {
    skills,
    sectors,
    workers,
    tasks: chips,
    liveWires,
    queueOverflow: Math.max(
      0,
      (liveMode ? counters.queue : queued.length) - visibleByStatus('queued'),
    ),
    runningOverflow: liveMode ? Math.max(0, counters.running - visibleByStatus('running')) : 0,
    awaitingOverflow: liveMode
      ? Math.max(0, counters.awaiting - visibleByStatus('awaiting_case_confirm'))
      : 0,
  }
}
