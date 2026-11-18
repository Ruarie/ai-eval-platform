<template>
  <div class="rc-page">
    <header class="rc-head">
      <div>
        <div class="eyebrow">能力中心</div>
        <h1>{{ cfg.title }}</h1>
        <p>{{ cfg.sub }}</p>
      </div>
      <div class="rc-head-actions">
        <n-button :disabled="loading" @click="reload">刷新</n-button>
        <n-button type="primary" @click="openEditor()">新建{{ cfg.noun }}</n-button>
      </div>
    </header>

    <section class="rc-toolbar" aria-label="筛选">
      <n-input
        v-model:value="query"
        clearable
        placeholder="搜索名称或描述"
        aria-label="搜索资源"
        :maxlength="80"
        @keyup.enter="reload"
      />
      <n-select v-model:value="scope" :options="scopeOptions" aria-label="范围" style="width: 140px" />
      <n-select v-model:value="sort" :options="sortOptions" aria-label="排序" style="width: 150px" />
      <n-button :disabled="loading" @click="reload">搜索</n-button>
    </section>

    <p class="rc-caption">
      共 {{ total }} 个{{ cfg.noun }}
      <span>团队共享的资源全员可用；私有资源只有你和管理员可见。不会保存任何密钥。</span>
    </p>

    <n-spin :show="loading">
      <div v-if="error" class="rc-error">
        <n-alert type="error" :show-icon="false">{{ error }}</n-alert>
        <n-button size="small" @click="reload">重试</n-button>
      </div>

      <div v-else-if="!items.length" class="rc-empty">
        <n-empty :description="emptyText" />
        <n-button size="small" type="primary" @click="openEditor()">新建{{ cfg.noun }}</n-button>
      </div>

      <div v-else class="rc-grid">
        <article
          v-for="item in items"
          :key="item.id"
          class="rc-card"
          :style="{ '--t': cfg.t, '--c': cfg.c }"
        >
          <div class="rc-card-top">
            <span class="rc-kind">{{ cfg.noun }}</span>
            <span class="rc-vis" :class="item.visibility">{{ item.visibility === 'team' ? '团队' : '私有' }}</span>
            <button class="rc-name" :title="item.name" @click="openDetail(item)">{{ item.name }}</button>
          </div>
          <p class="rc-summary">{{ item.summary || '（暂无描述）' }}</p>
          <div class="rc-meta">
            <span>{{ item.owner_name || '未知作者' }}</span>
            <span>·</span>
            <span>使用 {{ item.usage_count }}</span>
            <span>·</span>
            <span>{{ shortTime(item.updated_at) }}</span>
          </div>
          <div class="rc-actions">
            <n-button size="tiny" @click="useItem(item)">使用</n-button>
            <n-button size="tiny" @click="cloneItem(item)">基于此创建</n-button>
            <n-button size="tiny" quaternary @click="openDetail(item)">详情</n-button>
            <n-button v-if="item.editable" size="tiny" quaternary @click="openEditor(item)">编辑</n-button>
            <n-button v-if="item.editable" size="tiny" quaternary type="error" @click="askDelete(item)">删除</n-button>
          </div>
        </article>
      </div>
    </n-spin>

    <!-- 新建 / 编辑 -->
    <n-modal
      v-model:show="editor.show"
      preset="card"
      :title="editor.id ? `编辑${cfg.noun}` : `新建${cfg.noun}`"
      style="width: 640px; max-width: calc(100vw - 32px)"
      :mask-closable="!saving"
    >
      <div class="rc-form">
        <label class="rc-label">名称 <span class="req">*</span></label>
        <n-input v-model:value="editor.name" placeholder="例如：日志分析助手" :maxlength="80" show-count />

        <label class="rc-label">简介</label>
        <n-input
          v-model:value="editor.summary"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 3 }"
          placeholder="一句话说明它解决什么问题（会显示在卡片和广场）"
          :maxlength="400"
          show-count
        />

        <template v-if="kind === 'agent'">
          <label class="rc-label">系统提示词 <span class="req">*</span></label>
          <n-input
            v-model:value="editor.prompt"
            type="textarea"
            :autosize="{ minRows: 6, maxRows: 14 }"
            placeholder="描述角色、边界与输出格式，例如：你是日志分析助手，先聚合错误再给结论……"
          />
          <label class="rc-label">可用工具</label>
          <n-checkbox-group v-model:value="editor.tools">
            <div class="rc-tools">
              <n-checkbox v-for="tool in TOOLS" :key="tool.value" :value="tool.value" :label="tool.label" />
            </div>
          </n-checkbox-group>
        </template>

        <template v-else-if="kind === 'script'">
          <label class="rc-label">语言</label>
          <n-select v-model:value="editor.language" :options="LANGUAGES" style="width: 200px" />
          <label class="rc-label">脚本内容 <span class="req">*</span></label>
          <n-input
            v-model:value="editor.code"
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 22 }"
            placeholder="粘贴可复用脚本；不要写入密钥，运行时请从环境变量读取"
            class="rc-code"
          />
        </template>

        <template v-else-if="kind === 'rag'">
          <label class="rc-label">绑定知识库 <span class="req">*</span></label>
          <n-select
            v-model:value="editor.kbId"
            :options="kbOptions"
            filterable
            placeholder="选择要复用的知识库"
            :status="kbOptions.length ? undefined : 'warning'"
          />
          <p v-if="!kbOptions.length" class="rc-hint">还没有可选的知识库，可先到「知识库」页创建。</p>
          <label class="rc-label">检索模式</label>
          <n-select v-model:value="editor.mode" :options="RAG_MODES" style="width: 240px" />
          <label class="rc-label">Top-K</label>
          <n-input-number v-model:value="editor.k" :min="1" :max="20" style="width: 140px" />
        </template>

        <template v-else>
          <label class="rc-label">{{ kind === 'skill' ? '技能说明' : '规则内容' }} <span class="req">*</span></label>
          <n-input
            v-model:value="editor.markdown"
            type="textarea"
            :autosize="{ minRows: 10, maxRows: 22 }"
            :placeholder="kind === 'skill' ? '支持 Markdown：适用场景、操作步骤、注意事项……' : '支持 Markdown：约束、判定口径、禁止事项……'"
            class="rc-code"
          />
        </template>

        <label class="rc-label">可见范围</label>
        <n-radio-group v-model:value="editor.visibility">
          <n-radio value="team">团队共享（推荐）</n-radio>
          <n-radio value="private">仅自己可见</n-radio>
        </n-radio-group>
      </div>

      <template #footer>
        <div class="rc-modal-foot">
          <n-button :disabled="saving" @click="editor.show = false">取消</n-button>
          <n-button type="primary" :loading="saving" @click="submit">保存</n-button>
        </div>
      </template>
    </n-modal>

    <!-- 详情 -->
    <n-drawer v-model:show="detail.show" :width="560">
      <n-drawer-content :title="detail.item?.name || ''" closable>
        <template v-if="detail.item">
          <div class="rc-detail-meta">
            <span class="rc-kind">{{ cfg.noun }}</span>
            <span class="rc-vis" :class="detail.item.visibility">
              {{ detail.item.visibility === 'team' ? '团队' : '私有' }}
            </span>
            <span class="rc-muted">{{ detail.item.owner_name || '未知作者' }}</span>
            <span class="rc-muted">使用 {{ detail.item.usage_count }}</span>
          </div>
          <p class="rc-detail-summary">{{ detail.item.summary || '（暂无描述）' }}</p>

          <template v-if="detail.item.kind === 'agent'">
            <h3 class="rc-h3">系统提示词</h3>
            <pre class="rc-pre">{{ asText(detail.item.content.system_prompt) || '（空）' }}</pre>
            <h3 class="rc-h3">可用工具</h3>
            <div class="rc-chips">
              <span v-for="tool in asList(detail.item.content.tools)" :key="tool" class="rc-chip">{{ tool }}</span>
              <span v-if="!asList(detail.item.content.tools).length" class="rc-muted">未限定工具</span>
            </div>
          </template>
          <template v-else-if="detail.item.kind === 'script'">
            <h3 class="rc-h3">语言</h3>
            <p class="rc-muted">{{ asText(detail.item.content.language) || '未指定' }}</p>
            <h3 class="rc-h3">脚本内容</h3>
            <pre class="rc-pre">{{ asText(detail.item.content.code) || '（空）' }}</pre>
          </template>
          <template v-else-if="detail.item.kind === 'rag'">
            <h3 class="rc-h3">检索口径</h3>
            <p class="rc-muted">
              知识库：{{ asText(detail.item.content.kb_name) || asText(detail.item.content.kb_id) }}
              · 模式 {{ asText(detail.item.content.mode) || 'hybrid' }}
              · Top-{{ detail.item.content.k || 5 }}
            </p>
            <h3 class="rc-h3">试检索</h3>
            <div class="rc-probe">
              <n-input v-model:value="probe.query" placeholder="输入一个问题，用这份口径检索一次" @keyup.enter="runProbe" />
              <n-button :loading="probe.loading" @click="runProbe">检索</n-button>
            </div>
            <p v-if="probe.error" class="rc-probe-err">{{ probe.error }}</p>
            <ol v-if="probe.items.length" class="rc-probe-list">
              <li v-for="(hit, index) in probe.items" :key="hit.chunk_id">
                <span class="rc-probe-rank">{{ index + 1 }}</span>
                <span class="rc-probe-main">
                  <b>{{ hit.doc_name || '未命名文档' }}</b>
                  <small>{{ hit.similarity != null ? '相似度 ' + hit.similarity.toFixed(3) : '相似度 —' }}</small>
                  <p>{{ hit.text }}</p>
                </span>
              </li>
            </ol>
            <p v-else-if="probe.done && !probe.error" class="rc-muted">这次检索没有召回内容。</p>
          </template>

          <template v-else>
            <h3 class="rc-h3">{{ detail.item.kind === 'skill' ? '技能说明' : '规则内容' }}</h3>
            <pre class="rc-pre">{{ asText(detail.item.content.markdown) || '（空）' }}</pre>
          </template>

          <p v-if="detail.item.source_id" class="rc-lineage">来源：基于其他资源创建（来源 ID {{ detail.item.source_id.slice(0, 8) }}）</p>
        </template>

        <template #footer>
          <n-button v-if="detail.item" @click="useItem(detail.item)">使用并复制</n-button>
          <n-button v-if="detail.item" type="primary" @click="cloneItem(detail.item)">基于此创建</n-button>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { api } from '../api/http'
