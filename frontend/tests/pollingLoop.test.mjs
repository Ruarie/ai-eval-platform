import test from 'node:test'
import assert from 'node:assert/strict'
import { usePollingLoop } from '../src/composables/usePollingLoop.ts'

function fakeEnv() {
  let handler = null
  let hidden = false
  return {
    env: {
      setInterval: (fn) => { handler = fn; return 1 },
      clearInterval: () => { handler = null },
      isHidden: () => hidden,
    },
    fire: () => handler && handler(),
    setHidden: (v) => { hidden = v },
    hasTimer: () => handler !== null,
  }
}

test('start 只注册一次，stop 清理', () => {
  const f = fakeEnv()
  const loop = usePollingLoop({ intervalMs: 1000, run: () => {}, env: f.env })
  loop.start(); loop.start()
  assert.equal(loop.isRunning(), true)
  loop.stop()
  assert.equal(f.hasTimer(), false)
})

test('同一时刻只允许一个在飞请求', async () => {
  const f = fakeEnv()
  let calls = 0
  let release
  const gate = new Promise(r => { release = r })
  const loop = usePollingLoop({
    intervalMs: 1000,
    run: async () => { calls += 1; await gate },
    env: f.env,
  })
  const first = loop.tick()
  const second = loop.tick()      // 在飞期间应被跳过
  release()
  await Promise.all([first, second])
  assert.equal(calls, 1)
})

test('后台标签页暂停轮询', async () => {
  const f = fakeEnv()
  let calls = 0
  const loop = usePollingLoop({ intervalMs: 1000, run: () => { calls += 1 }, env: f.env })
  f.setHidden(true)
  await loop.tick()
  assert.equal(calls, 0)
  f.setHidden(false)
  await loop.tick()
  assert.equal(calls, 1)
})

test('可关闭后台暂停', async () => {
  const f = fakeEnv()
  let calls = 0
  const loop = usePollingLoop({
    intervalMs: 1000, run: () => { calls += 1 }, pauseWhenHidden: false, env: f.env,
  })
  f.setHidden(true)
  await loop.tick()
  assert.equal(calls, 1)
})

test('enabled 返回 false 时跳过本轮', async () => {
  const f = fakeEnv()
  let calls = 0
  let on = false
  const loop = usePollingLoop({
    intervalMs: 1000, run: () => { calls += 1 }, enabled: () => on, env: f.env,
  })
  await loop.tick()
  assert.equal(calls, 0)
  on = true
  await loop.tick()
  assert.equal(calls, 1)
})
