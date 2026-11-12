<template>
  <div class="panel">
    <div class="panel-header-row">
      <div class="panel-title-area">
        <span class="panel-title-text">全局向量与重排模型</span>
        <span class="tag-soft">全局生效 · 实时生效</span>
      </div>
      <div class="panel-actions-area">
        <button class="btn btn-secondary btn-sm" :disabled="ragModelsLoading" @click="loadRagModels">
          重置
        </button>
        <button class="btn btn-primary btn-sm" :disabled="ragModelsSaving" @click="saveRagModels">
          {{ ragModelsSaving ? '保存中…' : '保存全局配置' }}
        </button>
      </div>
    </div>

    <div class="rag-models-grid mt16">
      <!-- 1. 全局向量嵌入模型 (Embedding) -->
      <div class="rag-model-card">
        <div class="rag-card-header">
          <div class="row" style="gap: 8px; align-items: center">
            <span class="rag-type-pill">向量嵌入 (Embedding)</span>
            <span class="rag-model-sub">知识库向量化与语义检索</span>
          </div>
          <span v-if="ragModelsForm.has_embedding_api_key" class="key-status-badge ok" title="已加密存储密钥">
            ● 已配置密钥
          </span>
          <span v-else class="key-status-badge none" title="未配置密钥时使用免密端点或平台默认">
            ○ 免密 / 全局
          </span>
        </div>

        <div class="field mt12">
          <label class="field-label">常用预设</label>
          <n-select
            :options="embeddingPresetOptions"
            placeholder="选择常用向量模型预设一键填充…"
            @update:value="handleSelectEmbeddingPreset"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">Base URL <span class="req">*</span></label>
          <n-input
            v-model:value="ragModelsForm.embedding_base_url"
            placeholder="例如：https://api.siliconflow.cn/v1"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">模型标识 (Model ID) <span class="req">*</span></label>
          <n-input
            v-model:value="ragModelsForm.embedding_model"
            placeholder="例如：BAAI/bge-large-zh-v1.5"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">API Key</label>
          <n-input
            v-model:value="ragModelsForm.embedding_api_key"
            type="password"
            show-password-on="click"
            :placeholder="ragModelsForm.has_embedding_api_key ? '********* (已保存密钥，留空保持不变)' : '可选；私有端点或免密模型可留空'"
          />
        </div>

        <div class="rag-check-row mt16">
          <button
            class="btn btn-secondary btn-xs"
            :disabled="checkingEmbedding || !ragModelsForm.embedding_base_url || !ragModelsForm.embedding_model"
            @click="handleCheckEmbedding"
          >
            {{ checkingEmbedding ? '探活中…' : '端点连通测试' }}
          </button>
          <div v-if="embeddingCheckResult" class="rag-check-feedback" :class="embeddingCheckResult.ok ? 'success' : 'fail'">
            <span v-if="embeddingCheckResult.ok">✓ 连通正常 ({{ embeddingCheckResult.latency_ms }}ms)</span>
            <span v-else>✕ {{ embeddingCheckResult.message }}</span>
          </div>
        </div>
      </div>

      <!-- 2. 全局重排序模型 (Reranker) -->
      <div class="rag-model-card">
        <div class="rag-card-header">
          <div class="row" style="gap: 8px; align-items: center">
            <span class="rag-type-pill">语义重排 (Reranker)</span>
            <span class="rag-model-sub">Top-K 候选打分与二次降噪</span>
          </div>
          <span v-if="ragModelsForm.has_reranker_api_key" class="key-status-badge ok" title="已加密存储密钥">
            ● 已配置密钥
          </span>
          <span v-else class="key-status-badge none" title="未配置密钥时使用免密端点或平台默认">
            ○ 免密 / 全局
          </span>
        </div>

        <div class="field mt12">
          <label class="field-label">常用预设</label>
          <n-select
            :options="rerankerPresetOptions"
            placeholder="选择常用重排模型预设一键填充…"
            @update:value="handleSelectRerankerPreset"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">Base URL <span class="req">*</span></label>
          <n-input
            v-model:value="ragModelsForm.reranker_base_url"
            placeholder="例如：https://api.siliconflow.cn/v1"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">模型标识 (Model ID) <span class="req">*</span></label>
          <n-input
            v-model:value="ragModelsForm.reranker_model"
            placeholder="例如：BAAI/bge-reranker-v2-m3"
          />
        </div>

        <div class="field mt12">
          <label class="field-label">API Key</label>
          <n-input
            v-model:value="ragModelsForm.reranker_api_key"
            type="password"
            show-password-on="click"
            :placeholder="ragModelsForm.has_reranker_api_key ? '********* (已保存密钥，留空保持不变)' : '可选；私有端点或免密模型可留空'"
          />
        </div>

        <div class="rag-check-row mt16">
          <button
            class="btn btn-secondary btn-xs"
            :disabled="checkingReranker || !ragModelsForm.reranker_base_url || !ragModelsForm.reranker_model"
            @click="handleCheckReranker"
          >
            {{ checkingReranker ? '探活中…' : '端点连通测试' }}
          </button>
          <div v-if="rerankerCheckResult" class="rag-check-feedback" :class="rerankerCheckResult.ok ? 'success' : 'fail'">
            <span v-if="rerankerCheckResult.ok">✓ 连通正常 ({{ rerankerCheckResult.latency_ms }}ms)</span>
            <span v-else>✕ {{ rerankerCheckResult.message }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useMessage } from 'naive-ui'