import { resources, type ResourceItem, type ResourceKind, type ResourceVisibility } from '../api/resources'

const route = useRoute()
const message = useMessage()

interface KindConfig {
  title: string
  sub: string
  noun: string
  t: string
  c: string
}

const CONFIG: Record<ResourceKind, KindConfig> = {
  agent: { title: 'Agent 中心', sub: '集中管理智能体 · 灵活配置 · 即调即用', noun: 'Agent', t: 'var(--t-agent)', c: 'var(--c-agent)' },
  skill: { title: 'Skills 中心', sub: '把可复用的操作经验沉淀成技能，团队随取随用', noun: 'Skill', t: 'var(--t-datasets)', c: 'var(--c-datasets)' },
  script: { title: 'Script 中心', sub: '集中管理脚本 · 支持多语言 · 快速复用', noun: 'Script', t: 'var(--t-reports)', c: 'var(--c-reports)' },
  rule: { title: 'Rules 中心', sub: '把判定口径与红线固化成规则，减少来回确认', noun: 'Rule', t: 'var(--t-profiles)', c: 'var(--c-profiles)' },
  rag: { title: 'RAG 中心', sub: '把知识库与检索口径存成可复用资源，随手试检索', noun: 'RAG', t: 'var(--t-kb)', c: 'var(--c-kb)' },
}

