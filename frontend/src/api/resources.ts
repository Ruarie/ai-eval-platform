/** 能力中心：Agent / Skill / Script / Rule 四类资源的统一客户端。 */
import http from './http'

export type ResourceKind = 'agent' | 'skill' | 'script' | 'rule' | 'rag'
export type ResourceVisibility = 'private' | 'team'

/** 列表与详情共用的资源投影；editable 由服务端判定，前端不重复算权限。 */
export interface ResourceItem {
  id: string
  kind: ResourceKind
  name: string
  summary: string
  content: Record<string, unknown>
  owner_id: string | null
  owner_name: string
  visibility: ResourceVisibility
  usage_count: number
  source_id: string | null
  editable: boolean
  created_at: string
  updated_at: string
}

export interface ResourcePage { items: ResourceItem[]; total: number }

export interface ResourceInput {
  kind: ResourceKind
  name: string
  summary: string
  content: Record<string, unknown>
  visibility: ResourceVisibility
}

/** 广场榜单条目：weekly_uses 只统计近 7 日事件，避免用累计值冒充热度。 */
export interface PlazaRankItem {
  id: string
  kind: ResourceKind
  name: string
  summary: string
  owner_name: string
  usage_count: number
  weekly_uses: number
  created_at: string
}

export interface Plaza {
  total: number
  featured: PlazaRankItem[]
  popular: PlazaRankItem[]
  rising: PlazaRankItem[]
  newest: PlazaRankItem[]
}

export const resources = {
  /** 按类型与范围取列表；scope=mine 只看自己创建的。 */
  async list(params: {
    kind?: ResourceKind | ''
    scope?: 'all' | 'mine'
    visibility?: ResourceVisibility | ''
    q?: string
    sort?: 'recent' | 'popular'
    offset?: number
    limit?: number
  }): Promise<ResourcePage> {
    const { data } = await http.get<ResourcePage>('/api/resources', { params })
    return data
  },

  async create(input: ResourceInput): Promise<ResourceItem> {
    const { data } = await http.post<ResourceItem>('/api/resources', input)
    return data
  },

  /** 只提交变更字段，未提交的字段由服务端保持原值。 */
  async update(id: string, input: Partial<Omit<ResourceInput, 'kind'>>): Promise<ResourceItem> {
    const { data } = await http.patch<ResourceItem>(`/api/resources/${encodeURIComponent(id)}`, input)
    return data
  },

  async remove(id: string): Promise<void> {
    await http.delete(`/api/resources/${encodeURIComponent(id)}`)
  },

  /** 使用一次：计数 +1 并落事件，返回最新内容用于复制。 */
  async use(id: string): Promise<{ id: string; usage_count: number; content: Record<string, unknown> }> {
    const { data } = await http.post(`/api/resources/${encodeURIComponent(id)}/use`)
    return data
  },

  /** 基于此创建：副本归当前用户且默认私有。 */
  async clone(id: string, name?: string): Promise<ResourceItem> {
    const { data } = await http.post<ResourceItem>(
      `/api/resources/${encodeURIComponent(id)}/clone`,
      name ? { name } : {},
    )
    return data
  },

  async plaza(): Promise<Plaza> {
    const { data } = await http.get<Plaza>('/api/resources/plaza')
    return data
  },
}
