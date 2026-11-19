/**
 * 把后端 `400 VALIDATION` 的 `fields` 翻译成一句人话。
 *
 * 背景：请求体校验失败时后端只给 `请检查标红字段`，前端若直接弹 message，
 * 用户既看不到哪个字段错、也不知道错在哪（曾导致「开通新成员」整条链路不可用）。
 * 现在错误体已带 `{字段名: 原始校验信息}`（API §1.3），这里统一做两层翻译：
 * 字段名 → 中文标签，pydantic 原始英文 → 中文原因。
 */

const FIELD_LABELS: Record<string, string> = {
  name: '名称',
  title: '标题',
  username: '用户名',
  password: '密码',
  display_name: '显示名',
  email: '邮箱',
  summary: '描述',
  content: '内容',
  kind: '类型',
  visibility: '可见性',
  kb_id: '知识库',
  mode: '检索模式',
  k: 'Top-K',
  dataset_id: '数据集',
  base_url: '接口地址',
  model: '模型',
  api_key: 'API Key',
  old_password: '原密码',
  new_password: '新密码',
  workspace_id: '工作区',
  session_id: '会话',
  role: '角色',
  disabled: '停用状态',
}

/** pydantic 常见校验信息的固定翻译；未命中则原样返回英文信息。 */
const MESSAGE_RULES: Array<[RegExp, (match: RegExpMatchArray) => string]> = [
  [/^Field required$/i, () => '必填'],
  [/^String should have at most (\d+) characters$/i, (m) => `最多 ${m[1]} 个字符`],
  [/^String should have at least (\d+) characters$/i, (m) => `至少 ${m[1]} 个字符`],
  [/^String should contain at most (\d+) characters$/i, (m) => `最多 ${m[1]} 个字符`],
  [/^Input should be a valid integer/i, () => '需要是整数'],
  [/^Input should be a valid number/i, () => '需要是数字'],
  [/^Input should be a valid string/i, () => '需要是文本'],
  [/^Input should be a valid boolean/i, () => '需要是布尔值'],
  [/^Extra inputs are not permitted$/i, () => '不支持的字段'],
  [/^Input should be (.+)$/i, (m) => `只能是 ${m[1]}`],
]

const humanMessage = (raw: string): string => {
  const text = String(raw || '').trim()
  if (!text) return ''
  for (const [pattern, render] of MESSAGE_RULES) {
    const match = text.match(pattern)
    if (match) return render(match)
  }
  return text
}

const labelOf = (key: string): string => FIELD_LABELS[key] || key

/**
 * 组合成「名称最多 100 个字符；用户名必填」这种形式，最多取 `limit` 个字段，
 * 避免一次错误弹出一长串。
 */
export function describeFieldErrors(fields?: Record<string, string> | null, limit = 2): string {
  if (!fields || typeof fields !== 'object') return ''
  const entries = Object.entries(fields).filter(([, value]) => String(value || '').trim())
  if (!entries.length) return ''
  const parts = entries.slice(0, Math.max(1, limit)).map(([key, value]) => {
    const message = humanMessage(value)
    const label = labelOf(key)
    // 「必填」「不支持的字段」这类短结论直接跟在字段名后面，读起来更顺。
    if (/^(必填|不支持的字段)$/.test(message)) return `${label}${message}`
    return `${label}：${message}`
  })
  const rest = entries.length - parts.length
  return rest > 0 ? `${parts.join('；')}（另有 ${rest} 项）` : parts.join('；')
}

/** 后端只给了通用文案时，用它判断是否值得替换成字段级描述。 */
export const GENERIC_VALIDATION_MESSAGE = '请检查标红字段'