const TOOLS = [
  { label: 'read（读文件）', value: 'read' },
  { label: 'write（写文件）', value: 'write' },
  { label: 'edit（改文件）', value: 'edit' },
  { label: 'bash（执行命令）', value: 'bash' },
  { label: 'web_search（联网搜索）', value: 'web_search' },
  { label: 'task（任务中心）', value: 'task' },
]
const RAG_MODES = [
  { label: 'hybrid（混合，推荐）', value: 'hybrid' },
  { label: 'naive（纯向量）', value: 'naive' },
  { label: 'local（实体局部）', value: 'local' },
  { label: 'global（全局关系）', value: 'global' },
]
const LANGUAGES = [
  { label: 'Python', value: 'python' },
  { label: 'Bash', value: 'bash' },
  { label: 'JavaScript', value: 'javascript' },
]

const kind = computed<ResourceKind>(() => (route.meta.resourceKind as ResourceKind) || 'agent')
const cfg = computed(() => CONFIG[kind.value] || CONFIG.agent)

const items = ref<ResourceItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const query = ref('')
const scope = ref<'all' | 'mine'>('all')
const sort = ref<'recent' | 'popular'>('recent')
const scopeOptions = [
  { label: '全部可见', value: 'all' },
  { label: '我创建的', value: 'mine' },
]
const sortOptions = [
  { label: '最近更新', value: 'recent' },
  { label: '使用最多', value: 'popular' },
]