import { api } from '../../api/http'

const message = useMessage()

const ragModelsForm = ref<{
  embedding_base_url: string
  embedding_model: string
  embedding_api_key: string
  has_embedding_api_key?: boolean
  reranker_base_url: string
  reranker_model: string
  reranker_api_key: string
  has_reranker_api_key?: boolean
}>({
  embedding_base_url: '',
  embedding_model: '',
  embedding_api_key: '',
  reranker_base_url: '',
  reranker_model: '',
  reranker_api_key: '',
})
const ragModelsLoading = ref(false)
const ragModelsSaving = ref(false)

const embeddingPresetOptions = [
  { label: 'SiliconFlow (BAAI/bge-large-zh-v1.5)', value: 'sf-bge-large' },
  { label: 'SiliconFlow (BAAI/bge-m3)', value: 'sf-bge-m3' },
  { label: 'OpenAI (text-embedding-3-small)', value: 'openai-small' },
  { label: 'OpenAI (text-embedding-3-large)', value: 'openai-large' },
  { label: 'Alibaba DashScope (text-embedding-v3)', value: 'dashscope-v3' },
  { label: 'Zhipu AI (embedding-3)', value: 'zhipu-3' },
  { label: 'Ollama Local (nomic-embed-text)', value: 'ollama-nomic' },
]

const EMBEDDING_PRESET_MAP: Record<string, { base_url: string; model: string }> = {
  'sf-bge-large': { base_url: 'https://api.siliconflow.cn/v1', model: 'BAAI/bge-large-zh-v1.5' },
  'sf-bge-m3': { base_url: 'https://api.siliconflow.cn/v1', model: 'BAAI/bge-m3' },
  'openai-small': { base_url: 'https://api.openai.com/v1', model: 'text-embedding-3-small' },
  'openai-large': { base_url: 'https://api.openai.com/v1', model: 'text-embedding-3-large' },
  'dashscope-v3': { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'text-embedding-v3' },
  'zhipu-3': { base_url: 'https://open.bigmodel.cn/api/paas/v4', model: 'embedding-3' },
  'ollama-nomic': { base_url: 'http://localhost:11434/v1', model: 'nomic-embed-text' },
}

function handleSelectEmbeddingPreset(key: string) {
  const item = EMBEDDING_PRESET_MAP[key]
  if (!item) return
  ragModelsForm.value.embedding_base_url = item.base_url
  ragModelsForm.value.embedding_model = item.model
  message.info(`已填充预设: ${item.model}`)
}

