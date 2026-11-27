/**
 * 工作台展示辅助（Datasets 与 Cases 共用）。
 *
 * 收敛前 ``renderIcon`` / ``escapeHtml`` / ``escapeRegex`` 在两个工作台页面
 * 内逐字重复实现；此处为唯一事实源。
 */
import { h } from 'vue'

/**
 * 构造 14×14 的 stroke 风格内联 SVG 图标渲染函数。
 *
 * @param pathD 单条或多条 path 的 d 属性
 * @param strokeColor 描边颜色，缺省继承 currentColor
 */
export function renderIcon(pathD: string | string[], strokeColor?: string) {
  return () =>
    h(
      'svg',
      {
        width: 14,
        height: 14,
        viewBox: '0 0 24 24',
        fill: 'none',
        stroke: strokeColor || 'currentColor',
        strokeWidth: 2,
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        style: { display: 'inline-block', verticalAlign: '-2px', marginRight: '6px' },
      },
      Array.isArray(pathD) ? pathD.map(p => h('path', { d: p })) : [h('path', { d: pathD })],
    )
}

/** 转义 HTML 特殊字符（含单双引号，可安全用于文本与属性值），防止 v-html 注入。 */
export function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/** 转义正则元字符，用于把用户输入安全地拼进 RegExp。 */
export function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * 关键词高亮：在**原文**上切分命中片段，逐段转义后用 <mark> 包裹，输出可交给 v-html。
 * 不能先转义再匹配——否则查询 amp/quot 会把标签插进 &amp; 等实体中间，
 * 而含 & < " 的关键词又永远匹配不到。大小写不敏感。
 */
export function highlightText(text: string, query: string, markClass = 'highlight-match'): string {
  const q = query.trim()
  if (!text) return ''
  if (!q) return escapeHtml(text)
  const regex = new RegExp(escapeRegex(q), 'gi')
  let out = ''
  let last = 0
  for (const match of text.matchAll(regex)) {
    const start = match.index ?? 0
    out += escapeHtml(text.slice(last, start))
    out += `<mark class="${escapeHtml(markClass)}">${escapeHtml(match[0])}</mark>`
    last = start + match[0].length
  }
  return out + escapeHtml(text.slice(last))
}
