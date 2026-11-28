<template>
  <div class="workbench-page">
    <header class="workbench-intro">
      <p>浏览团队共享的智能体、技能、脚本、规则和检索配置。</p>
      <div class="pl-stats">
        <div><b>{{ data?.total ?? '—' }}</b><span>团队资源</span></div>
        <div><b>{{ data?.featured.length ?? '—' }}</b><span>精选</span></div>
        <div><b>{{ totalUses }}</b><span>热门榜累计使用</span></div>
      </div>
    </header>

    <n-spin :show="loading">
      <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>

      <section class="pl-section">
        <div class="pl-section-head">
          <h2>精选组件</h2>
          <span>按累计使用挑选，定期更新</span>
        </div>
        <div v-if="!data?.featured.length" class="pl-empty">
          <n-empty description="还没有资源，去对应中心创建第一个" />
        </div>
        <div v-else class="pl-featured">
          <router-link
            v-for="item in data.featured"
            :key="item.id"
            :to="kindStyle(item.kind).path"
            class="pl-hero-card"
            :style="{ '--t': kindStyle(item.kind).t, '--c': kindStyle(item.kind).c }"
            :aria-label="item.name"
          >
            <div class="pl-hero-top">
              <span class="pl-kind">{{ kindStyle(item.kind).noun }}</span>
              <span class="pl-uses">使用 {{ item.usage_count }}</span>
            </div>
            <h3>{{ item.name }}</h3>
            <p>{{ item.summary || '（暂无描述）' }}</p>
            <div class="pl-hero-foot">
              <span>{{ item.owner_name || '未知作者' }}</span>
              <span class="pl-go" aria-hidden="true">→</span>
            </div>
          </router-link>
        </div>
      </section>

      <section class="pl-boards">
        <div v-for="board in boards" :key="board.key" class="pl-board">
          <div class="pl-board-head">
            <h2>{{ board.title }}</h2>
            <span>{{ board.hint }}</span>
          </div>
          <ol v-if="board.items.length" class="pl-rank">
            <li v-for="(item, index) in board.items.slice(0, 8)" :key="item.id">
              <router-link class="pl-rank-link" :to="kindStyle(item.kind).path" :aria-label="item.name">
                <span class="pl-no" :class="{ top: index < 3 }">{{ index + 1 }}</span>
                <span class="pl-rank-main">
                  <span class="pl-rank-name">{{ item.name }}</span>
                  <span class="pl-rank-meta">
                    <span class="pl-tag" :style="{ '--t': kindStyle(item.kind).t, '--c': kindStyle(item.kind).c }">{{ kindStyle(item.kind).noun }}</span>
                    <span>{{ item.owner_name || '未知' }}</span>
                  </span>
                </span>
                <span class="pl-score">{{ board.score(item) }}</span>
              </router-link>
            </li>
          </ol>
          <p v-else class="pl-board-empty">{{ board.empty }}</p>
        </div>
      </section>

      <p class="pl-footnote">
        榜单口径：热门按累计使用次数，飙升按近 7 日使用事件数，新品按创建时间；没有使用记录的资源不进飙升榜。
      </p>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { resources, type Plaza, type PlazaRankItem, type ResourceKind } from '../api/resources'

const data = ref<Plaza | null>(null)
const loading = ref(false)
const error = ref('')

const KIND_META: Record<ResourceKind, { noun: string; path: string; t: string; c: string }> = {
  agent: { noun: 'Agent', path: '/agents', t: 'var(--t-agent)', c: 'var(--c-agent)' },
  skill: { noun: 'Skill', path: '/skills', t: 'var(--t-datasets)', c: 'var(--c-datasets)' },
  script: { noun: 'Script', path: '/scripts', t: 'var(--t-reports)', c: 'var(--c-reports)' },
  rule: { noun: 'Rule', path: '/rules', t: 'var(--t-profiles)', c: 'var(--c-profiles)' },
  rag: { noun: 'RAG', path: '/rag', t: 'var(--t-kb)', c: 'var(--c-kb)' },
}

const kindStyle = (kind: ResourceKind) => KIND_META[kind] || KIND_META.agent

const totalUses = computed(() => {
  if (!data.value) return '—'
  const seen = new Set<string>()
  let sum = 0
  for (const row of data.value.popular) {
    if (seen.has(row.id)) continue
    seen.add(row.id)
    sum += row.usage_count
  }
  return sum
})