const rerankerPresetOptions = [
  { label: 'SiliconFlow (BAAI/bge-reranker-v2-m3)', value: 'sf-rerank-v2-m3' },
  { label: 'SiliconFlow (BAAI/bge-reranker-large)', value: 'sf-rerank-large' },
  { label: 'Jina AI (jina-reranker-v2-base-multilingual)', value: 'jina-v2' },
  { label: 'Alibaba DashScope (gte-rerank)', value: 'dashscope-gte' },
  { label: 'Cohere (rerank-v3.5)', value: 'cohere-v3.5' },
]

const RERANKER_PRESET_MAP: Record<string, { base_url: string; model: string }> = {
  'sf-rerank-v2-m3': { base_url: 'https://api.siliconflow.cn/v1', model: 'BAAI/bge-reranker-v2-m3' },
  'sf-rerank-large': { base_url: 'https://api.siliconflow.cn/v1', model: 'BAAI/bge-reranker-large' },
  'jina-v2': { base_url: 'https://api.jina.ai/v1', model: 'jina-reranker-v2-base-multilingual' },
  'dashscope-gte': { base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1', model: 'gte-rerank' },
  'cohere-v3.5': { base_url: 'https://api.cohere.com/v2', model: 'rerank-v3.5' },
}

function handleSelectRerankerPreset(key: string) {
  const item = RERANKER_PRESET_MAP[key]
  if (!item) return
  ragModelsForm.value.reranker_base_url = item.base_url
  ragModelsForm.value.reranker_model = item.model
  message.info(`已填充预设: ${item.model}`)
}

const checkingEmbedding = ref(false)
const embeddingCheckResult = ref<{ ok: boolean; latency_ms?: number; message?: string } | null>(null)

async function handleCheckEmbedding() {
  if (!ragModelsForm.value.embedding_base_url.trim() || !ragModelsForm.value.embedding_model.trim()) {
    message.warning('请先填写 Embedding Base URL 与模型名称')
    return
  }
  checkingEmbedding.value = true
  embeddingCheckResult.value = null
  try {
    const res = await api.admin.checkRagModel({
      target: 'embedding',
      base_url: ragModelsForm.value.embedding_base_url.trim(),
      model: ragModelsForm.value.embedding_model.trim(),
      api_key: ragModelsForm.value.embedding_api_key?.trim() || undefined,
    })
    embeddingCheckResult.value = res
    if (res.ok) {
      message.success(`Embedding 连通正常 (${res.latency_ms}ms)`)
    } else {
      message.error(res.message || 'Embedding 连通检测未通过')
    }
  } catch (err: any) {
    embeddingCheckResult.value = { ok: false, message: err.message || '请求异常' }
    message.error(err.message || '探活异常')
  } finally {
    checkingEmbedding.value = false
  }
}

const checkingReranker = ref(false)
const rerankerCheckResult = ref<{ ok: boolean; latency_ms?: number; message?: string } | null>(null)

async function handleCheckReranker() {
  if (!ragModelsForm.value.reranker_base_url.trim() || !ragModelsForm.value.reranker_model.trim()) {
    message.warning('请先填写 Reranker Base URL 与模型名称')
    return
  }
  checkingReranker.value = true
  rerankerCheckResult.value = null
  try {
    const res = await api.admin.checkRagModel({
      target: 'reranker',
      base_url: ragModelsForm.value.reranker_base_url.trim(),
      model: ragModelsForm.value.reranker_model.trim(),
      api_key: ragModelsForm.value.reranker_api_key?.trim() || undefined,
    })
    rerankerCheckResult.value = res
    if (res.ok) {
      message.success(`Reranker 连通正常 (${res.latency_ms}ms)`)
    } else {
      message.error(res.message || 'Reranker 连通检测未通过')
    }
  } catch (err: any) {
    rerankerCheckResult.value = { ok: false, message: err.message || '请求异常' }
    message.error(err.message || '探活异常')
  } finally {
    checkingReranker.value = false
  }
}

async function loadRagModels() {
  ragModelsLoading.value = true
  try {
    const data = await api.admin.getRagModels()
    ragModelsForm.value = {
      embedding_base_url: data.embedding_base_url || '',
      embedding_model: data.embedding_model || '',
      embedding_api_key: '',
      has_embedding_api_key: data.has_embedding_api_key,
      reranker_base_url: data.reranker_base_url || '',
      reranker_model: data.reranker_model || '',
      reranker_api_key: '',
      has_reranker_api_key: data.has_reranker_api_key,
    }
  } catch (err: any) {
    message.error(err.message || '加载全局 RAG 模型配置失败')
  } finally {
    ragModelsLoading.value = false
  }
}

async function saveRagModels() {
  if (
    !ragModelsForm.value.embedding_base_url.trim() &&
    !ragModelsForm.value.embedding_model.trim() &&
    !ragModelsForm.value.reranker_base_url.trim() &&
    !ragModelsForm.value.reranker_model.trim()
  ) {
    message.warning('请至少填写 Embedding 或 Reranker 的基础配置')
    return
  }
  ragModelsSaving.value = true
  try {
    const payload: any = {
      embedding_base_url: ragModelsForm.value.embedding_base_url.trim() || undefined,
      embedding_model: ragModelsForm.value.embedding_model.trim() || undefined,
      reranker_base_url: ragModelsForm.value.reranker_base_url.trim() || undefined,
      reranker_model: ragModelsForm.value.reranker_model.trim() || undefined,
    }
    if (ragModelsForm.value.embedding_api_key?.trim()) {
      payload.embedding_api_key = ragModelsForm.value.embedding_api_key.trim()
    }
    if (ragModelsForm.value.reranker_api_key?.trim()) {
      payload.reranker_api_key = ragModelsForm.value.reranker_api_key.trim()
    }
    const res = await api.admin.updateRagModels(payload)
    ragModelsForm.value = {
      embedding_base_url: res.embedding_base_url || '',
      embedding_model: res.embedding_model || '',
      embedding_api_key: '',
      has_embedding_api_key: res.has_embedding_api_key,
      reranker_base_url: res.reranker_base_url || '',
      reranker_model: res.reranker_model || '',
      reranker_api_key: '',
      has_reranker_api_key: res.has_reranker_api_key,
    }
    message.success('全局 RAG 模型配置已成功保存并生效！')
  } catch (err: any) {
    message.error(err.message || '保存全局 RAG 模型配置失败')
  } finally {
    ragModelsSaving.value = false
  }
}

onMounted(loadRagModels)
</script>

<style scoped>
/* 面板标题行与卡片样式与 AdminProfiles 同源；抽成子组件后需一并携带。 */
.panel-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.panel-title-area {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.panel-title-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #111827);
  letter-spacing: -0.01em;
}
.rag-models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
}
.rag-model-card {
  background: var(--bg-elevated, #f9fafb);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 12px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
}
.rag-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
}
.rag-type-pill {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #111827);
}
.rag-model-sub {
  font-size: 11.5px;
  color: var(--text-tertiary, #9ca3af);
}
.key-status-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  font-weight: 500;
}
.key-status-badge.ok {
  background: rgba(16, 185, 129, 0.1);
  color: var(--accent-success, #10b981);
}
.key-status-badge.none {
  background: var(--bg-card, #ffffff);
  color: var(--text-tertiary, #9ca3af);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
}
.rag-check-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.06));
}
.rag-check-feedback {
  font-size: 11.5px;
}
.rag-check-feedback.success {
  color: var(--accent-success, #10b981);
  font-weight: 500;
}
.rag-check-feedback.fail {
  color: var(--accent-error, #ef4444);
}
</style>
