<template>
  <div class="my-models-page">
    <div class="row-between">
      <div class="info-strip" style="margin: 0; padding: 6px 14px; border-radius: 8px">
        我的模型仅本人可见、仅本人可用；平台公共模型由管理端维护，所有成员均可选用。API Key 只写不回显。
      </div>
    </div>

    <div class="panel" style="--glow-c: var(--c-profiles)">
      <div class="panel-title">
        <div class="row">
          <span>我的私有模型</span>
          <span class="mono" style="font-size: 12px; color: var(--text-tertiary)">({{ personalProfiles.length }} 个)</span>
        </div>
        <div class="row">
          <button class="btn btn-primary btn-sm" @click="openCreate">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
            <span>添加我的模型</span>
          </button>
          <button class="btn btn-secondary btn-sm" :disabled="loading" @click="loadProfiles">
            <span>刷新</span>
          </button>
        </div>
      </div>

      <p v-if="loading" class="small tertiary" role="status">正在加载我的模型…</p>
      <EmptyState
        v-else-if="!personalProfiles.length"
        title="还没有个人模型"
        description="添加后只在你自己的对话模型列表中显示，其他成员不可见。"
      >
        <template #action>
          <button class="btn btn-primary btn-sm" @click="openCreate">添加我的模型</button>
        </template>
      </EmptyState>

      <table v-else class="ds-table">
        <thead>
          <tr>
            <th>模型名称</th>
            <th style="width: 150px">协议类型</th>
            <th style="width: 220px">模型标识</th>
            <th style="width: 120px">密钥</th>
            <th style="width: 150px">更新时间</th>
            <th style="width: 140px; text-align: right">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in personalProfiles" :key="p.id">
            <td>
              <div class="model-name-cell">
                <ProviderLogo :provider="getModelLogoKey(p.model)" compact :size="18" />
                <span>{{ p.name }}</span>
                <span v-if="p.usages?.includes('agent')" class="tag-soft">可用于对话</span>
              </div>
            </td>
            <td><span class="mono" style="font-size: 12px">{{ p.protocol }}</span></td>
            <td><span class="mono" style="font-size: 12px">{{ p.model }}</span></td>
            <td>
              <span class="tag-soft" :class="p.has_api_key ? 'key-ok' : 'key-none'">
                {{ p.has_api_key ? '已配置' : '未配置' }}
              </span>
            </td>
            <td class="mono" style="font-size: 12px; color: var(--text-tertiary)">{{ formatTime(p.updated_at || p.created_at) }}</td>
            <td style="text-align: right">
              <div class="row" style="justify-content: flex-end; gap: 8px">
                <button class="link-btn" @click="openEdit(p)">编辑</button>
                <button class="link-btn danger" @click="handleDelete(p)">删除</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <div class="panel-title">
        <div class="row">
          <span>平台公共模型</span>
          <span class="mono" style="font-size: 12px; color: var(--text-tertiary)">({{ platformProfiles.length }} 个，只读)</span>
        </div>
      </div>
      <p v-if="!platformProfiles.length" class="small tertiary">管理端尚未配置平台模型。</p>
      <table v-else class="ds-table">
        <thead>
          <tr>
            <th>模型名称</th>
            <th style="width: 150px">协议类型</th>
            <th style="width: 220px">模型标识</th>
            <th style="width: 120px">用途</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in platformProfiles" :key="p.id">
            <td>
              <div class="model-name-cell">
                <ProviderLogo :provider="getModelLogoKey(p.model)" compact :size="18" />
                <span>{{ p.name }}</span>
              </div>
            </td>
            <td><span class="mono" style="font-size: 12px">{{ p.protocol }}</span></td>
            <td><span class="mono" style="font-size: 12px">{{ p.model }}</span></td>
            <td>
              <div class="row wrap" style="gap: 4px">
                <span v-if="p.usages?.includes('agent')" class="kind-tag kind-rag">Agent</span>
                <span v-if="p.usages?.includes('target')" class="kind-tag kind-benchmark">被测</span>
                <span v-if="p.usages?.includes('judge')" class="kind-tag kind-cases">裁判</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ProfileModal
      v-model:show="showModal"
      :profile="selectedProfile"
      scope="personal"
      :default-usages="['agent']"
      @success="loadProfiles"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useDialog, useMessage } from 'naive-ui'

import { api } from '../api/http'
import type { Profile } from '../api/types'
import { useAuthStore } from '../stores/auth'
import { getModelLogoKey } from '../utils/providerLogo'
import { safeBlur } from '../utils/dom'
import ProviderLogo from '../components/ProviderLogo.vue'
import EmptyState from '../components/common/EmptyState.vue'
import ProfileModal from '../components/modals/ProfileModal.vue'

const message = useMessage()
const dialog = useDialog()
const auth = useAuthStore()

const profiles = ref<Profile[]>([])
const loading = ref(false)
const showModal = ref(false)
const selectedProfile = ref<Profile | null>(null)

const personalProfiles = computed(() => profiles.value.filter(p => (
  p.visibility === 'personal' && (!p.owner_id || p.owner_id === auth.user?.id)
)))
const platformProfiles = computed(() => profiles.value.filter(p => p.visibility !== 'personal'))

async function loadProfiles() {
  loading.value = true
  try {
    profiles.value = await api.profiles.list()
  } catch (err: any) {
    message.error(err.message || '加载模型失败')
  } finally {
    loading.value = false
  }
}

function openCreate() {
  safeBlur()
  selectedProfile.value = null
  showModal.value = true
}

function openEdit(profile: Profile) {
  safeBlur()
  selectedProfile.value = { ...profile }
  showModal.value = true
}

function handleDelete(profile: Profile) {
  dialog.warning({
    title: `删除模型「${profile.name}」？`,
    content: '删除后该模型与本地密钥配置一并移除，不可恢复。',
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await api.profiles.delete(profile.id)
        message.success('模型已删除')
        await loadProfiles()
      } catch (err: any) {
        message.error(err.message || '删除失败')
      }
    },
  })
}

/** 与账号页一致：只展示到分钟，避免把毫秒噪声带进表格。 */
function formatTime(value?: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

onMounted(loadProfiles)
</script>

<style scoped>
.my-models-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}
.model-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 13.5px;
}
.key-ok {
  color: var(--accent-success, #10b981);
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 999px;
  padding: 1px 8px;
}
.key-none {
  color: var(--text-tertiary);
  border: 1px solid var(--border-subtle, rgba(0, 0, 0, 0.08));
  border-radius: 999px;
  padding: 1px 8px;
}
</style>
