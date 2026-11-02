import { defineStore } from 'pinia'

export type ThemeMode = 'light' | 'dark'

/** 首次访问跟随系统配色；用户显式切换后以 localStorage 为准。 */
function initialMode(): ThemeMode {
  const stored = localStorage.getItem('data-theme')
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useThemeStore = defineStore('theme', {
  state: () => ({
    mode: initialMode(),
    // 导航栏折叠态跨页持久化（键名对齐原型 ae_sidebar_fold）
    collapsed: localStorage.getItem('ae_sidebar_fold') === '1',
  }),
  actions: {
    apply() {
      document.documentElement.setAttribute('data-theme', this.mode)
      localStorage.setItem('data-theme', this.mode)
    },
    toggle() {
      this.mode = this.mode === 'light' ? 'dark' : 'light'
      this.apply()
    },
    toggleCollapsed() {
      this.collapsed = !this.collapsed
      localStorage.setItem('ae_sidebar_fold', this.collapsed ? '1' : '0')
    },
  },
})
