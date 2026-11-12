/** 迷你趋势线：把历史序列映射为 76×24 视窗内的 polyline 坐标点。 */
export function sparkPoints(hist: number[]): string {
  if (hist.length < 2) return ''
  const max = Math.max(...hist, 1)
  const min = Math.min(...hist, 0)
  const span = Math.max(max - min, 1)
  return hist
    .map(
      (value, index) =>
        `${((index / (hist.length - 1)) * 74 + 1).toFixed(1)},${(
          22 -
          ((value - min) / span) * 20
        ).toFixed(1)}`,
    )
    .join(' ')
}