const emptyText = computed(() =>
  query.value ? '没有匹配的资源，换个关键词试试' : `还没有${cfg.value.noun}，新建一个并共享给团队`,
)

const editor = reactive({
  show: false,
  id: '' as string,
  name: '',
  summary: '',
  visibility: 'team' as ResourceVisibility,
  prompt: '',
  tools: [] as string[],
  markdown: '',
  language: 'python',
  code: '',
  kbId: '' as string,
  mode: 'hybrid',
  k: 5,
})
const saving = ref(false)

const detail = reactive({ show: false, item: null as ResourceItem | null })

// RAG 资源需要选知识库：按需加载，避免每次进页面都请求。
const kbOptions = ref<{ label: string; value: string }[]>([])
async function loadKbs(): Promise<void> {
  if (kbOptions.value.length) return
  try {
    const list = await api.kb.list()
    kbOptions.value = list.map((kb) => ({ label: kb.name, value: kb.id }))
  } catch {
    kbOptions.value = []
  }
}

// 详情里的「试检索」：直接用这份资源固化的口径打一次真实检索。
const probe = reactive({
  query: '',
  loading: false,
  error: '',
  done: false,
  items: [] as { chunk_id: string; doc_name: string; similarity: number | null; text: string }[],
})

/** 秒级时间戳转「今天 / 昨天 / MM-DD」，列表里只表达新鲜度。 */
function shortTime(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) return `今天 ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  return `${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const asText = (value: unknown): string => (typeof value === 'string' ? value : '')
const asList = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [])

