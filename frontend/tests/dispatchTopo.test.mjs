import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTopo } from '../src/utils/dispatchTopo.ts'

const geometry = { cx: 400, cy: 300, rSkill: 120, rWorker: 220, rQueue: 64 }
const skills = [
  { kind: 'testcase', angle: 180, color: '#111' },
  { kind: 'stress', angle: 90, color: '#222' },
]
const counters = { queue: 0, running: 0, awaiting: 0 }

test('技能节点落在半径上并统计活跃数', () => {
  const topo = buildTopo(
    {
      skills,
      workers: [],
      tasks: [
        { id: 't1', kind: 'testcase', status: 'queued' },
        { id: 't2', kind: 'testcase', status: 'running', workerId: 'w1' },
      ],
      liveMode: false,
      maxQueueChips: 6,
      geometry,
    },
    counters,
  )
  const skill = topo.skills.find(s => s.kind === 'testcase')
  assert.ok(Math.abs(skill.x - (geometry.cx - geometry.rSkill)) < 1e-6)
  assert.ok(Math.abs(skill.y - geometry.cy) < 1e-6)
  assert.equal(skill.activeCount, 2)
  assert.equal(skill.runningCount, 1)
})

test('存在未匹配能力时新增 general 扇区并压缩跨度', () => {
  const topo = buildTopo(
    {
      skills,
      workers: [{ id: 'w9', caps: ['unknown'] }],
      tasks: [],
      liveMode: false,
      maxQueueChips: 6,
      geometry,
    },
    counters,
  )
  const general = topo.sectors.find(s => s.kind === 'general')
  assert.ok(general, '应生成 general 扇区')
  assert.equal(general.spread, 14)
  assert.equal(topo.sectors.find(s => s.kind === 'testcase').spread, 26)
  assert.equal(topo.workers[0].skillKind, 'general')
})

test('没有未匹配 Worker 时不生成 general，跨度放宽', () => {
  const topo = buildTopo(
    {
      skills,
      workers: [{ id: 'w1', caps: ['testcase'] }],
      tasks: [],
      liveMode: false,
      maxQueueChips: 6,
      geometry,
    },
    counters,
  )
  assert.equal(topo.sectors.some(s => s.kind === 'general'), false)
  assert.equal(topo.sectors[0].spread, 34)
})

test('运行中芯片落在技能→Worker 链路 55% 处', () => {
  const topo = buildTopo(
    {
      skills,
      workers: [{ id: 'w1', caps: ['testcase'] }],
      tasks: [{ id: 't1', kind: 'testcase', status: 'running', workerId: 'w1' }],
      liveMode: false,
      maxQueueChips: 6,
      geometry,
    },
    counters,
  )
  const skill = topo.skills.find(s => s.kind === 'testcase')
  const worker = topo.workers[0]
  const chip = topo.tasks[0]
  const expectedX = skill.x + (worker.x - skill.x) * 0.55
  const expectedY = skill.y + (worker.y - skill.y) * 0.55
  assert.ok(Math.abs(chip.x - expectedX) < 1e-6)
  assert.ok(Math.abs(chip.y - expectedY) < 1e-6)
  assert.equal(topo.liveWires.length, 1)
  assert.ok(topo.liveWires[0].d.startsWith(`M ${geometry.cx} ${geometry.cy} L `))
})

test('排队芯片受上限约束并给出溢出数', () => {
  const tasks = Array.from({ length: 9 }, (_, i) => ({ id: `q${i}`, kind: 'testcase', status: 'queued' }))
  const topo = buildTopo(
    {
      skills,
      workers: [],
      tasks,
      liveMode: true,
      maxQueueChips: 4,
      geometry,
    },
    { queue: 9, running: 0, awaiting: 0 },
  )
  assert.equal(topo.tasks.length, 4)
  assert.equal(topo.queueOverflow, 5)
})
