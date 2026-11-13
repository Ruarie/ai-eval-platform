/**
 * 可见性感知的轮询循环：页面只提供「取数」回调，调度语义（间隔、重复进入保护、
 * 后台暂停、卸载清理）统一在这里，避免每个定时器各写一遍。
 */
export interface PollingEnv {
  setInterval: (handler: () => void, ms: number) => number
  clearInterval: (id: number) => void
  isHidden: () => boolean
}

export interface PollingOptions {
  /** 轮询间隔（毫秒）。 */
  intervalMs: number
  /** 单次轮询：返回 Promise 时同一时刻只会有一个在飞。 */
  run: () => void | Promise<void>
  /** 后台标签页是否暂停（默认 true）。 */
  pauseWhenHidden?: boolean
  /** 额外开关：返回 false 时跳过本轮（如「未运行时不做仿真负载抖动」）。 */
  enabled?: () => boolean
  env?: Partial<PollingEnv>
}

const defaultEnv: PollingEnv = {
  setInterval: (handler, ms) => window.setInterval(handler, ms),
  clearInterval: id => window.clearInterval(id),
  isHidden: () => document.hidden,
}

export function usePollingLoop(options: PollingOptions) {
  const env: PollingEnv = { ...defaultEnv, ...(options.env || {}) }
  const pauseWhenHidden = options.pauseWhenHidden !== false
  let timer: number | null = null
  let inFlight = false

  async function tick() {
    if (inFlight) return          // 上一轮还没回来就跳过，避免请求堆积
    if (pauseWhenHidden && env.isHidden()) return
    if (options.enabled && !options.enabled()) return
    inFlight = true
    try {
      await options.run()
    } finally {
      inFlight = false
    }
  }

  function start() {
    if (timer !== null) return
    timer = env.setInterval(() => void tick(), options.intervalMs)
  }

  function stop() {
    if (timer === null) return
    env.clearInterval(timer)
    timer = null
  }

  return { start, stop, tick, isRunning: () => timer !== null }
}