const boards = computed(() => {
  const empty: PlazaRankItem[] = []
  return [
    {
      key: 'popular',
      title: '热门榜',
      hint: '累计使用最多',
      items: data.value?.popular || empty,
      score: (item: PlazaRankItem) => item.usage_count,
      empty: '还没有使用记录',
    },
    {
      key: 'rising',
      title: '飙升榜',
      hint: '近 7 日使用增长',
      items: data.value?.rising || empty,
      score: (item: PlazaRankItem) => item.weekly_uses,
      empty: '近 7 天还没有新的使用记录',
    },
    {
      key: 'newest',
      title: '新品榜',
      hint: '最近创建',
      items: data.value?.newest || empty,
      score: (item: PlazaRankItem) => item.created_at.slice(5, 10),
      empty: '还没有新资源',
    },
  ]
})

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await resources.plaza()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '加载广场失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.pl-stats { display: flex; flex-wrap: wrap; gap: var(--space-2) var(--space-4); }
.pl-stats div { display: flex; flex-direction: column; }
.pl-stats b { font-size: 22px; font-variant-numeric: tabular-nums; }
.pl-stats span { font-size: 11.5px; color: var(--text-tertiary); }

.pl-section-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-1) var(--space-3); margin-bottom: var(--space-3); }
.pl-section-head h2 { font-size: 16px; margin: 0; }
.pl-section-head span { font-size: 12px; color: var(--text-tertiary); }

.pl-featured { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 18rem), 1fr)); gap: var(--space-3); }
.pl-hero-card {
  display: flex; flex-direction: column; min-width: 0; overflow-wrap: anywhere;
  border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); padding: var(--space-4);
  background:
    radial-gradient(120% 90% at 100% 0%, color-mix(in srgb, var(--c) 9%, transparent), transparent 60%),
    var(--bg-card);
  transition: border-color .15s ease;
}
.pl-hero-card:hover, .pl-hero-card:focus-visible { border-color: var(--c); }
.pl-hero-top { display: flex; justify-content: space-between; align-items: center; }
.pl-kind { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 6px; background: var(--t); color: var(--c); }
.pl-uses { font-size: 11.5px; color: var(--text-tertiary); }
.pl-hero-card h3 { margin: 10px 0 6px; font-size: 16px; }
.pl-hero-card p { margin: 0; font-size: 12.8px; line-height: 1.55; color: var(--text-secondary); min-height: 38px; }
.pl-hero-foot { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); margin-top: auto; padding-top: var(--space-3); font-size: 12px; color: var(--text-tertiary); }
.pl-go { color: var(--c); font-weight: 600; }

.pl-boards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)); gap: var(--space-3); margin-top: var(--space-4); }
.pl-board { min-width: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-lg); background: var(--bg-card); padding: var(--space-4); }
.pl-board-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--space-1) var(--space-2); margin-bottom: var(--space-2); }
.pl-board-head h2 { font-size: 14.5px; margin: 0; }
.pl-board-head span { font-size: 11.5px; color: var(--text-tertiary); }
.pl-rank { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
.pl-rank li { border-bottom: 1px solid var(--border-subtle); }
.pl-rank-link {
  display: flex; align-items: center; gap: 10px; padding: 8px 4px;
  border-radius: var(--radius-sm);
}
.pl-rank li:last-child { border-bottom: 0; }
.pl-rank-link:hover { background: var(--row-hover); }
.pl-no { width: 18px; font-variant-numeric: tabular-nums; font-weight: 700; color: var(--text-tertiary); font-size: 12.5px; }
.pl-no.top { color: var(--accent-warning); }
.pl-rank-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.pl-rank-name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-rank-meta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--text-tertiary); }
.pl-rank-meta span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-tag { padding: 1px 6px; border-radius: 5px; background: var(--t); color: var(--c); font-size: 10.5px; }
.pl-score { font-size: 12px; font-variant-numeric: tabular-nums; color: var(--text-secondary); }
.pl-board-empty, .pl-empty { color: var(--text-tertiary); font-size: 12.5px; padding: 18px 0; text-align: center; }
.pl-footnote { margin-top: var(--space-3); font-size: 12px; color: var(--text-tertiary); }
</style>
