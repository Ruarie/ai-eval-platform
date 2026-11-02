<template>
  <div class="not-found">
    <div class="not-found-card panel">
      <div class="not-found-code mono">404</div>
      <h1 class="not-found-title">页面不存在</h1>
      <p class="not-found-desc">
        该地址可能已随版本迭代下线或输入有误，请从左侧导航重新进入。
      </p>
      <div class="not-found-actions">
        <button class="btn btn-primary btn-sm" type="button" @click="goHome">返回智能体</button>
        <button class="btn btn-secondary btn-sm" type="button" @click="goBack">回到上一页</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/agent')
}

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.push('/agent')
}
</script>

<style scoped>
.not-found {
  display: grid;
  place-items: center;
  min-height: 60vh;
  padding: 24px;
}

.not-found-card {
  width: min(460px, 100%);
  padding: 40px 32px;
  text-align: center;
  background: var(--bg-main);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl);
}

.not-found-code {
  font-size: 56px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: 2px;
  color: var(--accent-ai);
  opacity: 0.85;
}

.not-found-title {
  margin: 16px 0 8px;
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.not-found-desc {
  margin: 0 0 24px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.not-found-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}
</style>
