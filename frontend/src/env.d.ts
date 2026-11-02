/// <reference types="vite/client" />

// 构建时由 vite.config.js 的 define 注入
declare const __BUILD_VERSION__: string
declare const __BUILD_TIME__: string

interface ImportMetaEnv {
  /** 值为 "1" 时允许生产构建使用本地 Mock 数据（默认为关闭）。 */
  readonly VITE_ENABLE_MOCK?: string
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, any>
  export default component
}
