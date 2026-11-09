/**
 * 用例工作台的纯函数与类型。
 *
 * 从 Cases.vue 抽出的第一步：只放无 Vue 依赖的映射/格式化逻辑，
 * 便于单测与后续把表格、生成向导拆成组件时复用。
 */

import type { TestCase, TestCaseInput } from '../api/types'

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function escapeRegex(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export type CaseStrategy = '正向' | '反向' | '边界' | '状态迁移' | '场景' | '等价类'
export type CasePriority = 'HX' | 'FHX' | 'BJ' | 'YC' | 'ZD' | 'BL'

/** 页面编辑字段与服务端原始行并存，保存时保留未直接展示的固定字段。 */
export interface ExtendedTestCase {
  id: string
  set_id?: string
  code: string
  name: string
  module: string
  feature_point: string
  strategy: CaseStrategy
  priority: CasePriority
  preconditions: string
  expected_result: string
  steps?: string[]
  target_dataset_id?: string
  checked?: boolean
  extras?: Record<string, unknown>
  source?: TestCase
}

export const CASE_STRATEGIES: CaseStrategy[] = ['正向', '反向', '边界', '等价类', '状态迁移', '场景']
export const CASE_PRIORITIES: CasePriority[] = ['HX', 'FHX', 'BJ', 'YC', 'ZD', 'BL']

const FIXED_CASE_KEYS = new Set([
  'id',
  'code',
  'name',
  'module',
  'strategy',
  'priority',
  'precondition',
  'steps',
  'expected',
  'submodule',
  'feature_point',
  'test_type',
  'mapped',
  'pending_complete',
])

export function normalizeCaseStrategy(strategy: TestCase['strategy']): CaseStrategy {
  if (strategy === '等价') return '等价类'
  if (strategy === '状态') return '状态迁移'
  return strategy || '正向'
}

/** 服务端将扩展字段平铺；固定字段之外的值进入页面扩展列，不丢弃未知数据。 */
export function editableCase(c: TestCase, setId: string, index: number): ExtendedTestCase {
  return {
    id: c.id || `temp-${Date.now()}-${index}`,
    set_id: setId,
    code: c.code || `TC-${String(index + 1).padStart(3, '0')}`,
    name: c.name || '',
    module: c.module || '通用',
    feature_point: c.feature_point || '',
    strategy: normalizeCaseStrategy(c.strategy),
    priority: c.priority || 'HX',
    preconditions: c.precondition || '',
    expected_result: c.expected || '',
    steps: typeof c.steps === 'string' ? c.steps.split('\n') : [],
    target_dataset_id: typeof c.target_dataset_id === 'string' ? c.target_dataset_id : undefined,
    extras: Object.fromEntries(Object.entries(c).filter(([key]) => !FIXED_CASE_KEYS.has(key))),
    source: { ...c },
  }
}

/** 固定字段使用契约名称；扩展键与未展示的固定字段完整保留。 */
export function casePayload(c: ExtendedTestCase): TestCaseInput {
  return {
    ...c.source,
    ...c.extras,
    id: c.id.startsWith('temp-') ? undefined : c.id,
    code: c.code,
    name: c.name,
    module: c.module,
    feature_point: c.feature_point,
    strategy: c.strategy,
    priority: c.priority,
    precondition: c.preconditions,
    steps: c.steps?.join('\n') || '',
    expected: c.expected_result,
    ...(c.target_dataset_id ? { target_dataset_id: c.target_dataset_id } : {}),
  }
}

export function getCaseExtra(c: ExtendedTestCase, key: string): string {
  return String(c.extras?.[key] ?? '')
}

/** 新建空用例行；编号按当前集合行数递增，ID 带时间戳避免并发重复。 */
export function createEmptyCase(setId: string, nextNumber: number): ExtendedTestCase {
  return {
    id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    set_id: setId,
    code: `TC-${String(nextNumber).padStart(3, '0')}`,
    name: '',
    module: '通用',
    feature_point: '',
    strategy: '正向',
    priority: 'HX',
    preconditions: '',
    steps: ['1. 执行标准输入'],
    expected_result: '',
    target_dataset_id: undefined,
    extras: {},
  }
}

/** 只输出经过转义的纯文本 + mark 标签，调用方仍需只用于 v-html。 */
export function highlightText(text: string, query: string): string {
  const q = query.trim()
  if (!q || !text) return escapeHtml(text)
  const regex = new RegExp(`(${escapeRegex(q)})`, 'gi')
  return escapeHtml(text).replace(regex, '<mark class="highlight-match">$1</mark>')
}

export function caseSetStatusLabel(status: 'generated' | 'confirmed' | 'cancelled'): string {
  return status === 'confirmed' ? '已入库' : status === 'cancelled' ? '已废弃' : '草稿'
}
