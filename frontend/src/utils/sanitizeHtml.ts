/**
 * v-html 输出前的统一消毒入口（代码质量报告 S6）。
 *
 * 各渲染器（Markdown、调度日志等）先自行转义再拼接受控标签；这里作为最后一道
 * 防线，用 DOMPurify 移除脚本、事件属性与危险协议，防止转义遗漏时模型输出或
 * 业务数据注入页面。只放行渲染器实际需要的少量额外属性。
 */
import DOMPurify from 'dompurify'

/** 渲染器依赖、而 DOMPurify 默认不放行的属性。 */
const EXTRA_ATTRS = ['target']

let hookInstalled = false

/** 新窗口打开的链接一律补齐 noopener/noreferrer，防止反向篡改 opener。 */
function installLinkHook(): void {
  if (hookInstalled) return
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node instanceof Element && node.tagName === 'A' && node.getAttribute('target')) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
  hookInstalled = true
}

/** 消毒一段将交给 v-html 渲染的 HTML；非浏览器环境（无 DOM）直接返回空串。 */
export function sanitizeHtml(html: string): string {
  if (!html) return ''
  if (!DOMPurify.isSupported) return ''
  installLinkHook()
  return DOMPurify.sanitize(html, {
    ADD_ATTR: EXTRA_ATTRS,
    // 禁止 <form>/<style> 等可改写页面结构或样式的标签。
    FORBID_TAGS: ['style', 'form', 'input', 'textarea', 'select', 'iframe', 'object', 'embed'],
    // 不自定义 ALLOWED_URI_REGEXP：它会作用于所有非 URI 白名单属性的取值（会误删
    // target="_blank"、SVG width 等）；DOMPurify 默认规则已拦截 javascript: 及链接上的 data:。
  })
}
