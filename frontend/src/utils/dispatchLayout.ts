/** 星图布局的纯计算：极坐标、扇区路径、文本截断等，与组件状态无关。 */

export interface Point {
  x: number
  y: number
}

/** 极坐标 → 直角坐标（角度单位：度，0° 正右，90° 正下）。 */
export function polarPoint(cx: number, cy: number, angleDeg: number, r: number): Point {
  const a = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
}

/** 业务扇区楔块路径：从内核出发、跨度 ±spread 的扇形。 */
export function wedgePath(
  cx: number,
  cy: number,
  angle: number,
  spread: number,
  r: number,
): string {
  const p1 = polarPoint(cx, cy, angle - spread, r)
  const p2 = polarPoint(cx, cy, angle + spread, r)
  return `M ${cx} ${cy} L ${p1.x.toFixed(1)} ${p1.y.toFixed(1)} A ${r} ${r} 0 0 1 ${p2.x.toFixed(1)} ${p2.y.toFixed(1)} Z`
}

/** Worker 归属业务扇区：取能力标签中首个命中，未命中落通用扇区。 */
export function workerLane<K extends string>(caps: string[], kinds: K[]): K | 'general' {
  const hit = kinds.find(kind => caps.includes(kind))
  return hit ?? 'general'
}

/** 文本截断：星图芯片宽度有限，超长标签用省略号收尾。 */
export function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max - 1) + '…' : text
}
