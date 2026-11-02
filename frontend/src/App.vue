<template>
  <n-config-provider :theme="naiveTheme" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { darkTheme } from 'naive-ui'
import { darkThemeOverrides, themeOverrides as lightThemeOverrides } from './naive-theme'
import { useThemeStore } from './stores/theme'

// 深色模式必须同时切换 CSS 令牌（data-theme）与 Naive UI 主题，
// 否则弹窗、表格、输入框仍按浅色渲染，深色下文字对比度不可用。
const theme = useThemeStore()
const naiveTheme = computed(() => (theme.mode === 'dark' ? darkTheme : null))
const themeOverrides = computed(() =>
  theme.mode === 'dark' ? darkThemeOverrides : lightThemeOverrides,
)
</script>