async function reload(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const page = await resources.list({
      kind: kind.value,
      scope: scope.value,
      sort: sort.value,
      q: query.value.trim(),
      limit: 60,
    })
    items.value = page.items
    total.value = page.total
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载失败'
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function openEditor(item?: ResourceItem): void {
  editor.show = true
  editor.id = item?.id || ''
  editor.name = item?.name || ''
  editor.summary = item?.summary || ''
  editor.visibility = item?.visibility || 'team'
  const content = item?.content || {}
  editor.prompt = asText(content.system_prompt)
  editor.tools = asList(content.tools)
  editor.markdown = asText(content.markdown)
  editor.language = asText(content.language) || 'python'
  editor.code = asText(content.code)
  editor.kbId = asText(content.kb_id)
  editor.mode = asText(content.mode) || 'hybrid'
  editor.k = Number(content.k) || 5
  if (kind.value === 'rag') void loadKbs()
}

/** 按类型组装 content，避免把无关字段写进 JSONB。 */
function buildContent(): Record<string, unknown> {
  if (kind.value === 'agent') {
    return { system_prompt: editor.prompt.trim(), tools: editor.tools }
  }
  if (kind.value === 'script') {
    return { language: editor.language, code: editor.code }
  }
  if (kind.value === 'rag') {
    return { kb_id: editor.kbId, mode: editor.mode, k: editor.k }
  }
  return { markdown: editor.markdown }
}

function validate(): string {
  if (!editor.name.trim()) return '请填写名称'
  if (kind.value === 'agent' && !editor.prompt.trim()) return '请填写系统提示词'
  if (kind.value === 'script' && !editor.code.trim()) return '请填写脚本内容'
  if ((kind.value === 'skill' || kind.value === 'rule') && !editor.markdown.trim()) return '请填写内容'
  if (kind.value === 'rag' && !editor.kbId) return '请选择要绑定的知识库'
  return ''
}

async function submit(): Promise<void> {
  const problem = validate()
  if (problem) {
    message.warning(problem)
    return
  }
  saving.value = true
  try {
    const payload = {
      name: editor.name.trim(),
      summary: editor.summary.trim(),
      content: buildContent(),
      visibility: editor.visibility,
    }
    if (editor.id) {
      await resources.update(editor.id, payload)
      message.success('已保存')
    } else {
      await resources.create({ kind: kind.value, ...payload })
      message.success('已创建')
    }
    editor.show = false
    await reload()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 使用：计数 + 复制内容，用户可直接粘贴到对话或脚本里。 */
async function useItem(item: ResourceItem): Promise<void> {
  try {
    const result = await resources.use(item.id)
    item.usage_count = result.usage_count
    const text = contentToText(item.kind, result.content)
    if (text) {
      await navigator.clipboard.writeText(text).catch(() => undefined)
      message.success(`已记录使用并复制内容（共 ${result.usage_count} 次）`)
    } else {
      message.success(`已记录使用（共 ${result.usage_count} 次）`)
    }
  } catch (err) {
    message.error(err instanceof Error ? err.message : '操作失败')
  }
}

/** 把资源内容拍平成可粘贴文本。 */
function contentToText(kindName: string, content: Record<string, unknown>): string {
  if (kindName === 'agent') {
    const tools = asList(content.tools)
    return `${asText(content.system_prompt)}\n\n可用工具：${tools.length ? tools.join(', ') : '不限定'}`
  }
  if (kindName === 'script') return asText(content.code)
  return asText(content.markdown)
}

async function cloneItem(item: ResourceItem): Promise<void> {
  try {
    const copy = await resources.clone(item.id)
    message.success(`已创建副本「${copy.name}」，可在「我创建的」里查看`)
    await reload()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '创建副本失败')
  }
}

function askDelete(item: ResourceItem): void {
  const dlg = window.confirm(`删除「${item.name}」？该操作不可恢复，已克隆的副本不受影响。`)
  if (!dlg) return
  void removeItem(item)
}

async function removeItem(item: ResourceItem): Promise<void> {
  try {
    await resources.remove(item.id)
    message.success('已删除')
    if (detail.item?.id === item.id) detail.show = false
    await reload()
  } catch (err) {
    message.error(err instanceof Error ? err.message : '删除失败')
  }
}

function openDetail(item: ResourceItem): void {
  detail.item = item
  detail.show = true
  probe.query = ''
  probe.items = []
  probe.error = ''
  probe.done = false
}

/** 用资源固化的模式与 Top-K 真跑一次知识库检索。 */
async function runProbe(): Promise<void> {
  const item = detail.item
  if (!item || item.kind !== 'rag') return
  const question = probe.query.trim()
  if (!question) {
    message.warning('请输入检索问题')
    return
  }
  probe.loading = true
  probe.error = ''
  probe.items = []
  probe.done = false
  try {
    const result = await api.kb.query(asText(item.content.kb_id), {
      query: question,
      mode: asText(item.content.mode) || 'hybrid',
      k: Number(item.content.k) || 5,
    })
    probe.items = (result.items || []).slice(0, 8)
    probe.done = true
  } catch (err) {
    probe.error = err instanceof Error ? err.message : '检索失败'
    probe.done = true
  } finally {
    probe.loading = false
  }
}

// 从导航切换类型时（/agents → /skills）复用同一组件，需要重新拉数据。
watch(kind, () => {
  query.value = ''
  scope.value = 'all'
  sort.value = 'recent'
  void reload()
})

onMounted(reload)
</script>

<style scoped>
.rc-page { display: flex; flex-direction: column; gap: 14px; }
.rc-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.eyebrow { font-size: 12px; letter-spacing: .12em; color: var(--text-tertiary); text-transform: uppercase; }
.rc-head h1 { margin: 4px 0 4px; font-size: 22px; }
.rc-head p { margin: 0; color: var(--text-secondary); font-size: 13.5px; }
.rc-head-actions { display: flex; gap: 8px; }

.rc-toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.rc-toolbar :deep(.n-input) { max-width: 320px; }

.rc-caption { margin: 0; font-size: 12.5px; color: var(--text-secondary); display: flex; gap: 10px; flex-wrap: wrap; }
.rc-caption span { color: var(--text-tertiary); }

.rc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
.rc-card {
  display: flex; flex-direction: column; gap: 8px;
  border: 1px solid var(--border-subtle); border-radius: 14px; padding: 14px 16px;
  background: var(--bg-card);
  transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease;
}
.rc-card:hover { border-color: var(--c); box-shadow: 0 6px 20px rgba(15, 23, 42, .06); transform: translateY(-1px); }
.rc-card-top { display: flex; align-items: center; gap: 8px; min-width: 0; }
.rc-kind {
  flex: 0 0 auto; font-size: 11px; font-weight: 700; letter-spacing: .04em;
  padding: 2px 7px; border-radius: 6px; background: var(--t); color: var(--c);
}
.rc-vis { flex: 0 0 auto; font-size: 11px; padding: 2px 7px; border-radius: 6px; border: 1px solid var(--border-subtle); color: var(--text-secondary); }
.rc-vis.private { border-style: dashed; }
.rc-name {
  flex: 1 1 auto; min-width: 0; border: 0; background: none; padding: 0; text-align: left;
  font-size: 14.5px; font-weight: 650; color: var(--text-primary); cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rc-name:hover { color: var(--c); }
.rc-summary {
  margin: 0; font-size: 13px; line-height: 1.55; color: var(--text-secondary);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 40px;
}
.rc-meta { display: flex; gap: 6px; font-size: 11.5px; color: var(--text-tertiary); flex-wrap: wrap; }
.rc-actions { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }

.rc-empty, .rc-error { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 0; }
.rc-error :deep(.n-alert) { max-width: 520px; }

.rc-form { display: flex; flex-direction: column; gap: 6px; }
.rc-label { font-size: 12.5px; color: var(--text-secondary); margin-top: 6px; }
.rc-label .req { color: var(--danger); margin-left: 2px; }
.rc-tools { display: flex; flex-wrap: wrap; gap: 4px 16px; }
.rc-code :deep(textarea) { font-family: var(--font-mono); font-size: 12.5px; }
.rc-modal-foot { display: flex; justify-content: flex-end; gap: 10px; }

.rc-detail-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.rc-muted { color: var(--text-secondary); font-size: 12.5px; }
.rc-detail-summary { color: var(--text-secondary); font-size: 13.5px; margin: 10px 0 6px; }
.rc-h3 { font-size: 13px; margin: 16px 0 6px; color: var(--text-primary); }
.rc-pre {
  margin: 0; padding: 12px 14px; border: 1px solid var(--border-subtle); border-radius: 10px;
  background: var(--bg-elevated); color: var(--text-primary);
  font: 12.5px/1.7 var(--font-mono); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 340px; overflow: auto;
}
.rc-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.rc-chip { font-size: 11.5px; padding: 2px 8px; border-radius: 999px; background: var(--bg-elevated); color: var(--text-secondary); border: 1px solid var(--border-subtle); }
.rc-lineage { margin-top: 16px; font-size: 12px; color: var(--text-tertiary); }
.rc-hint { margin: 4px 0 0; font-size: 12px; color: var(--accent-warning); }
.rc-probe { display: flex; gap: 8px; align-items: center; }
.rc-probe-err { margin: 8px 0 0; font-size: 12.5px; color: var(--danger); }
.rc-probe-list { list-style: none; margin: 10px 0 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.rc-probe-list li { display: flex; gap: 8px; padding: 10px 12px; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--bg-card); }
.rc-probe-rank { flex: 0 0 auto; width: 18px; height: 18px; border-radius: 50%; background: var(--bg-elevated); color: var(--text-secondary); font-size: 11px; display: grid; place-items: center; }
.rc-probe-main { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.rc-probe-main b { font-size: 12.5px; }
.rc-probe-main small { font-size: 11px; color: var(--text-tertiary); }
.rc-probe-main p { margin: 4px 0 0; font-size: 12.5px; line-height: 1.6; color: var(--text-secondary); display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
</style>
