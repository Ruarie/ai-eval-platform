/** 管理后台：总览聚合与审计查询；资源治理复用能力中心客户端。 */
import http from './http'

export interface AdminOverview {
  users: { total: number; new_7d: number; active_7d: number; disabled: number }
  sessions: { total: number; new_7d: number; shared: number }
  tasks: { total_7d: number; by_status: Record<string, number> }
  resources: {
    total: number
    new_7d: number
    team: number
    private: number
    usage_total: number
    by_kind: Record<string, number>
  }
  storage: { files: number; bytes: number; kb_count: number; kb_docs: number }
  audit_24h: number
  top_actions: Record<string, number>
  recent_audit: OverviewAuditItem[]
  generated_at: string
}

export interface AuditTarget { type: string | null; id: string | null }

/** 概览里的最近审计：服务端已把操作人解析成展示名。 */
export interface OverviewAuditItem {
  id: number
  action: string
  target_type: string | null
  target_id: string | null
  user_name: string
  ip: string | null
  ts: string
}

export interface AuditEntry {
  id: number
  at?: string
  ts?: string
  actor_id?: string | null
  action: string
  target?: AuditTarget
  target_type?: string | null
  target_id?: string | null
  ip?: string | null
  detail?: Record<string, unknown>
}

export interface AuditPage { items: AuditEntry[]; total: number }

export const adminConsole = {
  /** 后台首屏：一次拿全部计数，前端不二次聚合。 */
  async overview(): Promise<AdminOverview> {
    const { data } = await http.get<AdminOverview>('/api/admin/overview')
    return data
  },

  /** 审计查询：from/to 为本地时间的 ISO 串，后端按半开区间过滤。 */
  async audit(params: { from?: string; to?: string; offset?: number; limit?: number }): Promise<AuditPage> {
    const { data } = await http.get<AuditPage>('/api/admin/audit-logs', { params })
    return data
  },
}
